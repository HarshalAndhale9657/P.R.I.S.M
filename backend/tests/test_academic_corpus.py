"""Unit tests for the academic-corpus retrieval helpers (pure parts; providers are faked)."""
import services.academic_corpus as ac
from services.plagiarism_matcher import SourceDoc


def test_abstract_reconstructed_from_inverted_index():
    inv = {"clusters": [2], "Density": [0], "based": [1], "work.": [3]}
    assert ac._abstract_from_inverted(inv) == "Density based clusters work."
    assert ac._abstract_from_inverted(None) == ""


def test_build_queries_prefers_long_distinct_sentences():
    doc = ("Short one. " * 3
           + "This considerably longer sentence carries enough distinctive words to be a useful search query for us. "
           + "This considerably longer sentence carries enough distinctive words to be a useful search query for us. "
           + "Another long sentence with different content about density based clustering and cluster counts here.")
    qs = ac.build_queries(doc, max_queries=5)
    assert 1 <= len(qs) <= 2                         # duplicates collapse; short sentences dropped
    assert all(len(q.split()) <= 18 for q in qs)
    assert ac.build_queries("too short", max_queries=5) == []


def test_dedup_key_ignores_year_case_and_punctuation():
    a = SourceDoc("1", "Attention Is All You Need (2017)", "x")
    b = SourceDoc("2", "attention is all you need", "x")
    assert ac._dedup_key(a) == ac._dedup_key(b)


def test_user_agent_only_includes_contact_when_configured():
    assert "mailto:" not in ac._user_agent(None)
    assert ac._user_agent("ops@example.org").endswith("mailto:ops@example.org")


def test_search_merges_dedups_caps_and_reids(monkeypatch):
    def fake_openalex(queries, per_query, timeout, max_sources, contact_email=None):
        return [ac._mk("openalex", "Same Paper", 2020, "short abstract " * 10, "u1"),
                ac._mk("openalex", "Only Here", 2019, "abstract text " * 10, "u2")], []

    def fake_arxiv(queries, per_query, timeout, max_sources, contact_email=None):
        return [ac._mk("arxiv", "Same paper", None, "a much longer abstract " * 20, "u3")], ["arxiv-warn"]

    monkeypatch.setitem(ac._PROVIDERS, "openalex", fake_openalex)
    monkeypatch.setitem(ac._PROVIDERS, "arxiv", fake_arxiv)
    doc = "A sufficiently long sentence with plenty of words to become a query for the providers here."
    sources, warnings = ac.search(doc, max_sources=5)
    names = sorted(s.name for s in sources)
    assert len(sources) == 2 and "arxiv-warn" in warnings
    assert [s.id for s in sources] == ["ac-0", "ac-1"]
    same = next(s for s in sources if s.name.lower().startswith("same paper"))
    assert same.origin == "arxiv"                    # the longer abstract wins the dedup
    assert "Only Here (2019)" in names


def test_search_provider_crash_degrades_to_warning(monkeypatch):
    def crash(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setitem(ac._PROVIDERS, "openalex", crash)
    monkeypatch.setitem(ac._PROVIDERS, "arxiv", crash)
    doc = "A sufficiently long sentence with plenty of words to become a query for the providers here."
    sources, warnings = ac.search(doc)
    assert sources == [] and len(warnings) == 2
