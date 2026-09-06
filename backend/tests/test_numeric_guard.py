"""Unit tests for the numeric guard (ADR-0026) — the pure signal and its one shipped use."""
import pytest

from services.numeric_guard import DEFAULT_GATE, agreement, conflicts, numbers_in
from services.triage import Signals, collect_signals, triage_matches

# The pair ADR-0025 found: same skeleton, opposite direction, not one figure in common.
BOILERPLATE_A = "The broad Standard & Poor's 500 Index was up 8.79 points, or 0.96 percent, at 929.06."
BOILERPLATE_B = "The broader Standard & Poor's 500 Index gave up 11.91 points, or 1.19 percent, at 986.60."


# ── The signal ────────────────────────────────────────────────────────────────

def test_numbers_are_read_with_separators_and_decimals():
    assert numbers_in("up 8.79 points, or 0.96 percent, at 1,653.62") == [8.79, 0.96, 1653.62]


def test_small_number_words_count_so_a_paraphrase_may_spell_them_out():
    assert agreement("five patients withdrew", "5 patients withdrew") == 1.0


def test_repeated_figures_are_not_collapsed():
    """One shared figure must not vouch for a sentence that states it twice."""
    assert numbers_in("5% in 2020 and 5% in 2021") == [5.0, 2020.0, 5.0, 2021.0]


def test_the_boilerplate_pair_conflicts_even_though_it_shares_a_name_number():
    """`500` here is part of the index's *name*, not a fact either sentence states —
    which is exactly why the measured gate sits at 0.20 rather than at zero."""
    assert agreement(BOILERPLATE_A, BOILERPLATE_B) == pytest.approx(0.1429, abs=1e-4)
    assert conflicts(BOILERPLATE_A, BOILERPLATE_B) is True
    assert conflicts(BOILERPLATE_A, BOILERPLATE_B, gate=0.0) is False


def test_a_real_paraphrase_carries_its_figures_across():
    a = "Revenue grew 12 percent to $4.5 billion in 2023."
    b = "In 2023, revenue rose by 12 percent, reaching $4.5 billion."
    assert agreement(a, b) == 1.0
    assert conflicts(a, b) is False


def test_partial_overlap_is_not_a_conflict():
    """Partial overlap is normal in genuine paraphrase and must not fire the guard."""
    a = "The trial enrolled 120 patients over 3 years."
    b = "Over 4 years, 120 patients were enrolled in the trial."
    assert agreement(a, b) > DEFAULT_GATE
    assert conflicts(a, b) is False


def test_the_default_gate_is_the_measured_one():
    """Pinned so a future edit has to argue with eval/results/numeric_*.json."""
    assert DEFAULT_GATE == 0.20


def test_the_signal_is_silent_when_either_side_states_no_number():
    assert agreement("no figures at all here", "1,000 widgets were sold") is None
    assert conflicts("no figures at all here", "1,000 widgets were sold") is False
    assert agreement("nothing here", "nothing there") is None


def test_empty_text_is_handled():
    assert numbers_in("") == [] and numbers_in(None) == []
    assert agreement("", "5 things") is None


# ── The one shipped use ───────────────────────────────────────────────────────

def _matcher(**kw):
    from services.plagiarism_matcher import PlagiarismMatcher
    return PlagiarismMatcher(**kw)


class _StubEmbedder:
    """Every sentence embeds identically, so cosine is 1.0 and only the guard can move
    the band. No model, no network — the test is about the guard, not the encoder."""
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _check(doc, source_text, **kw):
    from services.plagiarism_matcher import SourceDoc
    # A distinct model key namespaces the shared embedding cache (ADR-0023), so these
    # stub vectors can never be handed to another test.
    m = _matcher(embedding_model_key="test-stub-numeric-guard", **kw)
    m._get_embedder = lambda: _StubEmbedder()
    return m.check(doc, [SourceDoc(id="s1", name="Source", text=source_text)])


def test_a_conflicting_pair_is_downgraded_to_review_but_still_reported():
    out = _check(BOILERPLATE_A, BOILERPLATE_B)
    para = [m for m in out["matches"] if m["match_type"] == "paraphrase"]
    assert para, "the guard must never remove a match — only soften the band"
    assert para[0]["confidence"] == "review"
    assert para[0]["numeric_conflict"] is True


def test_the_guard_can_be_turned_off():
    out = _check(BOILERPLATE_A, BOILERPLATE_B, numeric_guard=False)
    para = [m for m in out["matches"] if m["match_type"] == "paraphrase"]
    assert para[0]["confidence"] == "confident"
    assert para[0]["numeric_conflict"] is False


def test_agreeing_figures_stay_confident():
    a = "Revenue grew 12 percent to $4.5 billion in 2023 across every region we serve."
    b = "In 2023 revenue rose 12 percent, reaching $4.5 billion in all regions served."
    out = _check(a, b)
    para = [m for m in out["matches"] if m["match_type"] == "paraphrase"]
    assert para[0]["confidence"] == "confident"
    assert para[0]["numeric_conflict"] is False


def test_the_guard_never_moves_a_match_below_the_reporting_floor():
    """`review` is the floor of the downgrade: the match is still shown, with its source."""
    out = _check(BOILERPLATE_A, BOILERPLATE_B)
    para = [m for m in out["matches"] if m["match_type"] == "paraphrase"]
    assert para[0]["similarity"] >= out["engine"]["paraphrase_threshold"] if "engine" in out else True
    assert para[0]["source_excerpt"], "the source must remain visible on a downgraded match"


@pytest.mark.parametrize("guard", [True, False])
def test_the_guard_never_changes_the_number_of_matches(guard):
    kept = _check(BOILERPLATE_A, BOILERPLATE_B, numeric_guard=guard)
    assert len(kept["matches"]) == len(_check(BOILERPLATE_A, BOILERPLATE_B, numeric_guard=not guard)["matches"])


# ── Triage explains the downgrade ─────────────────────────────────────────────

def test_triage_carries_the_signal_and_explains_the_band():
    doc = BOILERPLATE_A
    matches = [{
        "match_type": "paraphrase", "confidence": "review", "numeric_conflict": True,
        "similarity": 0.877, "words": 16, "doc_start": 0, "doc_end": len(doc),
        "source_id": "s1", "source_excerpt": BOILERPLATE_B,
    }]
    triage_matches(doc, [], matches, [])
    t = matches[0]["triage"]
    assert t["signals"]["numeric_conflict"] is True
    assert t["note"] and "figure" in t["note"]
    assert t["type"] == "needs_review"


def test_triage_note_never_suggests_changing_the_numbers():
    """ADR-0014 boundary: guidance explains, it never hands over a way to score lower."""
    doc = BOILERPLATE_A
    matches = [{
        "match_type": "paraphrase", "confidence": "review", "numeric_conflict": True,
        "similarity": 0.877, "words": 16, "doc_start": 0, "doc_end": len(doc),
        "source_id": "s1", "source_excerpt": BOILERPLATE_B,
    }]
    triage_matches(doc, [], matches, [])
    note = matches[0]["triage"]["note"].lower()
    for banned in ("change the number", "alter the figure", "lower the score", "avoid detection"):
        assert banned not in note


def test_collect_signals_defaults_the_flag_off_for_older_matches():
    s = collect_signals("some text", [], {"doc_start": 0, "doc_end": 9, "source_id": "s1"}, {})
    assert isinstance(s, Signals) and s.numeric_conflict is False
