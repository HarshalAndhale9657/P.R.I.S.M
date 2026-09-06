"""Authentication, ownership and quota (W7, ADR-0030) — offline, self-signed tokens."""
import time

import jwt
import pytest
from conftest import make_client

from app.auth import AuthError, JWTVerifier

SECRET = "test-project-jwt-secret-that-is-long-enough-for-hs256"
PAPER = b"The proliferation of transformer-based architectures has fundamentally reshaped natural language processing.\n"
REF = b"Transformer architectures have spread widely and completely changed how natural language processing is done.\n"


def _token(sub="user-a", *, secret=SECRET, aud="authenticated", exp_in=600, alg="HS256", key=None, **extra):
    claims = {"sub": sub, "aud": aud, "iat": int(time.time()), "exp": int(time.time()) + exp_in,
              "email": f"{sub}@example.test", "role": "authenticated", **extra}
    return jwt.encode(claims, key or secret, algorithm=alg, headers={"kid": extra.get("kid", "k1")})


def _files():
    return [("file", ("paper.txt", PAPER, "text/plain")), ("references", ("ref.txt", REF, "text/plain"))]


def _auth_client(**overrides):
    overrides.setdefault("auth_jwt_secret", SECRET)
    overrides.setdefault("auth_audience", "authenticated")
    return make_client(**overrides)


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


# ── The verifier ──────────────────────────────────────────────────────────────

def test_hs256_token_yields_a_principal():
    v = JWTVerifier(secret=SECRET)
    p = v.verify(_token("user-a"))
    assert p.user_id == "user-a" and p.email == "user-a@example.test" and p.role == "authenticated"


@pytest.mark.parametrize("bad, reason", [
    (lambda: _token(exp_in=-120), "expired"),
    (lambda: _token(secret="wrong-secret-wrong-secret-wrong-secret"), "signature"),
    (lambda: _token(aud="anon"), "audience"),
    (lambda: "not.a.token", "malformed"),
    (lambda: jwt.encode({"aud": "authenticated", "exp": int(time.time()) + 60}, SECRET, algorithm="HS256"), "no sub"),
])
def test_bad_tokens_are_rejected(bad, reason):
    v = JWTVerifier(secret=SECRET)
    with pytest.raises(AuthError):
        v.verify(bad())


def test_issuer_is_checked_when_configured():
    v = JWTVerifier(secret=SECRET, issuer="https://ref.supabase.co/auth/v1")
    assert v.verify(_token(iss="https://ref.supabase.co/auth/v1")).user_id == "user-a"
    with pytest.raises(AuthError):
        v.verify(_token(iss="https://evil.example"))


def test_hs256_token_without_a_secret_is_rejected_not_accepted():
    """No shared secret configured must never mean 'accept unsigned'."""
    v = JWTVerifier(jwks_url="https://example.test/jwks")
    with pytest.raises(AuthError):
        v.verify(_token())


def test_rs256_via_jwks_with_one_refresh_on_unknown_kid():
    """Asymmetric Supabase projects: keys come from a JWKS document, cached, refreshed once on a miss."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    k1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    k2 = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def jwk(key, kid):
        import json
        d = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
        d.update({"kid": kid, "alg": "RS256", "use": "sig"})
        return d

    docs = [{"keys": [jwk(k1, "k1")]}, {"keys": [jwk(k1, "k1"), jwk(k2, "k2")]}]
    calls = []

    def fetch(url):
        calls.append(url)
        return docs[min(len(calls) - 1, len(docs) - 1)]

    v = JWTVerifier(jwks_url="https://ref.supabase.co/auth/v1/.well-known/jwks.json", jwks_fetch=fetch)
    pem1 = k1.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    pem2 = k2.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())

    assert v.verify(_token("u1", alg="RS256", key=pem1, kid="k1")).user_id == "u1"
    assert v.verify(_token("u1", alg="RS256", key=pem1, kid="k1")).user_id == "u1"
    assert len(calls) == 1, "keys are cached"
    assert v.verify(_token("u2", alg="RS256", key=pem2, kid="k2")).user_id == "u2"
    assert len(calls) == 2, "an unknown kid triggers exactly one refresh"
    with pytest.raises(AuthError):
        v.verify(_token("u3", alg="RS256", key=pem2, kid="k9"))     # still unknown after refresh


# ── The endpoints ─────────────────────────────────────────────────────────────

def test_anonymous_still_works_when_auth_is_optional():
    with _auth_client(auth_required=False) as c:
        r = c.post("/api/v1/check", files=_files())
        assert r.status_code == 202, r.text
        assert c.get(f"/api/v1/check/{r.json()['job_id']}").status_code == 200


def test_a_presented_bad_token_is_401_even_when_auth_is_optional():
    """Rule 1: never a silent downgrade to anonymous."""
    with _auth_client(auth_required=False) as c:
        r = c.post("/api/v1/check", files=_files(), headers=_bearer(_token(exp_in=-120)))
        assert r.status_code == 401 and r.headers.get("www-authenticate") == "Bearer"


def test_no_token_is_401_when_auth_is_required():
    with _auth_client(auth_required=True) as c:
        assert c.post("/api/v1/check", files=_files()).status_code == 401
        assert c.get("/api/v1/check/anything").status_code == 401
        r = c.post("/api/v1/check", files=_files(), headers=_bearer(_token("user-a")))
        assert r.status_code == 202, r.text


def test_token_without_any_verifier_configured_is_401():
    with make_client(auth_jwt_secret="", auth_jwks_url="") as c:
        r = c.post("/api/v1/check", files=_files(), headers=_bearer(_token()))
        assert r.status_code == 401
        assert c.get("/health").json()["auth"] == "off"


def test_ownership_is_404_for_everyone_but_the_owner():
    """Rule 3: another user's job is indistinguishable from a job that never existed."""
    with _auth_client() as c:
        job = c.post("/api/v1/check", files=_files(), headers=_bearer(_token("user-a"))).json()["job_id"]
        assert c.get(f"/api/v1/check/{job}", headers=_bearer(_token("user-a"))).status_code == 200
        assert c.get(f"/api/v1/check/{job}", headers=_bearer(_token("user-b"))).status_code == 404
        assert c.get(f"/api/v1/check/{job}").status_code == 404
        assert c.get("/health").json()["auth"] == "optional"


def test_anonymous_jobs_stay_readable_by_id_as_before():
    with _auth_client() as c:
        job = c.post("/api/v1/check", files=_files()).json()["job_id"]
        assert c.get(f"/api/v1/check/{job}").status_code == 200
        assert c.get(f"/api/v1/check/{job}", headers=_bearer(_token("user-a"))).status_code == 200


def test_quota_is_402_after_the_limit_and_per_user():
    with _auth_client(quota_checks=2, quota_window_seconds=3600) as c:
        a, b = _bearer(_token("user-a")), _bearer(_token("user-b"))
        assert c.post("/api/v1/check", files=_files(), headers=a).status_code == 202
        assert c.post("/api/v1/check", files=_files(), headers=a).status_code == 202
        r = c.post("/api/v1/check", files=_files(), headers=a)
        assert r.status_code == 402, r.text
        assert r.headers["x-quota-limit"] == "2" and r.headers["x-quota-used"] == "2"
        assert "Upgrade" in r.json()["detail"]
        assert c.post("/api/v1/check", files=_files(), headers=b).status_code == 202, "quota is per user"
        assert c.post("/api/v1/check", files=_files()).status_code == 202, "anonymous is not quota-governed"


def test_a_rejected_submission_does_not_consume_quota():
    with _auth_client(quota_checks=1) as c:
        a = _bearer(_token("user-a"))
        bad = [("file", ("paper.exe", b"x", "application/octet-stream"))]
        assert c.post("/api/v1/check", files=bad, headers=a).status_code == 400
        assert c.post("/api/v1/check", files=_files(), headers=a).status_code == 202


def test_signed_in_users_are_not_subject_to_the_per_ip_limiter():
    """The quota replaces the IP limiter for accounts (LAUNCH_PLAN W7)."""
    with _auth_client(rate_limit_submissions=1, rate_limit_window_seconds=600, quota_checks=0) as c:
        a = _bearer(_token("user-a"))
        assert c.post("/api/v1/check", files=_files(), headers=a).status_code == 202
        assert c.post("/api/v1/check", files=_files(), headers=a).status_code == 202
        assert c.post("/api/v1/check", files=_files()).status_code == 202
        assert c.post("/api/v1/check", files=_files()).status_code == 429, "anonymous still is"
