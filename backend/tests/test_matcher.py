"""Unit tests for the PlagiarismMatcher (pure, offline)."""
import pytest

from services.plagiarism_matcher import PlagiarismMatcher, SourceDoc
from conftest import requires_model

SRC_TRANSFORMER = (
    "The transformer architecture relies entirely on self-attention mechanisms "
    "to draw global dependencies between input and output sequences."
)
SRC_CLUSTER = (
    "Density-based clustering automatically determines the number of clusters "
    "present in a dataset without requiring a preset count parameter."
)


@pytest.fixture
def matcher():
    return PlagiarismMatcher()


def _overall_keys(ov):
    return {
        "similarity_pct", "verbatim_pct", "paraphrase_pct", "translated_pct",
        "confident_pct", "review_pct",
        "matched_words", "total_words", "match_count", "review_count", "source_count",
    } <= set(ov)


# ── Verbatim (no model needed) ────────────────────────────────────────────────

def test_verbatim_detected(matcher):
    doc = (
        "An original opening sentence about unrelated topics and everyday life. "
        + SRC_TRANSFORMER
        + " A closing original remark about weather and weekend plans."
    )
    r = matcher.check(doc, [SourceDoc("s0", "Src", SRC_TRANSFORMER)])
    verbatim = [m for m in r["matches"] if m["match_type"] == "verbatim"]
    assert verbatim, "expected a verbatim match"
    assert "self-attention mechanisms to draw global" in verbatim[0]["doc_excerpt"]
    assert verbatim[0]["source_id"] == "s0"
    assert verbatim[0]["source_origin"] == "upload"
    assert r["overall"]["verbatim_pct"] > 0
    assert _overall_keys(r["overall"])


def test_matched_words_never_exceed_total(matcher):
    doc = SRC_TRANSFORMER + " " + SRC_TRANSFORMER
    r = matcher.check(doc, [SourceDoc("s0", "Src", SRC_TRANSFORMER)])
    assert r["overall"]["matched_words"] <= r["overall"]["total_words"]
    assert 0 <= r["overall"]["similarity_pct"] <= 100


def test_verbatim_spans_non_overlapping(matcher):
    doc = SRC_TRANSFORMER + " " + SRC_TRANSFORMER
    r = matcher.check(doc, [SourceDoc("s0", "Src", SRC_TRANSFORMER)])
    spans = sorted((m["doc_start"], m["doc_end"]) for m in r["matches"] if m["match_type"] == "verbatim")
    for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
        assert prev_end <= next_start, "verbatim doc spans must not overlap"


def test_original_text_not_flagged(matcher):
    doc = "On weekends the campus cafeteria serves a rotating menu of regional dishes that many students enjoy."
    r = matcher.check(doc, [SourceDoc("s0", "Src", SRC_TRANSFORMER)])
    assert r["overall"]["verbatim_pct"] == 0.0
    assert all(m["match_type"] != "verbatim" for m in r["matches"])


def test_case_and_punctuation_insensitive(matcher):
    doc = "the TRANSFORMER architecture relies entirely on self-attention mechanisms to draw global dependencies between input and output sequences!!!"
    r = matcher.check(doc, [SourceDoc("s0", "Src", SRC_TRANSFORMER)])
    assert any(m["match_type"] == "verbatim" for m in r["matches"])


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_no_sources_warns(matcher):
    r = matcher.check("some document text that is reasonably long here", [])
    assert r["matches"] == []
    assert r["overall"]["similarity_pct"] == 0.0
    assert any("reference" in w.lower() for w in r["warnings"])


def test_empty_document(matcher):
    r = matcher.check("", [SourceDoc("s0", "Src", SRC_TRANSFORMER)])
    assert r["matches"] == []
    assert r["overall"]["total_words"] == 0
    assert r["overall"]["similarity_pct"] == 0.0


def test_blank_source_ignored(matcher):
    r = matcher.check(SRC_TRANSFORMER, [SourceDoc("s0", "Blank", "   ")])
    assert r["matches"] == []


def test_every_match_has_excerpts(matcher):
    doc = SRC_TRANSFORMER + " plus original tail text about nothing in particular here."
    r = matcher.check(doc, [SourceDoc("s0", "Src", SRC_TRANSFORMER)])
    for m in r["matches"]:
        assert m["doc_excerpt"], "doc_excerpt must be populated"
        assert m["source_excerpt"], "source_excerpt must be populated"
        assert m["doc_end"] > m["doc_start"]


# ── Confidence band (inconclusive "review" vs "confident") ───────────────────

def test_verbatim_is_always_confident(matcher):
    doc = SRC_TRANSFORMER + " A closing original remark about weekend plans and weather."
    r = matcher.check(doc, [SourceDoc("s0", "Src", SRC_TRANSFORMER)])
    verbatim = [m for m in r["matches"] if m["match_type"] == "verbatim"]
    assert verbatim
    assert all(m["confidence"] == "confident" for m in verbatim)
    assert r["overall"]["confident_pct"] > 0
    assert r["overall"]["review_pct"] == 0.0


def test_confidence_band_thresholds():
    """A match between paraphrase_threshold and confident_threshold is labelled
    'review'; at/above confident_threshold it is 'confident'."""
    m = PlagiarismMatcher(paraphrase_threshold=0.66, confident_threshold=0.78)
    assert m.paraphrase_threshold == 0.66 and m.confident_threshold == 0.78
    # confident_threshold can never sit below the reporting floor
    m2 = PlagiarismMatcher(paraphrase_threshold=0.80, confident_threshold=0.50)
    assert m2.confident_threshold == 0.80


def test_every_match_carries_a_confidence(matcher):
    doc = SRC_TRANSFORMER + " plus original tail text about nothing in particular here."
    r = matcher.check(doc, [SourceDoc("s0", "Src", SRC_TRANSFORMER)])
    for mm in r["matches"]:
        assert mm["confidence"] in ("confident", "review")


# ── Paraphrase / translated (model-dependent) ────────────────────────────────

@requires_model
def test_paraphrase_detected(matcher):
    doc = (
        "Clustering methods based on density can infer how many groups exist in the data "
        "without needing a fixed number to be specified in advance. "
        "This closing sentence is entirely original filler about something else."
    )
    r = matcher.check(doc, [SourceDoc("s0", "Src", SRC_CLUSTER)])
    if not r["paraphrase_enabled"]:
        pytest.skip("embedding model unavailable at runtime")
    assert any(m["match_type"] == "paraphrase" for m in r["matches"])
    assert r["overall"]["paraphrase_pct"] > 0


@requires_model
def test_translated_detected_with_language_pair(matcher):
    fr = (
        "L'architecture du transformateur repose entièrement sur des mécanismes d'auto-attention "
        "pour établir des dépendances globales entre les séquences d'entrée et de sortie."
    )
    doc = (
        "The transformer architecture relies entirely on self-attention mechanisms to establish "
        "global dependencies between input and output sequences. "
        "A separate original closing remark follows here for good measure."
    )
    r = matcher.check(doc, [SourceDoc("s0", "FR", fr)])
    if not r["paraphrase_enabled"]:
        pytest.skip("embedding model unavailable at runtime")
    translated = [m for m in r["matches"] if m["match_type"] == "translated"]
    assert translated, "expected a translated match"
    m = translated[0]
    assert m["source_lang"] and m["doc_lang"] and m["source_lang"] != m["doc_lang"]
    assert r["overall"]["translated_pct"] > 0
