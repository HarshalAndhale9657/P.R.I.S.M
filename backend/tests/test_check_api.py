"""Integration tests for the async /api/check flow (offline — no academic search)."""
import time


def _files(paper: bytes, ref: bytes | None = None):
    files = [("file", ("paper.txt", paper, "text/plain"))]
    if ref is not None:
        files.append(("references", ("ref.txt", ref, "text/plain")))
    return files


def _poll(client, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/check/{job_id}")
        assert r.status_code == 200, r.text
        d = r.json()
        if d["status"] in ("done", "error"):
            return d
        time.sleep(0.4)
    raise AssertionError("job did not finish within the timeout")


def _run_check(client, files, data):
    """Submit a check and poll it to completion; returns the final status payload."""
    r = client.post("/api/check", files=files, data=data)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["job_id"] and body["status"] in ("queued", "running")
    return _poll(client, body["job_id"])


# ── Health / contract ─────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi_lists_check_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/check" in paths
    assert "/api/check/{job_id}" in paths


def test_submit_returns_202_with_job_id(client, sample_paper, sample_ref):
    r = client.post("/api/check", files=_files(sample_paper, sample_ref), data={"use_academic": "false"})
    assert r.status_code == 202
    b = r.json()
    assert b["job_id"] and b["status"] in ("queued", "running")
    assert b["status_url"] == f"/api/check/{b['job_id']}"


def test_status_unknown_job_404(client):
    r = client.get("/api/check/does-not-exist")
    assert r.status_code == 404


def test_check_success_contract(client, sample_paper, sample_ref):
    d = _run_check(client, _files(sample_paper, sample_ref), {"use_academic": "false"})
    assert d["status"] == "done", d
    j = d["result"]

    assert j["status"] == "success"
    assert j["academic_used"] is False
    assert isinstance(j["document_text"], str) and j["document_text"]
    assert isinstance(j["paragraphs"], list) and j["paragraphs"]

    ov = j["overall"]
    for k in ("similarity_pct", "verbatim_pct", "paraphrase_pct", "translated_pct",
              "matched_words", "total_words", "match_count", "source_count"):
        assert k in ov
    assert ov["verbatim_pct"] > 0          # the transformer sentence is copied verbatim
    assert 0 <= ov["similarity_pct"] <= 100

    assert j["sources"] and j["sources"][0]["origin"] == "upload"

    verbatim = [m for m in j["matches"] if m["match_type"] == "verbatim"]
    assert verbatim
    m = verbatim[0]
    for k in ("id", "match_type", "similarity", "doc_start", "doc_end", "doc_excerpt",
              "source_id", "source_name", "source_origin", "source_start", "source_end",
              "source_excerpt", "source_context", "paragraph_index"):
        assert k in m
    assert m["doc_end"] > m["doc_start"]


# ── Error handling (validated synchronously at submit) ────────────────────────

def test_check_requires_a_source(client, sample_paper):
    r = client.post("/api/check", files=_files(sample_paper), data={"use_academic": "false"})
    assert r.status_code == 400
    assert "reference" in r.json()["detail"].lower()


def test_check_rejects_unsupported_filetype(client, sample_ref):
    files = [
        ("file", ("paper.exe", b"not a document", "application/octet-stream")),
        ("references", ("ref.txt", sample_ref, "text/plain")),
    ]
    r = client.post("/api/check", files=files, data={"use_academic": "false"})
    assert r.status_code == 400
    assert "PDF or TXT" in r.json()["detail"]


def test_check_empty_paper(client, sample_ref):
    r = client.post("/api/check", files=_files(b"", sample_ref), data={"use_academic": "false"})
    assert r.status_code in (400, 422)


def test_check_enforces_size_cap(client, monkeypatch, sample_ref):
    import main
    monkeypatch.setattr(main, "MAX_FILE_BYTES", 64)
    oversized = b"a" * 256
    r = client.post("/api/check", files=_files(oversized, sample_ref), data={"use_academic": "false"})
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


# ── Errors that happen in the worker become a job error (generic, no leakage) ──

def test_worker_error_is_generic(client, monkeypatch, sample_ref):
    import main

    def boom(*a, **k):
        raise RuntimeError("SECRET_INTERNAL_DETAIL")

    monkeypatch.setattr(main.plagiarism_matcher, "check", boom)
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
    # No usable sources → a user-safe CheckError surfaced as the job error.
    import main
    monkeypatch.setattr(main, "academic_search", lambda *a, **k: ([], ["no candidates"]))
    files = [
        ("file", ("paper.txt", sample_paper, "text/plain")),
        # a reference with no extractable text
        ("references", ("blank.txt", b"   \n  ", "text/plain")),
    ]
    d = _run_check(client, files, {"use_academic": "true"})
    assert d["status"] == "error"
    assert "no usable sources" in d["error"].lower()
