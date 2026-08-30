"""
P.R.I.S.M. — Academic Corpus Retrieval (Phase 2)
================================================
Fetches candidate source documents from open-access academic databases so a paper
can be checked without the user supplying references. Providers run concurrently and
their (abstract-bearing) results are merged + de-duplicated, then fed unchanged into
the PlagiarismMatcher.

Providers:
  • OpenAlex — free, no key; abstracts via an inverted index; broad coverage.
  • arXiv    — free; full abstracts (summaries); strong for CS / physics / ML.

Crossref was evaluated and intentionally NOT used as a content corpus: its records
rarely carry abstracts (publishers seldom deposit them), so it yields almost no text
to match against. It remains a good metadata/verification source for a future feature.

Everything is defensive: any provider/network failure degrades to a warning and the
other providers still contribute; it never raises into the caller.
"""

from __future__ import annotations

import re
import logging
import dataclasses
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

import requests

from services.plagiarism_matcher import SourceDoc

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "PRISM-OriginalityChecker/0.1 (mailto:prism@example.org)"}
_WORD_RE = re.compile(r"\w+(?:['’]\w+)*", re.UNICODE)
_MIN_ABSTRACT = 60  # need enough text to match against

DEFAULT_PROVIDERS = ("openalex", "arxiv")

# ── OpenAlex ──────────────────────────────────────────────────────────────────
_OPENALEX_URL = "https://api.openalex.org/works"
_OPENALEX_SELECT = "id,display_name,publication_year,abstract_inverted_index,primary_location"


def _abstract_from_inverted(inv: Optional[dict]) -> str:
    if not inv:
        return ""
    positions: List[Tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort(key=lambda t: t[0])
    return " ".join(w for _, w in positions)


def _search_openalex(queries, per_query, timeout, max_sources):
    sources, warnings, failures = [], [], 0
    for query in queries:
        if len(sources) >= max_sources:
            break
        try:
            resp = requests.get(
                _OPENALEX_URL,
                params={"search": query, "per-page": per_query, "select": _OPENALEX_SELECT},
                headers=_HEADERS, timeout=timeout,
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
                sources.append(_mk("openalex", title, year, abstract, url))
        except requests.RequestException as e:
            failures += 1
            logger.warning("[P.R.I.S.M.] OpenAlex query failed: %s", str(e)[:120])
    if failures and not sources:
        warnings.append("Could not reach OpenAlex — that source was skipped.")
    return sources, warnings


# ── arXiv ─────────────────────────────────────────────────────────────────────
_ARXIV_MAX_QUERIES = 4  # arXiv is slower per call; cap the number of searches


def _search_arxiv(queries, per_query, timeout, max_sources):
    sources, warnings = [], []
    try:
        import arxiv
    except Exception:
        return sources, ["arXiv client unavailable — that source was skipped."]

    client = arxiv.Client(page_size=per_query, delay_seconds=0.0, num_retries=2)
    failures = 0
    for query in queries[:_ARXIV_MAX_QUERIES]:
        if len(sources) >= max_sources:
            break
        try:
            search = arxiv.Search(
                query=query, max_results=per_query,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            for res in client.results(search):
                abstract = (res.summary or "").strip().replace("\n", " ")
                if len(abstract) < _MIN_ABSTRACT:
                    continue
                title = (res.title or "Untitled").strip()
                year = res.published.year if getattr(res, "published", None) else None
                url = getattr(res, "entry_id", None)
                sources.append(_mk("arxiv", title, year, abstract, url))
        except Exception as e:
            failures += 1
            logger.warning("[P.R.I.S.M.] arXiv query failed: %s", str(e)[:120])
    if failures and not sources:
        warnings.append("Could not reach arXiv — that source was skipped.")
    return sources, warnings


_PROVIDERS = {"openalex": _search_openalex, "arxiv": _search_arxiv}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _mk(origin: str, title: str, year, abstract: str, url) -> SourceDoc:
    name = f"{title}" + (f" ({year})" if year else "")
    return SourceDoc(id="", name=name, text=f"{title}. {abstract}", origin=origin, url=url)


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


def search(
    doc_text: str,
    *,
    providers: Tuple[str, ...] = DEFAULT_PROVIDERS,
    max_queries: int = 8,
    per_query: int = 5,
    max_sources: int = 30,
    timeout: float = 10.0,
) -> Tuple[List[SourceDoc], List[str]]:
    """
    Retrieve candidate academic sources for a document from the enabled providers
    (run concurrently). Returns (sources, warnings). Never raises.
    """
    queries = build_queries(doc_text, max_queries=max_queries)
    if not queries:
        return [], ["Document too short to search academic databases."]

    enabled = [p for p in providers if p in _PROVIDERS]
    if not enabled:
        return [], []

    collected: List[SourceDoc] = []
    warnings: List[str] = []

    with ThreadPoolExecutor(max_workers=len(enabled), thread_name_prefix="prism-corpus") as ex:
        futures = {
            ex.submit(_PROVIDERS[p], queries, per_query, timeout, max_sources): p
            for p in enabled
        }
        for fut in as_completed(futures):
            provider = futures[fut]
            try:
                srcs, warns = fut.result()
                collected.extend(srcs)
                warnings.extend(warns)
            except Exception as e:
                logger.warning("[P.R.I.S.M.] %s search failed: %s", provider, str(e)[:120])
                warnings.append(f"{provider.capitalize()} search failed — skipped.")

    # De-duplicate across providers (prefer the longer abstract), then cap + re-id.
    by_key: dict[str, SourceDoc] = {}
    for s in collected:
        key = _dedup_key(s)
        if not key:
            continue
        if key not in by_key or len(s.text) > len(by_key[key].text):
            by_key[key] = s

    final = [
        dataclasses.replace(s, id=f"ac-{i}")
        for i, s in enumerate(list(by_key.values())[:max_sources])
    ]

    if not final and not warnings:
        warnings.append("No candidate academic sources were found for this document.")

    logger.info("[P.R.I.S.M.] Academic corpus: %d sources from %s (%d queries).",
                len(final), enabled, len(queries))
    return final, warnings
