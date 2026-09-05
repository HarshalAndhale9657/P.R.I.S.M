"""Unit tests for academic-corpus retrieval (pure parts; providers and the fetcher are faked)."""
from types import SimpleNamespace

import services.academic_corpus as ac
from services.academic_corpus import Candidate, ProviderContext
from services.plagiarism_matcher import SourceDoc

DOC = ("A sufficiently long sentence with plenty of words to become a query for the providers here. "
       "Density based clustering determines the number of clusters without a preset count parameter.")


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


def test_mk_marks_abstracts_and_drops_empty_pdf_links():
    c = ac._mk("openalex", "T", 2020, "abstract text " * 10, "u", [None, "https://x.org/a.pdf", ""])
    assert c.doc.kind == "abstract" and c.pdf_urls == ["https://x.org/a.pdf"]


def test_semanticscholar_is_skipped_without_a_key():
    ctx = ProviderContext(queries=["q"], per_query=5, timeout=1.0, max_sources=5, s2_api_key=None)
    assert ac._search_semanticscholar(ctx) == ([], [])


def test_search_merges_dedups_unions_pdf_links_and_reids(monkeypatch):
    def fake_openalex(ctx):
        return [ac._mk("openalex", "Same Paper", 2020, "short abstract " * 10, "u1", ["https://oa.org/same.pdf"]),
                ac._mk("openalex", "Only Here", 2019, "abstract text " * 10, "u2")], []

    def fake_arxiv(ctx):
        return [ac._mk("arxiv", "Same paper", None, "a much longer abstract " * 20, "u3",
                       ["https://arxiv.org/pdf/1.pdf"])], ["arxiv-warn"]

    monkeypatch.setitem(ac._PROVIDERS, "openalex", fake_openalex)
    monkeypatch.setitem(ac._PROVIDERS, "arxiv", fake_arxiv)
    sources, warnings = ac.search(DOC, max_sources=5)
    assert len(sources) == 2 and "arxiv-warn" in warnings
    assert [s.id for s in sources] == ["ac-0", "ac-1"]
    same = next(s for s in sources if s.name.lower().startswith("same paper"))
    assert same.origin == "arxiv" and same.kind == "abstract"     # longer abstract wins; still an abstract


def test_search_provider_crash_degrades_to_warning(monkeypatch):
    def crash(ctx):
        raise RuntimeError("boom")
    monkeypatch.setitem(ac._PROVIDERS, "openalex", crash)
    monkeypatch.setitem(ac._PROVIDERS, "arxiv", crash)
    sources, warnings = ac.search(DOC)
    assert sources == [] and len(warnings) == 2


def test_search_passes_key_and_contact_through_context(monkeypatch):
    seen = {}

    def spy(ctx):
        seen.update(key=ctx.s2_api_key, mail=ctx.contact_email, n=len(ctx.queries))
        return [], []
    monkeypatch.setitem(ac._PROVIDERS, "semanticscholar", spy)
    ac.search(DOC, providers=("semanticscholar",), s2_api_key="K", contact_email="m@x.org")
    assert seen == {"key": "K", "mail": "m@x.org", "n": 2}


# ── Full-text enrichment ──────────────────────────────────────────────────────

class FakeFetcher:
    def __init__(self, texts):
        self.texts = texts          # url -> text or None
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        t = self.texts.get(url)
        return None if t is None else SimpleNamespace(url=url, text=t, page_count=3, byte_size=1000)


def test_fulltext_upgrades_most_relevant_candidates_only(monkeypatch):
    relevant_abs = "Density based clustering determines the number of clusters automatically in data."
    filler_abs = "Bananas potassium tropical climates harvest export markets annual yields."

    def fake(ctx):
        return [
            ac._mk("openalex", "Relevant", 2020, relevant_abs, "u1", ["https://oa.org/relevant.pdf"]),
            ac._mk("openalex", "Filler", 2020, filler_abs, "u2", ["https://oa.org/filler.pdf"]),
            ac._mk("openalex", "No PDF", 2020, relevant_abs + " variant", "u3"),
        ], []
    monkeypatch.setitem(ac._PROVIDERS, "openalex", fake)
    fetcher = FakeFetcher({"https://oa.org/relevant.pdf": "FULL TEXT " * 50, "https://oa.org/filler.pdf": "x" * 500})

    sources, warnings = ac.search(DOC, providers=("openalex",), fetcher=fetcher, fulltext_max_docs=1)
    by_name = {s.name.split(" (")[0]: s for s in sources}
    assert fetcher.calls == ["https://oa.org/relevant.pdf"]          # budget of 1 went to the relevant one
    assert by_name["Relevant"].kind == "fulltext" and by_name["Relevant"].text.startswith("FULL TEXT")
    assert by_name["Filler"].kind == "abstract" and by_name["No PDF"].kind == "abstract"
    assert any("Full text was retrieved for 1 of 2" in w for w in warnings)


def test_fulltext_failure_keeps_abstract_and_tries_second_link(monkeypatch):
    def fake(ctx):
        return [ac._mk("arxiv", "Paper", 2021, "abstract words " * 10, "u",
                       ["https://dead.org/a.pdf", "https://arxiv.org/pdf/a.pdf"])], []
    monkeypatch.setitem(ac._PROVIDERS, "arxiv", fake)
    fetcher = FakeFetcher({"https://dead.org/a.pdf": None, "https://arxiv.org/pdf/a.pdf": "the full paper " * 40})
    sources, _ = ac.search(DOC, providers=("arxiv",), fetcher=fetcher)
    assert fetcher.calls == ["https://dead.org/a.pdf", "https://arxiv.org/pdf/a.pdf"]
    assert sources[0].kind == "fulltext"

    fetcher2 = FakeFetcher({})
    sources2, warnings2 = ac.search(DOC, providers=("arxiv",), fetcher=fetcher2)
    assert sources2[0].kind == "abstract" and any("0 of 1" in w for w in warnings2)


def test_no_fetcher_means_abstracts_and_no_downloads(monkeypatch):
    monkeypatch.setitem(ac._PROVIDERS, "arxiv",
                        lambda ctx: ([ac._mk("arxiv", "P", 2021, "abstract " * 12, "u", ["https://arxiv.org/pdf/p"])], []))
    sources, warnings = ac.search(DOC, providers=("arxiv",), fetcher=None)
    assert sources[0].kind == "abstract" and not any("Full text" in w for w in warnings)


def test_rank_for_fulltext_prefers_lexical_overlap():
    doc = "density clustering clusters preset count parameter automatically"
    cands = [Candidate(SourceDoc("", "a", "Bananas potassium tropical harvest", "openalex", None, "abstract"), ["u1"]),
             Candidate(SourceDoc("", "b", "Density clustering determines clusters automatically", "openalex", None, "abstract"), ["u2"]),
             Candidate(SourceDoc("", "c", "no pdf link at all clusters", "openalex", None, "abstract"), [])]
    ranked = ac._rank_for_fulltext(doc, cands, limit=5)
    assert [c.doc.name for c in ranked] == ["b", "a"]


# ── Observability: worker threads keep the caller's context (request/job ids in logs) ──

import contextvars  # noqa: E402

_probe_var: contextvars.ContextVar = contextvars.ContextVar("prism_test_probe", default=None)


def test_provider_and_fulltext_threads_inherit_contextvars(monkeypatch):
    seen = {}

    def provider(ctx):
        seen["provider"] = _probe_var.get()
        return [ac._mk("arxiv", "P", 2021, "abstract " * 12, "u", ["https://arxiv.org/pdf/p"])], []

    class Fetcher:
        def fetch(self, url):
            seen["fetch"] = _probe_var.get()
            return None

    monkeypatch.setitem(ac._PROVIDERS, "arxiv", provider)
    token = _probe_var.set("job-42")
    try:
        ac.search(DOC, providers=("arxiv",), fetcher=Fetcher())
    finally:
        _probe_var.reset(token)
    assert seen == {"provider": "job-42", "fetch": "job-42"}
