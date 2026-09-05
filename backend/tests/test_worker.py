"""Unit tests for the worker layer: job store, TTL cache, bounded executor, runner."""
import threading
import time

import pytest
from conftest import make_settings

from pipeline import PipelineError
from worker import BoundedExecutor, CheckRequest, CheckRunner, InMemoryJobStore, QueueFull, TTLCache

# ── InMemoryJobStore ──────────────────────────────────────────────────────────

def test_store_create_get_update_snapshot():
    st = InMemoryJobStore(max_jobs=10, ttl_seconds=60)
    rec = st.create()
    assert st.get(rec.id).status == "queued"
    st.update(rec.id, status="done", result={"x": 1})
    snap = st.get(rec.id)
    assert snap.status == "done" and snap.result == {"x": 1}
    # The snapshot's *fields* are detached from the store (the result payload itself is
    # shared by reference and treated as immutable once written — it is polled often).
    snap.status = "error"
    assert st.get(rec.id).status == "done"


def test_store_evicts_oldest_beyond_max():
    st = InMemoryJobStore(max_jobs=3, ttl_seconds=60)
    ids = [st.create().id for _ in range(5)]
    assert len(st) == 3
    assert st.get(ids[0]) is None and st.get(ids[-1]) is not None


def test_store_expires_by_ttl():
    st = InMemoryJobStore(max_jobs=10, ttl_seconds=1)
    rec = st.create()
    st._jobs[rec.id].updated -= 5                 # age it past the TTL
    assert st.get(rec.id) is None                 # lazy purge on read
    rec2 = st.create()
    st._jobs[rec2.id].updated -= 5
    assert st.sweep() == 1 and len(st) == 0


# ── TTLCache ──────────────────────────────────────────────────────────────────

def test_ttl_cache_lru_and_expiry():
    c = TTLCache(max_size=2, ttl_seconds=1)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1                        # touch a -> b is now LRU
    c.put("c", 3)
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3
    c._data["a"] = (time.time() - 5, 1)
    assert c.get("a") is None


# ── BoundedExecutor ───────────────────────────────────────────────────────────

def test_executor_rejects_when_pending_full():
    gate = threading.Event()
    ex = BoundedExecutor(max_workers=1, max_pending=1)
    try:
        ex.submit(gate.wait)                      # occupies the single worker
        time.sleep(0.05)
        ex.submit(gate.wait)                      # sits in the queue (pending=1)
        with pytest.raises(QueueFull):
            ex.submit(gate.wait)
        s = ex.stats()
        assert s["pending"] == 1 and s["capacity"] == 1
    finally:
        gate.set()
        ex.shutdown(wait=True)


def test_executor_zero_pending_means_no_queue():
    ex = BoundedExecutor(max_workers=1, max_pending=0)
    try:
        with pytest.raises(QueueFull):
            ex.submit(lambda: None)
    finally:
        ex.shutdown()


# ── CheckRunner (fake matcher, no model, no network) ──────────────────────────

class CountingMatcher:
    paraphrase_threshold = 0.66
    confident_threshold = 0.78

    def __init__(self):
        self.calls = 0

    def check(self, doc_text, sources):
        self.calls += 1
        return {
            "overall": {"similarity_pct": 0.0, "verbatim_pct": 0.0, "paraphrase_pct": 0.0, "translated_pct": 0.0,
                        "confident_pct": 0.0, "review_pct": 0.0, "matched_words": 0, "total_words": 5,
                        "match_count": 0, "review_count": 0, "source_count": 0},
            "per_source": [], "matches": [], "warnings": [], "paraphrase_enabled": False,
        }


def _runner(matcher=None, **settings_overrides):
    s = make_settings(**settings_overrides)
    return CheckRunner(
        settings=s,
        store=InMemoryJobStore(max_jobs=10, ttl_seconds=60),
        executor=BoundedExecutor(max_workers=1, max_pending=4),
        matcher=matcher or CountingMatcher(),
        academic_search=lambda text: ([], []),
    )


def _wait(runner, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rec = runner.status(job_id)
        if rec.status in ("done", "error"):
            return rec
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _req(text=b"one two three four five words here.", refs=None, academic=False):
    return CheckRequest(paper=("p.txt", text), references=refs if refs is not None else [("r.txt", b"ref words here")],
                        use_academic=academic, base_warnings=[])


def test_runner_runs_pipeline_and_caches_by_content():
    m = CountingMatcher()
    r = _runner(m)
    a = _wait(r, r.submit(_req()).id)
    assert a.status == "done"
    assert a.result["engine"]["version"] and "timings_ms" in a.result
    assert a.result["paragraphs"][0]["start"] == 0
    b = _wait(r, r.submit(_req()).id)             # identical content -> cache hit
    assert b.status == "done" and m.calls == 1


def test_runner_surfaces_pipeline_errors_verbatim():
    r = _runner()
    rec = _wait(r, r.submit(_req(refs=[])).id)    # no sources at all
    assert rec.status == "error" and "no usable sources" in rec.error.lower()


def test_runner_hides_internal_errors():
    class Boom(CountingMatcher):
        def check(self, *a, **k):
            raise RuntimeError("stack trace with secrets")
    r = _runner(Boom())
    rec = _wait(r, r.submit(_req(text=b"unique text " + str(time.time()).encode())).id)
    assert rec.status == "error"
    assert "secrets" not in rec.error and "try again" in rec.error.lower()


def test_runner_marks_job_error_when_queue_full():
    r = _runner(max_pending_jobs=0)
    r.executor = BoundedExecutor(max_workers=1, max_pending=0)
    with pytest.raises(QueueFull):
        r.submit(_req())


def test_pipeline_error_message_is_user_facing():
    assert str(PipelineError("No readable text")) == "No readable text"
