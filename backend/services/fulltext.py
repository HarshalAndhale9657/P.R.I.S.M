"""
P.R.I.S.M. — Open-access full-text fetcher (W4b, ADR-0021)
==========================================================
Abstract-level matching can only ever find paraphrase-shaped overlap. When a
retrieved candidate carries an open-access PDF link (arXiv, OpenAlex's
`best_oa_location`, Semantic Scholar's `openAccessPdf`), download it and match
against the *full text* — that is what makes verbatim detection against
academic sources possible.

Every download is treated as hostile input:
  * http(s) only; loopback / private / link-local hosts refused (the URL came from
    a third-party API, but we still never fetch inside our own network);
  * streamed with a hard byte cap — a 2 GB "PDF" is abandoned, not buffered;
  * the first bytes must be `%PDF`, whatever the server's Content-Type says;
  * parsed by our own parser under its page/char caps;
  * results (including failures) are cached for a while so a popular paper is
    fetched once, and a dead link is not retried on every check.

Pure service: no FastAPI, no settings import — everything is a constructor argument.
"""
from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests

from services.document_parser import ParseLimitExceeded, parse_document
from utils.ttl_cache import TTLCache

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF"
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}
_CHUNK = 64 * 1024


@dataclass(frozen=True)
class FetchedText:
    url: str
    text: str
    page_count: Optional[int]
    byte_size: int


class _Miss:
    """Cached negative result (distinct from 'not cached')."""


_MISS = _Miss()


def url_is_fetchable(url: str) -> bool:
    """Public http(s) URL with a hostname that is not loopback/private/link-local."""
    try:
        u = urlparse(url)
    except Exception:
        return False
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    host = u.hostname.lower()
    if host in _BLOCKED_HOSTS or host.endswith((".local", ".internal")):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # a DNS name; resolution happens at request time
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified)


class FullTextFetcher:
    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 15.0,
        max_bytes: int = 15 * 1024 * 1024,
        max_pdf_pages: int = 300,
        max_chars: int = 2_000_000,
        user_agent: str = "PRISM-OriginalityChecker/0.9",
        cache_ttl_seconds: int = 3600,
        cache_size: int = 256,
    ) -> None:
        self._session = session or requests.Session()
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_pdf_pages = max_pdf_pages
        self.max_chars = max_chars
        self.user_agent = user_agent
        self._cache: TTLCache[str, object] = TTLCache(max_size=cache_size, ttl_seconds=cache_ttl_seconds)

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch(self, url: str) -> Optional[FetchedText]:
        """Return parsed full text for an OA PDF URL, or None if it cannot be had safely."""
        if not url_is_fetchable(url):
            return None
        cached = self._cache.get(url)
        if cached is not None:
            return None if cached is _MISS else cached  # type: ignore[return-value]

        result = self._download_and_parse(url)
        self._cache.put(url, result if result is not None else _MISS)
        return result

    # ── Internals ─────────────────────────────────────────────────────────────

    def _download_and_parse(self, url: str) -> Optional[FetchedText]:
        try:
            with self._session.get(
                url, stream=True, allow_redirects=True, timeout=(5.0, self.timeout),
                headers={"User-Agent": self.user_agent, "Accept": "application/pdf,*/*;q=0.5"},
            ) as resp:
                if resp.status_code != 200:
                    logger.info("fulltext: %s -> HTTP %s", url, resp.status_code)
                    return None
                if not url_is_fetchable(resp.url):  # redirected somewhere we refuse
                    return None
                declared = resp.headers.get("Content-Length")
                if declared and declared.isdigit() and int(declared) > self.max_bytes:
                    logger.info("fulltext: %s declared %s bytes > cap", url, declared)
                    return None
                buf = bytearray()
                for chunk in resp.iter_content(chunk_size=_CHUNK):
                    if not chunk:
                        continue
                    if not buf and chunk.lstrip()[:4] != _PDF_MAGIC:
                        logger.info("fulltext: %s is not a PDF (first bytes %r)", url, bytes(chunk[:8]))
                        return None
                    buf.extend(chunk)
                    if len(buf) > self.max_bytes:
                        logger.info("fulltext: %s exceeded %d bytes; abandoned", url, self.max_bytes)
                        return None
        except requests.RequestException as exc:
            logger.info("fulltext: %s failed: %s", url, str(exc)[:120])
            return None

        if not buf:
            return None
        try:
            parsed = parse_document("oa.pdf", bytes(buf), max_pdf_pages=self.max_pdf_pages, max_chars=self.max_chars)
        except ParseLimitExceeded as exc:
            logger.info("fulltext: %s rejected by parser: %s", url, exc)
            return None
        if not parsed.text.strip():
            return None
        return FetchedText(url=url, text=parsed.text, page_count=parsed.page_count, byte_size=len(buf))
