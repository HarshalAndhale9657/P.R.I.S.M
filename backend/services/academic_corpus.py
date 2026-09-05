"""
P.R.I.S.M. — Academic Corpus Retrieval (Phase 2 → W4b)
=======================================================
Fetches candidate source documents from open-access academic databases so a paper
can be checked without the user supplying references. Providers run concurrently,
their results are merged + de-duplicated, then — where a candidate exposes an
open-access PDF — the **full text** is fetched (services.fulltext) so verbatim
matching becomes possible; otherwise the abstract is used and *labelled* as such.

Providers:
  • OpenAlex          — free, no key; abstracts via an inverted index; OA PDF via best_oa_location.
  • arXiv             — free; full abstracts + a PDF for every record; strong for CS / physics / ML.
  • Semantic Scholar  — needs an API key (429 without one); abstracts + openAccessPdf; broad coverage.

Crossref is intentionally NOT a content provider: its records rarely carry abstracts.
Unpaywall is not called directly: OpenAlex ingests Unpaywall's OA locations already.

Everything is defensive: any provider/network failure degrades to a warning and the
other providers still contribute; it never raises into the caller.
"""

from __future__ import annotations

import contextvars
import dataclasses
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from services.plagiarism_matcher import _WORD_RE, SourceDoc

logger = logging.getLogger(__name__)

_MIN_ABSTRACT = 60  # need enough text to match against

DEFAULT_PROVIDERS = ("openalex", "arxiv")
ALL_PROVIDERS = ("openalex", "arxiv", "semanticscholar")

# One pooled session with bounded retries for transient upstream failures. OpenAlex asks
# polite-pool users to identify themselves with a contact address; we only send one if
# the operator configured it (settings.contact_email) — never a placeholder.
_SESSION: Optional[requests.Session] = None
_SESSION_LOCK = threading.Lock()


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:
                s = requests.Session()
                retry = Retry(total=2, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504),
                              allowed_methods=frozenset({"GET"}), raise_on_status=False)
                s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))
                _SESSION = s
    return _SESSION


def _user_agent(contact_email: Optional[str]) -> str:
    ua = "PRISM-OriginalityChecker/0.9 (+https://github.com/HarshalAndhale9657/P.R.I.S.M)"
    return f"{ua} mailto:{contact_email}" if contact_email else ua


# ── Provider plumbing ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProviderContext:
    """Everything a provider needs; one object so adding a knob doesn't ripple through signatures."""
    queries: Sequence[str]
    per_query: int
    timeout: float
    max_sources: int
    contact_email: Optional[str] = None
    s2_api_key: Optional[str] = None


@dataclass
class Candidate:
    """A retrieved source plus any open-access PDF links we might fetch full text from."""
    doc: SourceDoc
    pdf_urls: List[str] = field(default_factory=list)


ProviderFn = Callable[[ProviderContext], Tuple[List[Candidate], List[str]]]


def _submit_with_context(ex: ThreadPoolExecutor, fn, *args):
    """Submit to a pool while propagating contextvars, so log lines emitted inside provider and
    full-text threads keep the calling job's request_id / job_id."""
    ctx = contextvars.copy_context()
    return ex.submit(ctx.run, fn, *args)


def _mk(origin: str, title: str, year, abstract: str, url, pdf_urls: Optional[List[str]] = None) -> Candidate:
    name = f"{title}" + (f" ({year})" if year else "")
    doc = SourceDoc(id="", name=name, text=f"{title}. {abstract}", origin=origin, url=url, kind="abstract")
    return Candidate(doc=doc, pdf_urls=[u for u in (pdf_urls or []) if u])


# ── OpenAlex ──────────────────────────────────────────────────────────────────
_OPENALEX_URL = "https://api.openalex.org/works"
_OPENALEX_SELECT = "id,display_name,publication_year,abstract_inverted_index,primary_location,best_oa_location,open_access"


def _abstract_from_inverted(inv: Optional[dict]) -> str:
    if not inv:
        return ""
    positions: List[Tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort(key=lambda t: t[0])
    return " ".join(w for _, w in positions)


def _search_openalex(ctx: ProviderContext) -> Tuple[List[Candidate], List[str]]:
    out, warnings, failures = [], [], 0
    headers = {"User-Agent": _user_agent(ctx.contact_email)}
    params_extra = {"mailto": ctx.contact_email} if ctx.contact_email else {}
    for query in ctx.queries:
        if len(out) >= ctx.max_sources:
            break
        try:
            resp = _session().get(
                _OPENALEX_URL,
                params={"search": query, "per-page": ctx.per_query, "select": _OPENALEX_SELECT, **params_extra},
                headers=headers, timeout=ctx.timeout,
            )
            if resp.status_code != 200:
                failures += 1
                continue
            for w in resp.json().get("results", []):
                abstract = _abstract_from_inverted(w.get("abstract_inverted_index"))
                if len(abstract) < _MIN_ABSTRACT:
                    continue
                title = w.get("display_name") or "Untitled"
                year = w.get("publication_year")
                url = (w.get("primary_location") or {}).get("landing_page_url") or w.get("id")
                best = w.get("best_oa_location") or {}
                pdfs = [best.get("pdf_url"), (w.get("open_access") or {}).get("oa_url")]
                out.append(_mk("openalex", title, year, abstract, url, pdfs))
        except requests.RequestException as e:
            failures += 1
            logger.warning("[P.R.I.S.M.] OpenAlex query failed: %s", str(e)[:120])
    if failures and not out:
        warnings.append("Could not reach OpenAlex — that source was skipped.")
    return out, warnings


# ── arXiv ─────────────────────────────────────────────────────────────────────
_ARXIV_MAX_QUERIES = 4  # arXiv is slower per call; cap the number of searches


def _search_arxiv(ctx: ProviderContext) -> Tuple[List[Candidate], List[str]]:
    out, warnings = [], []
    try:
        import arxiv
    except Exception:
        return out, ["arXiv client unavailable — that source was skipped."]

    client = arxiv.Client(page_size=ctx.per_query, delay_seconds=0.0, num_retries=2)
    failures = 0
    for query in list(ctx.queries)[:_ARXIV_MAX_QUERIES]:
        if len(out) >= ctx.max_sources:
            break
        try:
            search = arxiv.Search(query=query, max_results=ctx.per_query, sort_by=arxiv.SortCriterion.Relevance)
            for res in client.results(search):
                abstract = (res.summary or "").strip().replace("\n", " ")
                if len(abstract) < _MIN_ABSTRACT:
                    continue
                title = (res.title or "Untitled").strip()
                year = res.published.year if getattr(res, "published", None) else None
                url = getattr(res, "entry_id", None)
                out.append(_mk("arxiv", title, year, abstract, url, [getattr(res, "pdf_url", None)]))
        except Exception as e:
            failures += 1
            logger.warning("[P.R.I.S.M.] arXiv query failed: %s", str(e)[:120])
    if failures and not out:
        warnings.append("Could not reach arXiv — that source was skipped.")
    return out, warnings


# ── Semantic Scholar (keyed) ──────────────────────────────────────────────────
_S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_S2_FIELDS = "title,abstract,year,url,openAccessPdf"


def _search_semanticscholar(ctx: ProviderContext) -> Tuple[List[Candidate], List[str]]:
    if not ctx.s2_api_key:
        return [], []  # unauthenticated calls are rate-limited into uselessness (429); skip silently
    out, warnings, failures = [], [], 0
    headers = {"User-Agent": _user_agent(ctx.contact_email), "x-api-key": ctx.s2_api_key}
    for query in ctx.queries:
        if len(out) >= ctx.max_sources:
            break
        try:
            resp = _session().get(_S2_URL, params={"query": query, "limit": ctx.per_query, "fields": _S2_FIELDS},
                                  headers=headers, timeout=ctx.timeout)
            if resp.status_code != 200:
                failures += 1
                continue
            for p in resp.json().get("data", []):
                abstract = (p.get("abstract") or "").strip()
                if len(abstract) < _MIN_ABSTRACT:
                    continue
                title = p.get("title") or "Untitled"
                pdf = (p.get("openAccessPdf") or {}).get("url")
                out.append(_mk("semanticscholar", title, p.get("year"), abstract, p.get("url"), [pdf]))
        except requests.RequestException as e:
            failures += 1
            logger.warning("[P.R.I.S.M.] Semantic Scholar query failed: %s", str(e)[:120])
    if failures and not out:
        warnings.append("Could not reach Semantic Scholar — that source was skipped.")
    return out, warnings


_PROVIDERS: Dict[str, ProviderFn] = {
    "openalex": _search_openalex,
    "arxiv": _search_arxiv,
    "semanticscholar": _search_semanticscholar,
}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _dedup_key(s: SourceDoc) -> str:
    title = re.sub(r"\s*\(\d{4}\)\s*$", "", s.name or "")
    return re.sub(r"[^a-z0-9]", "", title.lower())[:60]


def build_queries(doc_text: str, max_queries: int = 8, words_per_query: int = 18) -> List[str]:
    """Turn the document's most distinctive (longest) sentences into search queries."""
    sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", doc_text or "")
    candidates = [s.strip() for s in sentences if len(_WORD_RE.findall(s)) >= 8]
    candidates.sort(key=lambda s: len(_WORD_RE.findall(s)), reverse=True)

    seen, queries = set(), []
    for s in candidates:
        query = " ".join(_WORD_RE.findall(s)[:words_per_query])
        key = query.lower()
        if query and key not in seen:
            seen.add(key)
            queries.append(query)
        if len(queries) >= max_queries:
            break
    return queries


def _lexical_overlap(doc_tokens: set, text: str) -> float:
    """Share of a candidate's distinct tokens that also occur in the document (0..1)."""
    toks = {t.lower() for t in _WORD_RE.findall(text) if len(t) > 3}
    return len(toks & doc_tokens) / len(toks) if toks else 0.0


def _rank_for_fulltext(doc_text: str, cands: List[Candidate], limit: int) -> List[Candidate]:
    """Pick which OA candidates deserve a (comparatively expensive) full-text download."""
    doc_tokens = {t.lower() for t in _WORD_RE.findall(doc_text) if len(t) > 3}
    with_pdf = [c for c in cands if c.pdf_urls]
    with_pdf.sort(key=lambda c: _lexical_overlap(doc_tokens, c.doc.text), reverse=True)
    return with_pdf[:limit]


def _enrich_fulltext(doc_text: str, cands: List[Candidate], *, fetcher, limit: int,
                     warnings: List[str]) -> int:
    """Replace abstracts with fetched full text where an OA PDF is available. Returns count upgraded."""
    chosen = _rank_for_fulltext(doc_text, cands, limit)
    if not chosen:
        return 0

    def _fetch(c: Candidate):
        for url in c.pdf_urls[:2]:      # at most two link attempts per candidate
            got = fetcher.fetch(url)
            if got is not None:
                return c, got
        return c, None

    upgraded = 0
    with ThreadPoolExecutor(max_workers=min(4, len(chosen)), thread_name_prefix="prism-fulltext") as ex:
        for fut in as_completed([_submit_with_context(ex, _fetch, c) for c in chosen]):
            try:
                c, got = fut.result()
            except Exception as exc:  # pragma: no cover — fetcher is already defensive
                logger.warning("fulltext task failed: %s", str(exc)[:120])
                continue
            if got is not None:
                c.doc = dataclasses.replace(c.doc, text=got.text, kind="fulltext")
                upgraded += 1

    total_oa = sum(1 for c in cands if c.pdf_urls)
    if upgraded < total_oa:
        warnings.append(
            f"Full text was retrieved for {upgraded} of {total_oa} open-access candidates; the remaining academic "
            f"sources were compared against their abstracts only."
        )
    return upgraded


def search(
    doc_text: str,
    *,
    providers: Tuple[str, ...] = DEFAULT_PROVIDERS,
    max_queries: int = 8,
    per_query: int = 5,
    max_sources: int = 30,
    timeout: float = 10.0,
    contact_email: Optional[str] = None,
    s2_api_key: Optional[str] = None,
    fetcher=None,
    fulltext_max_docs: int = 8,
) -> Tuple[List[SourceDoc], List[str]]:
    """
    Retrieve candidate academic sources for a document from the enabled providers
    (run concurrently), then upgrade up to `fulltext_max_docs` of them to full text
    when `fetcher` (a services.fulltext.FullTextFetcher) is given. Returns
    (sources, warnings). Never raises.

    Privacy note (surfaced in the UI): up to `max_queries` short excerpts of the
    document (its longest sentences, truncated to ~18 words) are sent to the
    providers as search queries. Nothing else leaves the server. Full-text fetches
    download *public* PDFs from the providers' OA links; nothing of the user's is sent.
    """
    queries = build_queries(doc_text, max_queries=max_queries)
    if not queries:
        return [], ["Document too short to search academic databases."]

    enabled = [p for p in providers if p in _PROVIDERS]
    if not enabled:
        return [], []

    ctx = ProviderContext(queries=queries, per_query=per_query, timeout=timeout, max_sources=max_sources,
                          contact_email=contact_email, s2_api_key=s2_api_key)
    collected: List[Candidate] = []
    warnings: List[str] = []

    with ThreadPoolExecutor(max_workers=len(enabled), thread_name_prefix="prism-corpus") as ex:
        futures = {_submit_with_context(ex, _PROVIDERS[p], ctx): p for p in enabled}
        for fut in as_completed(futures):
            provider = futures[fut]
            try:
                cands, warns = fut.result()
                collected.extend(cands)
                warnings.extend(warns)
            except Exception as e:
                logger.warning("[P.R.I.S.M.] %s search failed: %s", provider, str(e)[:120])
                warnings.append(f"{provider.capitalize()} search failed — skipped.")

    # De-duplicate across providers: keep the longer abstract, union the PDF links.
    by_key: Dict[str, Candidate] = {}
    for c in collected:
        key = _dedup_key(c.doc)
        if not key:
            continue
        cur = by_key.get(key)
        if cur is None:
            by_key[key] = Candidate(doc=c.doc, pdf_urls=list(c.pdf_urls))
        else:
            if len(c.doc.text) > len(cur.doc.text):
                cur.doc = c.doc
            cur.pdf_urls.extend(u for u in c.pdf_urls if u not in cur.pdf_urls)

    final_cands = list(by_key.values())[:max_sources]

    upgraded = 0
    if fetcher is not None and final_cands and fulltext_max_docs > 0:
        upgraded = _enrich_fulltext(doc_text, final_cands, fetcher=fetcher, limit=fulltext_max_docs,
                                    warnings=warnings)

    final = [dataclasses.replace(c.doc, id=f"ac-{i}") for i, c in enumerate(final_cands)]

    if not final and not warnings:
        warnings.append("No candidate academic sources were found for this document.")

    logger.info("[P.R.I.S.M.] Academic corpus: %d sources from %s (%d queries; %d with full text).",
                len(final), enabled, len(queries), upgraded)
    return final, warnings
