"""Integration tests for the async /api/v1/check flow (offline — no academic search)."""
import time

from conftest import make_client

from app.schemas import CheckResult


def _files(paper: bytes, ref: bytes | None = None):
    files = [("file", ("paper.txt", paper, "text/plain"))]
    if ref is not None:
        files.append(("references", ("ref.txt", ref, "text/plain")))
    return files


def _poll(client, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/check/{job_id}")
        assert r.status_code == 200, r.text
        d = r.json()
        if d["status"] in ("done", "error"):
            return d
        time.sleep(0.3)
    raise AssertionError("job did not finish within the timeout")


def _run_check(client, files, data):
    """Submit a check and poll it to completion; returns the final status payload."""
    r = client.post("/api/v1/check", files=files, data=data)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["job_id"] and body["status"] in ("queued", "running")
    return _poll(client, body["job_id"])


# ── Health / contract ─────────────────────────────────────────────────────────

def test_health_reports_snapshot(client):
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["queue"]["capacity"] >= 1
    assert "version" in d and d["env"] == "test"
    # Operators need the embedding-cache hit rate to reason about latency (ADR-0023).
    assert d["embedding_cache"]["capacity"] >= 0 and "hit_rate" in d["embedding_cache"]


def test_root_is_health_alias(client):
    assert client.get("/").status_code == 200


def test_ready_is_503_while_warming_up():
    # Lifespan not entered -> warm-up thread never runs -> model_loaded stays False.
    c = make_client(warmup_models=True)
    r = c.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "starting"


def test_openapi_lists_check_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/check" in paths
    assert "/api/v1/check/{job_id}" in paths
    assert "/health" in paths


def test_request_id_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    r2 = client.get("/health")
    assert r2.headers["X-Request-ID"]  # minted when absent


def test_submit_returns_202_with_job_id(client, sample_paper, sample_ref):
    r = client.post("/api/v1/check", files=_files(sample_paper, sample_ref), data={"use_academic": "false"})
    assert r.status_code == 202
    b = r.json()
    assert b["job_id"] and b["status"] in ("queued", "running")
    assert b["status_url"] == f"/api/v1/check/{b['job_id']}"


def test_status_unknown_job_404(client):
    r = client.get("/api/v1/check/does-not-exist")
    assert r.status_code == 404


def test_check_success_contract(client, sample_paper, sample_ref):
    d = _run_check(client, _files(sample_paper, sample_ref), {"use_academic": "false"})
    assert d["status"] == "done", d
    j = d["result"]

    # The public contract: the result must round-trip through the response model.
    parsed = CheckResult.model_validate(j)
    assert parsed.status == "success"
    assert parsed.academic_used is False
    assert parsed.document_text and parsed.paragraphs
    assert parsed.engine.version and parsed.engine.paraphrase_threshold < parsed.engine.confident_threshold
    assert "uploaded reference" in parsed.engine.coverage
    assert "Not checked" in parsed.engine.coverage
    assert set(parsed.timings_ms) >= {"parse", "retrieve", "match", "localize"}

    ov = parsed.overall
    assert ov.verbatim_pct > 0          # the transformer sentence is copied verbatim
    assert 0 <= ov.similarity_pct <= 100
    assert parsed.sources and parsed.sources[0].origin == "upload"

    verbatim = [m for m in parsed.matches if m.match_type == "verbatim"]
    assert verbatim
    m = verbatim[0]
    assert m.confidence == "confident"
    assert m.doc_end > m.doc_start
    assert m.paragraph_index == 1        # second paragraph of the paper
    # W8 triage: the copied sentence has no quotes and no citation -> act first.
    assert m.triage is not None and m.triage.type == "verbatim_uncited" and m.triage.priority == 1
    assert parsed.triage_summary and parsed.triage_summary.needs_action >= 1


# ── Error handling (validated synchronously at submit) ────────────────────────

def test_check_requires_a_source(client, sample_paper):
    r = client.post("/api/v1/check", files=_files(sample_paper), data={"use_academic": "false"})
    assert r.status_code == 400
    assert "reference" in r.json()["detail"].lower()


def test_check_rejects_unsupported_filetype(client, sample_ref):
    files = [
        ("file", ("paper.exe", b"not a document", "application/octet-stream")),
        ("references", ("ref.txt", sample_ref, "text/plain")),
    ]
    r = client.post("/api/v1/check", files=files, data={"use_academic": "false"})
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]


def test_check_empty_paper(client, sample_ref):
    r = client.post("/api/v1/check", files=_files(b"", sample_ref), data={"use_academic": "false"})
    assert r.status_code in (400, 422)


def test_check_enforces_per_file_size_cap(client, monkeypatch, sample_ref):
    monkeypatch.setattr(client.app.state.settings, "max_file_bytes", 64)
    r = client.post("/api/v1/check", files=_files(b"a" * 256, sample_ref), data={"use_academic": "false"})
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


def test_check_enforces_aggregate_size_cap(client, monkeypatch, sample_paper):
    # Each reference fits individually; together they exceed the per-check cap.
    monkeypatch.setattr(client.app.state.settings, "max_request_bytes", len(sample_paper) + 300)
    files = _files(sample_paper) + [
        ("references", (f"r{i}.txt", b"x" * 200, "text/plain")) for i in range(3)
    ]
    r = client.post("/api/v1/check", files=files, data={"use_academic": "false"})
    assert r.status_code == 413
    assert "per check" in r.json()["detail"]


def test_oversized_declared_body_is_rejected_early(client, monkeypatch, sample_paper, sample_ref):
    r = client.post("/api/v1/check", files=_files(sample_paper, sample_ref),
                    headers={"Content-Length": str(10**12)})
    assert r.status_code == 413


def test_queue_full_returns_503_with_retry_after(sample_paper, sample_ref):
    c = make_client(max_pending_jobs=0)   # nothing may wait in the queue
    r = c.post("/api/v1/check", files=_files(sample_paper, sample_ref), data={"use_academic": "false"})
    assert r.status_code == 503
    assert r.headers.get("Retry-After")
    assert "busy" in r.json()["detail"].lower()


def test_rate_limit_returns_429(sample_paper, sample_ref):
    c = make_client(rate_limit_submissions=1, rate_limit_window_seconds=600)
    ok = c.post("/api/v1/check", files=_files(sample_paper, sample_ref), data={"use_academic": "false"})
    assert ok.status_code == 202
    denied = c.post("/api/v1/check", files=_files(sample_paper, sample_ref), data={"use_academic": "false"})
    assert denied.status_code == 429
    assert denied.headers.get("Retry-After")


# ── Errors that happen in the worker become a job error (generic, no leakage) ──

def test_worker_error_is_generic(client, monkeypatch, sample_ref):
    runner = client.app.state.runner

    def boom(*a, **k):
        raise RuntimeError("SECRET_INTERNAL_DETAIL")

    monkeypatch.setattr(runner.matcher, "check", boom)
    # Unique content so the result cache can't short-circuit the (patched) matcher.
    unique_paper = (
        "Nonce-" + str(time.time()) + " The transformer architecture relies entirely on "
        "self-attention mechanisms to draw global dependencies between input and output sequences."
    ).encode("utf-8")

    d = _run_check(client, _files(unique_paper, sample_ref), {"use_academic": "false"})
    assert d["status"] == "error"
    assert "SECRET_INTERNAL_DETAIL" not in str(d)
    assert "try again" in d["error"].lower()


def test_worker_reports_user_safe_errors(client, monkeypatch, sample_paper):
    # No usable sources -> a user-safe PipelineError surfaced as the job error.
    runner = client.app.state.runner
    monkeypatch.setattr(runner, "academic_search", lambda *a, **k: ([], ["no candidates"]))
    files = [
        ("file", ("paper.txt", sample_paper, "text/plain")),
        ("references", ("blank.txt", b"   \n  ", "text/plain")),   # nothing extractable
    ]
    d = _run_check(client, files, {"use_academic": "true"})
    assert d["status"] == "error"
    assert "no usable sources" in d["error"].lower()


def test_unreadable_manuscript_is_user_safe(client, sample_ref):
    files = [
        ("file", ("scan.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")),
        ("references", ("ref.txt", sample_ref, "text/plain")),
    ]
    d = _run_check(client, files, {"use_academic": "false"})
    assert d["status"] == "error"
    assert "no readable text" in d["error"].lower()
