"""
P.R.I.S.M. — Rate limiting
==========================
A fixed-window counter per client key, in-process. Deliberately simple: the
product runs as a single process on one box (LAUNCH_PLAN §4), and the goal is
to stop one client from monopolising a CPU-bound endpoint — not to build a
distributed quota system. When accounts land (W7) the key becomes the user id
and the store moves to Postgres/Redis behind the same interface.

Windows are swept lazily on access so memory stays bounded by the number of
distinct clients seen in one window.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import HTTPException, Request


@dataclass
class _Window:
    start: float
    count: int


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._buckets: Dict[str, _Window] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    def check(self, key: str, now: Optional[float] = None) -> Optional[int]:
        """Record one hit for `key`. Returns None if allowed, else seconds until the window resets."""
        if not self.enabled:
            return None
        now = time.time() if now is None else now
        with self._lock:
            self._sweep(now)
            w = self._buckets.get(key)
            if w is None or now - w.start >= self.window:
                self._buckets[key] = _Window(start=now, count=1)
                return None
            if w.count >= self.limit:
                return max(1, int(w.start + self.window - now))
            w.count += 1
            return None

    def _sweep(self, now: float) -> None:
        if len(self._buckets) < 1024:
            return
        stale = [k for k, w in self._buckets.items() if now - w.start >= self.window]
        for k in stale:
            del self._buckets[k]


def client_key(request: Request, *, trust_proxy: bool) -> str:
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency: 429 with Retry-After when the client is over its submission budget."""
    limiter: RateLimiter = request.app.state.rate_limiter
    settings = request.app.state.settings
    retry = limiter.check(client_key(request, trust_proxy=settings.trust_proxy))
    if retry is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many checks from this address. Please wait a few minutes and try again.",
            headers={"Retry-After": str(retry)},
        )
