"""
P.R.I.S.M. — Document parser (checker-specific)
================================================
Turns an uploaded PDF or plain-text file into one offset-preserving text blob
plus paragraph anchors ``{index, page, start, end, text}`` that the matcher and
the UI both rely on.

Why a purpose-built parser (ADR-0019): the legacy stylometry parser dropped
every paragraph under 80 characters and always ran its heuristics for
*authorship*. For a plagiarism checker, a dropped paragraph is a passage that
is never checked. This parser keeps every block with real words, removes only
what would create false positives (repeated running headers/footers, page
numbers) or is out of scope (the reference list, which is excluded and
*reported* rather than silently deleted), and enforces hard limits so a
hostile PDF cannot exhaust the box.

Pure: bytes in, dataclass out, no framework imports.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pymupdf

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"\w+(?:['’]\w+)*", re.UNICODE)
_BIB_HEADING_RE = re.compile(
    r"^\s*(?:\d+\.?\s*)?(references?|bibliography|works\s+cited|cited\s+works|literature\s+cited)\s*[:.]?\s*$",
    re.IGNORECASE,
)
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:page\s*)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?\s*$", re.IGNORECASE)
_MIN_WORDS_PER_BLOCK = 3
_PDF_MAGIC = b"%PDF"
_PARAGRAPH_SEP = "\n\n"


class ParseLimitExceeded(ValueError):
    """The upload is valid but exceeds a configured size/page limit. Message is user-safe."""


@dataclass
class ParsedDocument:
    text: str
    paragraphs: List[Dict] = field(default_factory=list)   # {index, page, start, end, text}
    page_count: Optional[int] = None
    method: str = "text"                                      # "text" | "pdf"
    warnings: List[str] = field(default_factory=list)
    excluded_reference_paragraphs: int = 0

    @property
    def word_count(self) -> int:
        return len(_WORD_RE.findall(self.text))


def parse_document(
    name: str,
    data: bytes,
    *,
    max_pdf_pages: int = 300,
    max_chars: int = 2_000_000,
) -> ParsedDocument:
    """Parse PDF or text bytes. Never raises for *content* problems (returns an empty
    document with a warning); raises ParseLimitExceeded for oversize inputs."""
    if _looks_like_pdf(name, data):
        blocks, page_count, warnings = _pdf_blocks(data, max_pdf_pages=max_pdf_pages)
        method = "pdf"
    else:
        blocks = _plaintext_blocks(data)
        page_count, warnings, method = None, [], "text"

    blocks, excluded = _exclude_reference_list(blocks)
    if excluded:
        warnings.append(
            f"The reference list ({excluded} entr{'y' if excluded == 1 else 'ies'}) was excluded from matching — "
            f"bibliographies legitimately repeat across papers."
        )

    text, paragraphs = _assemble(blocks)
    if len(text) > max_chars:
        raise ParseLimitExceeded(
            f"'{name}' has {len(text):,} characters of text; the limit is {max_chars:,} per document."
        )
    return ParsedDocument(text=text, paragraphs=paragraphs, page_count=page_count, method=method,
                          warnings=warnings, excluded_reference_paragraphs=excluded)


# ── Detection ────────────────────────────────────────────────────────────────

def _looks_like_pdf(name: str, data: bytes) -> bool:
    lower = (name or "").lower()
    # A .pdf extension is honoured even without the magic bytes so PyMuPDF reports the
    # corruption instead of us guessing it is text.
    return data[:4] == _PDF_MAGIC or lower.endswith(".pdf")


# ── Plain text ───────────────────────────────────────────────────────────────

def _plaintext_blocks(data: bytes) -> List[Tuple[Optional[int], str]]:
    raw = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return [(None, _unwrap(chunk.strip())) for chunk in re.split(r"\n\s*\n", raw) if chunk.strip()]


# A hard-wrapped line: it does not finish a sentence, and the next line continues it in
# lower case. Markdown/plain-text manuscripts are routinely wrapped at 72-80 columns.
_HARD_WRAP_RE = re.compile(r"(?<![.!?:;])\n(?=[a-z0-9(])", re.UNICODE)
_WRAP_HYPHEN_RE = re.compile(r"(\w)-\n(\w)", re.UNICODE)


def _unwrap(text: str) -> str:
    """Undo hard line wrapping in plain text, but keep deliberate line structure.

    Without this the matcher splits at every wrapped line, because a newline ends a
    sentence (`plagiarism_matcher.split_sentences`). A 60-column paragraph then reaches
    the encoder as five fragments instead of two sentences, and any fragment under
    `min_sentence_words` is **dropped entirely** — the same failure ADR-0026 fixed on the
    punctuation side, arriving through the layout door on the text-input path only (PDFs
    go through `_clean_block`, which already collapses line breaks).

    A line break is only joined when the previous line does not finish a sentence *and*
    the next begins lower-case: that is what wrapping looks like. Headings, list items and
    anything starting with a capital keep their break, so a bulleted list is still a list.
    """
    text = _WRAP_HYPHEN_RE.sub(r"\1\2", text)          # "informa-\ntion" -> "information"
    return _HARD_WRAP_RE.sub(" ", text)


# ── PDF ──────────────────────────────────────────────────────────────────────

def _pdf_blocks(data: bytes, *, max_pdf_pages: int) -> Tuple[List[Tuple[Optional[int], str]], int, List[str]]:
    warnings: List[str] = []
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # corrupt / not actually a PDF
        logger.info("PDF open failed: %s", str(exc)[:120])
        return [], 0, ["The file could not be opened as a PDF (it may be corrupt or mislabelled)."]

    try:
        page_count = doc.page_count
        if page_count > max_pdf_pages:
            raise ParseLimitExceeded(f"The PDF has {page_count} pages; the limit is {max_pdf_pages}.")
        if doc.is_encrypted and not doc.authenticate(""):
            return [], page_count, ["The PDF is password-protected and could not be read."]

        per_page: List[List[str]] = []
        for page in doc:
            blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
            texts = []
            for b in sorted(blocks, key=lambda b: (round(b[1], 1), round(b[0], 1))):
                if len(b) >= 7 and b[6] != 0:      # image block
                    continue
                cleaned = _clean_block(b[4])
                if not cleaned:
                    continue
                # Keep tiny blocks only when they are a section heading we key on later
                # ("References"), otherwise they are stray labels/numbers.
                if len(_WORD_RE.findall(cleaned)) >= _MIN_WORDS_PER_BLOCK or _BIB_HEADING_RE.match(cleaned):
                    texts.append(cleaned)
            per_page.append(texts)
    finally:
        doc.close()

    boilerplate = _repeated_boilerplate(per_page)
    out: List[Tuple[Optional[int], str]] = []
    for pno, texts in enumerate(per_page, start=1):
        for t in texts:
            key = _norm_key(t)
            if key in boilerplate or _PAGE_NUMBER_RE.match(t):
                continue
            out.append((pno, t))

    if not out:
        warnings.append("No text could be extracted from this PDF. It may be scanned or image-only "
                        "(OCR is not supported yet).")
    return out, page_count, warnings


def _clean_block(text: str) -> str:
    # Re-join words hyphenated across line breaks, then collapse remaining line breaks into spaces.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"[ \t ]+", " ", text)
    return text.strip()


def _norm_key(text: str) -> str:
    return re.sub(r"\d+", "#", text.casefold())[:120]


def _repeated_boilerplate(per_page: List[List[str]]) -> set:
    """Blocks that recur on many pages are running headers/footers, not prose."""
    n_pages = len(per_page)
    if n_pages < 3:
        return set()
    counts: Counter = Counter()
    for texts in per_page:
        for key in {_norm_key(t) for t in texts if len(t) <= 160}:
            counts[key] += 1
    threshold = max(3, int(0.5 * n_pages))
    return {k for k, c in counts.items() if c >= threshold}


# ── Reference list ───────────────────────────────────────────────────────────

def _exclude_reference_list(blocks: List[Tuple[Optional[int], str]]) -> Tuple[List[Tuple[Optional[int], str]], int]:
    """Drop everything from the *last* bibliography heading onward, if that heading sits
    in the final 40% of the document (a 'References' heading in a table of contents is ignored)."""
    if len(blocks) < 5:
        return blocks, 0
    idx = None
    for i, (_, t) in enumerate(blocks):
        if len(t) <= 40 and _BIB_HEADING_RE.match(t):
            idx = i
    if idx is None or idx < 0.6 * len(blocks):
        return blocks, 0
    return blocks[:idx], len(blocks) - idx - 1


# ── Assembly ─────────────────────────────────────────────────────────────────

def _assemble(blocks: List[Tuple[Optional[int], str]]) -> Tuple[str, List[Dict]]:
    parts: List[str] = []
    paragraphs: List[Dict] = []
    pos = 0
    for i, (page, text) in enumerate(blocks):
        start = pos
        parts.append(text)
        pos += len(text)
        paragraphs.append({"index": i, "page": page, "start": start, "end": pos, "text": text})
        parts.append(_PARAGRAPH_SEP)
        pos += len(_PARAGRAPH_SEP)
    return "".join(parts), paragraphs
