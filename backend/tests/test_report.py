"""Submission-risk report + before/after re-check (W10, ADR-0032). Pure functions, then the API."""
from conftest import make_client

from services.report import BANDS, DISCLOSURE, FOOTER, build_report, compare

PAPER = (b"The proliferation of transformer-based architectures has fundamentally reshaped natural language processing.\n"
         b"Attention mechanisms permit the model to weigh the relevance of each token with respect to every other token.\n")
REF = (b"Transformer architectures have spread widely and completely changed how natural language processing is done.\n"
       b"Attention mechanisms permit the model to weigh the relevance of each token with respect to every other token.\n")
EDITED = (b"The proliferation of transformer-based architectures has fundamentally reshaped natural language processing.\n"
          b"Self-attention lets every position consult every other position when building its representation [1].\n")


def _overall(**kw):
    base = {"similarity_pct": 12.0, "verbatim_pct": 4.0, "paraphrase_pct": 8.0, "translated_pct": 0.0,
            "confident_pct": 9.0, "review_pct": 3.0, "matched_words": 30, "total_words": 250,
            "match_count": 3, "review_count": 1, "source_count": 2}
    base.update(kw)
    return base


def _triage(needs_action=0, items=()):
    return {"counts": {}, "needs_action": needs_action, "action_items": list(items), "method": "rules"}


# ── The report ────────────────────────────────────────────────────────────────

def test_band_is_act_when_something_needs_fixing():
    r = build_report(overall=_overall(), matches=[], coverage="c",
                     triage_summary=_triage(2, [{"type": "verbatim_uncited", "label": "Word-for-word, not cited",
                                                 "count": 2, "priority": 1}]))
    assert r["band"] == "act" and r["label"] == BANDS["act"][0]
    assert r["checklist"][0]["type"] == "verbatim_uncited" and r["checklist"][0]["count"] == 2


def test_band_is_look_for_cited_paraphrase_or_inconclusive_only():
    r = build_report(overall=_overall(review_count=1), matches=[], coverage="c", triage_summary=_triage(0, []))
    assert r["band"] == "look"
    r = build_report(overall=_overall(review_count=0), matches=[], coverage="c",
                     triage_summary=_triage(0, [{"type": "paraphrase_cited", "label": "Cited paraphrase",
                                                 "count": 1, "priority": 3}]))
    assert r["band"] == "look"


def test_band_is_clear_only_when_nothing_is_flagged_and_says_what_that_means():
    r = build_report(overall=_overall(match_count=0, review_count=0), matches=[], coverage="uploads only",
                     triage_summary=_triage(0, []))
    assert r["band"] == "clear"
    assert "sources that were checked" in r["reason"]
    assert r["coverage"] == "uploads only"


def test_report_never_claims_a_pass_and_always_carries_the_footer_and_disclosure():
    r = build_report(overall=_overall(), matches=[], coverage="c", triage_summary=_triage())
    text = " ".join([r["label"], r["reason"], r["footer"], r["disclosure"]]).lower()
    assert "guaranteed pass" not in text.replace("not a guarantee", "")
    assert r["footer"] == FOOTER and r["disclosure"] == DISCLOSURE
    assert "does not detect AI-written text" in r["disclosure"]
    assert "not performed" in r["ai_text_detection"]


def test_checklist_is_priority_ordered_and_ends_with_the_standing_items():
    r = build_report(overall=_overall(), matches=[], coverage="c", triage_summary=_triage(1, [
        {"type": "paraphrase_cited", "label": "Cited paraphrase", "count": 3, "priority": 3},
        {"type": "paraphrase_uncited", "label": "Close paraphrase, no citation", "count": 1, "priority": 1},
    ]))
    kinds = [(c["kind"], c["priority"]) for c in r["checklist"]]
    assert kinds == [("flag", 1), ("flag", 3), ("standing", 3), ("standing", 4)]


# ── The re-check ──────────────────────────────────────────────────────────────

def _m(src_excerpt, *, mtype="paraphrase", sid="s1", prio=1, sim=0.9, doc_start=0):
    return {"match_type": mtype, "source_id": sid, "source_name": "Source", "source_excerpt": src_excerpt,
            "similarity": sim, "doc_start": doc_start, "doc_end": doc_start + 10,
            "triage": {"type": "paraphrase_uncited", "priority": prio}}


def test_compare_counts_resolved_new_and_remaining_by_source_not_position():
    prev = {"filename": "paper.txt", "overall": _overall(match_count=2, similarity_pct=12.0),
            "triage_summary": _triage(2), "matches": [_m("alpha sentence"), _m("beta sentence", doc_start=50)]}
    cur = {"filename": "paper.txt", "overall": _overall(match_count=2, similarity_pct=7.5),
           "triage_summary": _triage(1), "matches": [_m("beta sentence", doc_start=900), _m("gamma sentence")]}
    d = compare(prev, cur, previous_job_id="abc")
    assert (d["resolved"], d["new"], d["remaining"]) == (1, 1, 1)
    assert d["resolved_examples"][0]["source_excerpt"] == "alpha sentence"
    assert d["new_examples"][0]["source_excerpt"] == "gamma sentence"
    assert d["delta"]["similarity_pct"] == -4.5 and d["delta"]["needs_action"] == -1
    assert d["previous_job_id"] == "abc" and d["same_filename"] is True


def test_compare_flags_a_different_filename_rather_than_pretending():
    d = compare({"filename": "a.txt", "matches": []}, {"filename": "b.pdf", "matches": []})
    assert d["same_filename"] is False and d["resolved"] == d["new"] == 0


def test_compare_ignores_whitespace_and_case_in_the_source_excerpt():
    prev = {"filename": "p", "matches": [_m("The  Quick brown")]}
    cur = {"filename": "p", "matches": [_m("the quick   brown")]}
    assert compare(prev, cur)["remaining"] == 1


# ── Through the API ───────────────────────────────────────────────────────────

def _files(paper):
    return [("file", ("paper.txt", paper, "text/plain")), ("references", ("ref.txt", REF, "text/plain"))]


def _finish(c, r):
    import time
    assert r.status_code == 202, r.text
    jid = r.json()["job_id"]
    for _ in range(300):
        d = c.get(f"/api/v1/check/{jid}").json()
        if d["status"] in ("done", "error"):
            assert d["status"] == "done", d
            return jid, d["result"]
        time.sleep(0.2)
    raise AssertionError("timed out")


def test_every_result_carries_a_report_and_the_engine_names_the_coach_state():
    with make_client() as c:
        _, res = _finish(c, c.post("/api/v1/check", files=_files(PAPER)))
        rep = res["report"]
        assert rep["band"] in ("act", "look", "clear") and rep["footer"] == FOOTER
        assert any(item["type"] == "disclosure" for item in rep["checklist"])
        assert res["engine"]["coach_model"] is None and res["engine"]["coach_estimated_cost_usd"] == 0.0
        assert res["recheck"] is None


def test_recheck_compares_the_edited_manuscript_with_the_previous_job():
    with make_client() as c:
        first_id, first = _finish(c, c.post("/api/v1/check", files=_files(PAPER)))
        assert first["overall"]["match_count"] >= 1, "the fixture must produce at least one flag to resolve"
        _, second = _finish(c, c.post("/api/v1/check", files=_files(EDITED), data={"compare_to": first_id}))
        rc = second["recheck"]
        assert rc and rc["previous_job_id"] == first_id and rc["same_filename"] is True
        assert rc["before"]["match_count"] == first["overall"]["match_count"]
        assert rc["resolved"] >= 1, rc
        assert rc["delta"]["similarity_pct"] < 0


def test_recheck_against_an_unknown_or_foreign_job_is_404():
    with make_client() as c:
        r = c.post("/api/v1/check", files=_files(PAPER), data={"compare_to": "nope"})
        assert r.status_code == 404
