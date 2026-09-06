"""Unit tests for the PlagiarismMatcher (pure, offline)."""
import pytest
from conftest import requires_model

from services.plagiarism_matcher import PlagiarismMatcher, SourceDoc

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


# ── Source-sentence budgeting (relevance-based, model-free) ──────────────────

from services.plagiarism_matcher import Unit  # noqa: E402


def _units(*texts):
    return [Unit(t, 0, len(t)) for t in texts]


def test_budget_keeps_relevant_sentences_from_late_sources():
    m = PlagiarismMatcher(max_source_sentences=3)
    doc = _units("The transformer architecture relies entirely on self-attention mechanisms.")
    filler = [(0, u) for u in _units(
        "Bananas are rich in potassium and grow in tropical climates around the world.",
        "The committee will reconvene on Thursday to discuss the annual budget report.",
        "Granite countertops resist heat but require periodic sealing against stains.",
        "Migratory birds navigate using the earth's magnetic field and star patterns.",
        "The recipe calls for two cups of flour and a pinch of salt before baking.",
    )]
    relevant = (1, _units("Self-attention mechanisms let the transformer architecture model dependencies.")[0])
    warnings = []
    kept = m._budget_source_sentences(doc, filler + [relevant], warnings)
    assert len(kept) == 3
    assert relevant in kept, "the lexically relevant sentence from the LAST source must survive the cap"
    assert warnings and "most lexically similar" in warnings[0] and "2 of 2 sources represented" in warnings[0]


def test_budget_is_noop_under_cap():
    m = PlagiarismMatcher(max_source_sentences=10)
    src = [(0, u) for u in _units("a b c d e f g.", "h i j k l m n.")]
    warnings = []
    assert m._budget_source_sentences(_units("x y z w v u t."), src, warnings) == src
    assert warnings == []


def test_budget_preserves_source_order():
    m = PlagiarismMatcher(max_source_sentences=2)
    doc = _units("alpha beta gamma delta epsilon zeta.")
    src = [(0, _units("alpha beta gamma related sentence here.")[0]),
           (1, _units("completely unrelated words about weather today.")[0]),
           (2, _units("delta epsilon zeta also related sentence here.")[0])]
    kept = m._budget_source_sentences(doc, src, [])
    assert [s for s, _ in kept] == [0, 2]


# ── Corpus-size-aware confidence cutoff (ADR-0024) ───────────────────────────

def test_cutoff_is_the_base_at_or_below_the_pivot():
    m = PlagiarismMatcher(confident_threshold=0.78, confidence_scale_pivot=500)
    assert m.confident_threshold_for(0) == 0.78
    assert m.confident_threshold_for(500) == 0.78


def test_cutoff_rises_with_corpus_size_and_is_capped():
    m = PlagiarismMatcher(confident_threshold=0.78, confidence_scale_k=0.06,
                          confidence_scale_pivot=500, confidence_ceiling=0.92)
    at_5k = m.confident_threshold_for(5000)
    assert m.confident_threshold_for(500) == 0.78 < m.confident_threshold_for(1500) < at_5k
    assert at_5k == pytest.approx(0.78 + 0.06, abs=1e-3)     # one decade above the pivot
    assert m.confident_threshold_for(10_000_000) <= 0.92     # ceiling holds


def test_cutoff_scaling_can_be_disabled():
    m = PlagiarismMatcher(confident_threshold=0.78, confidence_scaling=False)
    assert m.confident_threshold_for(100_000) == 0.78


def test_scaling_only_moves_matches_towards_review_never_to_clean():
    """The safety property: a bigger corpus may downgrade confidence, never hide a match."""
    scaled = PlagiarismMatcher(confidence_scaling=True)
    fixed = PlagiarismMatcher(confidence_scaling=False)
    assert scaled.paraphrase_threshold == fixed.paraphrase_threshold   # reporting floor untouched
    assert scaled.confident_threshold_for(6000) >= fixed.confident_threshold_for(6000)


@requires_model
def test_check_reports_the_cutoff_it_actually_applied():
    m = PlagiarismMatcher()
    r = m.check("Some document text that is long enough to be a sentence for matching.",
                [SourceDoc("s0", "Src", "An unrelated reference sentence with sufficient length here.")])
    assert r["confident_threshold_used"] == m.confident_threshold      # tiny corpus -> base
    assert r["corpus_sentences"] >= 1


# ── Sentence segmentation (ADR-0026) ──────────────────────────────────────────
# The old splitter broke on every period, so "up 8.79 points" became the sentence
# "up 8." — in a product whose users write "p = 0.05" and "Fig. 3" constantly.

from services.plagiarism_matcher import split_sentences  # noqa: E402


def _split(text):
    return [text[a:b].strip() for a, b in split_sentences(text)]


def test_a_decimal_does_not_end_a_sentence():
    text = "The index was up 8.79 points, or 0.96 percent, at 929.06."
    assert _split(text) == [text]


def test_statistics_survive_intact():
    assert _split("Values below p = 0.05 were significant. We used SPSS 24.0 throughout.") == [
        "Values below p = 0.05 were significant.",
        "We used SPSS 24.0 throughout.",
    ]


def test_known_abbreviations_do_not_end_a_sentence():
    assert _split("See Fig. 3 and Smith et al. 2019. The effect was small.") == [
        "See Fig. 3 and Smith et al. 2019.",
        "The effect was small.",
    ]


def test_initials_do_not_end_a_sentence():
    assert _split("J. R. R. Tolkien wrote it. It sold well.") == ["J. R. R. Tolkien wrote it.", "It sold well."]


def test_a_url_does_not_end_a_sentence():
    assert _split("Visit www.example.com for data. Then continue.") == [
        "Visit www.example.com for data.", "Then continue."]


def test_newlines_still_split():
    assert _split("A heading line\nAnd the body text") == ["A heading line", "And the body text"]


def test_question_and_exclamation_marks_still_split():
    assert _split("Is it right? Yes! Absolutely.") == ["Is it right?", "Yes!", "Absolutely."]


def test_offsets_point_at_the_real_text():
    text = "First sentence here. Second one at 3.5 metres. Third."
    for a, b in split_sentences(text):
        assert text[a:b] == text[a:b]          # trivially true, but pins the contract:
        assert 0 <= a < b <= len(text)         # spans are in-bounds and ordered
    spans = split_sentences(text)
    assert spans[0][0] == 0 and spans[-1][1] == len(text)
    assert all(spans[i][1] == spans[i + 1][0] for i in range(len(spans) - 1)), "spans must tile the text"


def test_a_numeric_sentence_is_matched_whole_not_truncated(matcher):
    """The regression this fixes: the embedded sentence used to be a fragment."""
    doc = "The broad Standard & Poor's 500 Index was up 8.79 points, or 0.96 percent, at 929.06."
    sents = matcher._sentences(doc)
    assert len(sents) == 1 and sents[0].text == doc
