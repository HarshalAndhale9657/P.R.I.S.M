"""
P.R.I.S.M. — Authentication (W7, ADR-0030)
==========================================
Verifies the bearer JWT that Supabase Auth issues and turns it into a
``Principal`` the routers can reason about. Two verification modes, because
Supabase projects come in two generations:

* **HS256 with the project's JWT secret** (``PRISM_AUTH_JWT_SECRET``) — the classic
  setup, one shared secret.
* **Asymmetric via JWKS** (``PRISM_AUTH_JWKS_URL``, e.g.
  ``https://<ref>.supabase.co/auth/v1/.well-known/jwks.json``) — signing keys are
  fetched once and cached; a token whose ``kid`` is unknown triggers one refresh.

Either mode, both, or neither may be configured. **Neither** means the product
runs anonymous, exactly as before W7 — the self-check use case (ADR-0014) does not
require an account, and E2E/dev keep working without one.

Three rules that do not bend:

1. **A presented token is always verified.** Even when auth is optional, a bad or
   expired token is a **401**, never a silent downgrade to anonymous — otherwise a
   client that thinks it is signed in is quietly getting the anonymous limits.
2. **``auth_required`` gates the endpoints, not the verification.** With it on, no
   token is a 401. With it off, no token is an anonymous principal.
3. **Ownership answers 404, not 403.** A job id another user owns is
   indistinguishable from one that never existed; existence is not leaked.

Only claims PRISM uses are read: ``sub`` (the user id), ``email``, ``role``. Nothing
else from the token is trusted or stored.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: Optional[str] = None
    role: Optional[str] = None
    claims: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


class AuthError(Exception):
    """A token was presented and it is not acceptable."""


def _fetch_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    import requests

    r = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


class JWTVerifier:
    """Verifies Supabase-style JWTs. Construct once; safe to share across requests."""

    def __init__(
        self,
        *,
        secret: str = "",
        jwks_url: str = "",
        issuer: str = "",
        audience: str = "authenticated",
        leeway_seconds: int = 30,
        jwks_fetch: Callable[[str], Dict[str, Any]] = _fetch_json,
        jwks_ttl_seconds: int = 3600,
    ) -> None:
        self.secret = secret
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self.leeway = leeway_seconds
        self._fetch = jwks_fetch
        self._jwks_ttl = jwks_ttl_seconds
        self._keys: Dict[str, Any] = {}
        self._keys_fetched_at = 0.0
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.secret or self.jwks_url)

    # ── Keys ──────────────────────────────────────────────────────────────────

    def _key_for(self, kid: Optional[str], *, refresh: bool = False):
        from jwt.algorithms import get_default_algorithms

        with self._lock:
            stale = time.time() - self._keys_fetched_at > self._jwks_ttl
            if refresh or stale or not self._keys:
                doc = self._fetch(self.jwks_url)
                algs = get_default_algorithms()
                keys: Dict[str, Any] = {}
                for jwk in doc.get("keys", []):
                    alg = jwk.get("alg") or ("ES256" if jwk.get("kty") == "EC" else "RS256")
                    if alg not in algs:
                        continue
                    keys[jwk.get("kid", "")] = (alg, algs[alg].from_jwk(jwk))
                self._keys = keys
                self._keys_fetched_at = time.time()
            if kid in self._keys:
                return self._keys[kid]
            if kid is None and len(self._keys) == 1:
                return next(iter(self._keys.values()))
            return None

    # ── Verification ──────────────────────────────────────────────────────────

    def verify(self, token: str) -> Principal:
        import jwt

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token") from exc
        alg = header.get("alg", "")
        options = {"require": ["exp", "sub"]}
        kwargs: Dict[str, Any] = {"leeway": self.leeway, "options": options}
        if self.audience:
            kwargs["audience"] = self.audience
        else:
            options["verify_aud"] = False
        if self.issuer:
            kwargs["issuer"] = self.issuer

        try:
            if alg == "HS256":
                if not self.secret:
                    raise AuthError("HS256 token but no shared secret is configured")
                claims = jwt.decode(token, self.secret, algorithms=["HS256"], **kwargs)
            elif alg in ("RS256", "ES256"):
                if not self.jwks_url:
                    raise AuthError(f"{alg} token but no JWKS URL is configured")
                kid = header.get("kid")
                found = self._key_for(kid)
                if found is None:
                    found = self._key_for(kid, refresh=True)
                if found is None:
                    raise AuthError("unknown signing key")
                key_alg, key = found
                if key_alg != alg:
                    raise AuthError("token algorithm does not match its key")
                claims = jwt.decode(token, key, algorithms=[alg], **kwargs)
            else:
                raise AuthError(f"unsupported algorithm {alg!r}")
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("token has expired") from exc
        except jwt.PyJWTError as exc:
            raise AuthError("invalid token") from exc
        except Exception as exc:                          # JWKS fetch failures etc.
            if isinstance(exc, AuthError):
                raise
            logger.warning("token verification failed: %s", exc)
            raise AuthError("could not verify token") from exc

        sub = str(claims.get("sub") or "")
        if not sub:
            raise AuthError("token has no subject")
        return Principal(user_id=sub, email=claims.get("email"), role=claims.get("role"), claims=dict(claims))


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def _bearer(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def current_principal(request: Request) -> Optional[Principal]:
    """The signed-in user, or None when anonymous access is allowed and no token was sent.

    A token that is present is always verified (rule 1). ``auth_required`` decides
    whether *no* token is acceptable (rule 2).
    """
    settings = request.app.state.settings
    verifier: JWTVerifier = request.app.state.auth
    token = _bearer(request)
    if token is None:
        if settings.auth_required:
            raise HTTPException(status_code=401, detail="Sign in to run a check.",
                                headers={"WWW-Authenticate": "Bearer"})
        return None
    if not verifier.configured:
        raise HTTPException(status_code=401, detail="This server is not configured to accept sign-in tokens.",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        return verifier.verify(token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=f"Not signed in: {exc}.",
                            headers={"WWW-Authenticate": "Bearer"}) from exc
