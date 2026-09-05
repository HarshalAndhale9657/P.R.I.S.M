"""Unit tests for the in-process rate limiter."""
from types import SimpleNamespace

from app.limits import RateLimiter, client_key


def test_rate_limiter_allows_then_denies_then_resets():
    rl = RateLimiter(limit=2, window_seconds=60)
    assert rl.check("ip", now=1000.0) is None
    assert rl.check("ip", now=1001.0) is None
    retry = rl.check("ip", now=1002.0)
    assert retry is not None and 1 <= retry <= 58
    assert rl.check("ip", now=1061.0) is None          # new window
    assert rl.check("other", now=1002.0) is None       # independent keys


def test_rate_limiter_disabled_when_limit_zero():
    rl = RateLimiter(limit=0, window_seconds=60)
    assert not rl.enabled
    assert all(rl.check("ip") is None for _ in range(50))


def test_rate_limiter_sweeps_stale_buckets():
    rl = RateLimiter(limit=1, window_seconds=10)
    for i in range(1100):
        rl.check(f"k{i}", now=0.0)
    rl.check("fresh", now=100.0)                       # triggers a sweep of the 1100 stale keys
    assert len(rl._buckets) == 1


def test_client_key_honours_proxy_only_when_trusted():
    req = SimpleNamespace(headers={"x-forwarded-for": "203.0.113.9, 10.0.0.1"},
                          client=SimpleNamespace(host="10.0.0.1"))
    assert client_key(req, trust_proxy=False) == "10.0.0.1"
    assert client_key(req, trust_proxy=True) == "203.0.113.9"
