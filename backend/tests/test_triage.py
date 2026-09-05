"""Unit tests for deterministic flag triage (ADR-0022). Pure — no model, no network."""
import pytest

from services.plagiarism_matcher import SourceDoc
from services.triage import RULES, classify, collect_signals, find_citations, is_quoted, triage_matches

SRC = "Density-based clustering determines the number of clusters without a preset count parameter."


def _doc(body: str):
    text = body
    paragraphs = [{"index": 0, "page": 1, "start": 0, "end": len(text), "text": text}]
    return text, paragraphs


def _match(text: str, needle: str, mtype="verbatim", confidence="confident", **extra):
    start = text.index(needle)
    m = {"match_type": mtype, "confidence": confidence, "doc_start": start, "doc_end": start + len(needle),
         "doc_excerpt": needle, "source_excerpt": needle, "source_id": "s0", "paragraph_index": 0}
    m.update(extra)
    return m


# ── Signals ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("as shown earlier [12].", ["[12]"]),
    ("results agree [3, 4] and [7-9].", ["[3, 4]", "[7-9]"]),
    ("this was reported (Smith et al., 2020).", ["(Smith et al., 2020)"]),
    ("this was reported (Smith & Jones, 2019; Lee, 2021a).", ["(Smith & Jones, 2019; Lee, 2021a)"]),
    ("Smith (2020) argued the opposite.", ["Smith (2020)"]),
    ("Smith and Jones (2018) argued the opposite.", ["Smith and Jones (2018)"]),
    ("no citation here at all.", []),
    ("The value (approximately 2020 units) was high.", []),     # a number in parentheses is not a citation
])
def test_find_citations(text, expected):
    assert find_citations(text) == expected


def test_is_quoted_detects_marks_around_span():
    text = 'He wrote that “density-based clustering determines clusters” in 2019.'
    inner = "density-based clustering determines clusters"
    s = text.index(inner)
    assert is_quoted(text, s, s + len(inner))
    text2 = "He wrote that density-based clustering determines clusters in 2019."
    s2 = text2.index(inner)
    assert not is_quoted(text2, s2, s2 + len(inner))


def test_collect_signals_uses_paragraph_context_for_citations():
    text, paras = _doc(f"Prior work established this. {SRC} This is well known [4].")
    m = _match(text, SRC)
    s = collect_signals(text, paras, m, {})
    assert s.cited and s.citation_markers == ["[4]"] and not s.quoted and s.words == 13


def test_collect_signals_counts_sources_sharing_verbatim_text():
    text, paras = _doc(f"Intro. {SRC}")
    m = _match(text, SRC)
    norm = {"a": SRC.casefold().replace("-", " "), "b": "unrelated text", "c": "x " + SRC.lower().replace("-", " ") + " y"}
    s = collect_signals(text, paras, m, norm)
    assert s.shared_by_sources == 2


# ── Classification ────────────────────────────────────────────────────────────

def _cls(body, needle, **kw):
    text, paras = _doc(body)
    m = _match(text, needle, **kw)
    return classify(m, collect_signals(text, paras, m, kw.pop("_norm", {}))).type


def test_verbatim_without_citation_or_quotes_is_top_priority():
    assert _cls(f"We note that {SRC} Our method differs.", SRC) == "verbatim_uncited"
    assert RULES["verbatim_uncited"].priority == 1


def test_verbatim_cited_but_unquoted():
    assert _cls(f"As Ester et al. (1996) showed, {SRC}", SRC) == "verbatim_cited_unquoted"


def test_quoted_and_cited_is_attributed():
    assert _cls(f'Ester et al. (1996) state: "{SRC}"', SRC) == "quoted_cited"
    assert RULES["quoted_cited"].priority == 5


def test_quoted_without_citation():
    assert _cls(f'One paper states: "{SRC}" and moves on.', SRC) == "quoted_uncited"


def test_paraphrase_confident_uncited_vs_cited():
    para = "Clustering methods based on density can infer how many groups exist without a fixed number."
    assert _cls(f"In our reading, {para}", para, mtype="paraphrase") == "paraphrase_uncited"
    assert _cls(f"In our reading, {para} [2]", para, mtype="paraphrase") == "paraphrase_cited"


def test_review_band_is_needs_review_regardless_of_citation():
    para = "Clustering methods based on density can infer how many groups exist without a fixed number."
    assert _cls(f"{para} [2]", para, mtype="paraphrase", confidence="review") == "needs_review"


def test_common_phrase_by_stopword_ratio_and_by_repetition():
    phrase = "In this paper we show that it is the case that"
    assert _cls(f"{phrase} the sky is blue.", phrase) == "common_phrase"
    text, paras = _doc(f"Intro. {SRC}")
    m = _match(text, SRC)
    s = collect_signals(text, paras, m, {"a": SRC.casefold().replace("-", " "), "b": SRC.casefold().replace("-", " ")})
    assert classify(m, s).type == "common_phrase"


# ── Whole-document triage ─────────────────────────────────────────────────────

def test_triage_matches_annotates_and_summarises():
    para = "Clustering methods based on density can infer how many groups exist without a fixed number."
    text, paras = _doc(f"{SRC} Later, {para} And finally something quoted: \"{SRC}\" (Ester et al., 1996).")
    matches = [
        _match(text, SRC),                                                # first occurrence: uncited verbatim
        _match(text, para, mtype="paraphrase"),                           # uncited paraphrase
    ]
    quoted = _match(text, SRC)
    quoted["doc_start"] = text.rindex(SRC)
    quoted["doc_end"] = quoted["doc_start"] + len(SRC)
    matches.append(quoted)
    sources = [SourceDoc("s0", "Src", SRC + " " + para)]
    summary = triage_matches(text, paras, matches, sources)

    types = [m["triage"]["type"] for m in matches]
    # All three sit in one paragraph that also contains a citation, so the first two are "cited";
    # the third is quoted + cited.
    assert types == ["verbatim_cited_unquoted", "paraphrase_cited", "quoted_cited"]
    assert summary["counts"] == {"verbatim_cited_unquoted": 1, "paraphrase_cited": 1, "quoted_cited": 1}
    assert summary["needs_action"] == 1
    assert [a["type"] for a in summary["action_items"]] == ["verbatim_cited_unquoted", "paraphrase_cited"]
    assert all({"type", "priority", "label", "what", "fix", "signals"} <= set(m["triage"]) for m in matches)
    assert "self-reuse is not detected" in summary["method"]


def test_translated_match_gets_a_note():
    para = "Les méthodes de clustering basées sur la densité déterminent le nombre de groupes automatiquement."
    text, paras = _doc(f"Nous montrons que {para}")
    m = _match(text, para, mtype="translated")
    triage_matches(text, paras, [m], [])
    assert m["triage"]["type"] == "paraphrase_uncited" and "translated" in m["triage"]["note"].lower()


def test_guidance_never_suggests_evasion():
    forbidden = ("lower the score", "beat the", "avoid detection", "humaniz", "reword to pass", "spin")
    for r in RULES.values():
        text = (r.what + " " + r.fix).lower()
        assert not any(f in text for f in forbidden), r.type
