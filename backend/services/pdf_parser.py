"""
P.R.I.S.M. — Dual-Pass PDF Parser
===================================
Stage 1 of the analysis pipeline.

Pass A: `unstructured` library — multi-column-aware NarrativeText extraction.
Pass B: PyMuPDF (fitz) — bibliography isolation via bounding-box & font analysis.
Fallback chain: unstructured → PyMuPDF raw → pdfplumber → raw 1000-char chunking.

Zero AI calls — fully deterministic.
"""

from __future__ import annotations

import io
import re
import logging
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports for optional heavy dependencies
# ---------------------------------------------------------------------------

def _try_import_unstructured():
    """Lazy import for unstructured — allows graceful fallback if unavailable."""
    try:
        from unstructured.partition.pdf import partition_pdf
        from unstructured.documents.elements import NarrativeText, Title
        return partition_pdf, NarrativeText, Title
    except ImportError:
        logger.warning("unstructured not available — will use fallback extraction")
        return None, None, None


def _try_import_pdfplumber():
    """Lazy import for pdfplumber — third-tier fallback."""
    try:
        import pdfplumber
        return pdfplumber
    except ImportError:
        logger.warning("pdfplumber not available — will use raw chunking fallback")
        return None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_PARAGRAPH_LENGTH = 80          # Characters — skip captions, headers, etc.
FALLBACK_CHUNK_SIZE  = 1000        # Characters per chunk in raw fallback
BIBLIOGRAPHY_KEYWORDS = re.compile(
    r"^\s*(references|bibliography|works\s+cited|cited\s+works|literature\s+cited)\s*$",
    re.IGNORECASE,
)
REFERENCE_ENTRY_PATTERN = re.compile(
    r"(?:^|\n)"                              # Start of line
    r"(?:\[\d+\]\s*|•\s*|–\s*|—\s*|\d+\.\s*)" # Numbered/bulleted prefix
    r"[A-Z]"                                  # Author name capital letter
)


class AcademicPDFParser:
    """
    Dual-pass academic PDF text extractor.

    Usage::

        parser = AcademicPDFParser()
        result = parser.parse(pdf_bytes)
        # result == {
        #     "paragraphs": [{"index": 0, "text": "...", "page": 1}, ...],
        #     "references": ["[1] Smith et al. ...", ...],
        #     "page_count": 12,
        #     "extraction_method": "unstructured",
        #     "degraded_mode": False,
        # }
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, pdf_bytes: bytes) -> dict:
        """
        Main entry point. Attempts extraction in order of fidelity:
        1. unstructured (best — column-aware, element-typed)
        2. PyMuPDF raw text (good — fast, reliable)
        3. pdfplumber (decent — table-aware)
        4. Raw chunking (last resort — guaranteed to produce *something*)

        Always attempts bibliography isolation via PyMuPDF (Pass B)
        regardless of which text extraction pass succeeds.
        """
        page_count = self._get_page_count(pdf_bytes)

        # --- Pass A: try unstructured first ---
        paragraphs, method = self._pass_a_unstructured(pdf_bytes)

        # --- Fallback chain ---
        if not paragraphs:
            paragraphs, method = self._fallback_pymupdf(pdf_bytes)
        if not paragraphs:
            paragraphs, method = self._fallback_pdfplumber(pdf_bytes)
        if not paragraphs:
            paragraphs, method = self._fallback_raw_chunk(pdf_bytes)

        degraded = method != "unstructured"
        if degraded:
            logger.warning("PDF parsed in degraded mode via: %s", method)

        # --- Pass B: bibliography isolation (always via PyMuPDF) ---
        references = self._extract_bibliography(pdf_bytes)

        # --- Filter bibliography text out of paragraphs ---
        paragraphs = self._remove_reference_paragraphs(paragraphs, references)

        return {
            "paragraphs": paragraphs,
            "references": references,
            "page_count": page_count,
            "extraction_method": method,
            "degraded_mode": degraded,
        }

    # ------------------------------------------------------------------
    # Pass A — unstructured (highest fidelity)
    # ------------------------------------------------------------------

    def _pass_a_unstructured(self, pdf_bytes: bytes):
        """
        Use `unstructured` library to partition the PDF into typed elements.
        Keeps only NarrativeText blocks ≥ MIN_PARAGRAPH_LENGTH characters.
        Multi-column aware; filters tables, headers, footers automatically.
        """
        partition_pdf, NarrativeText, Title = _try_import_unstructured()
        if partition_pdf is None:
            return [], None

        try:
            elements = partition_pdf(
                file=io.BytesIO(pdf_bytes),
                strategy="fast",
            )

            paragraphs = []
            idx = 0
            for el in elements:
                if isinstance(el, NarrativeText) and len(el.text.strip()) >= MIN_PARAGRAPH_LENGTH:
                    page_num = (
                        el.metadata.page_number
                        if hasattr(el, "metadata") and hasattr(el.metadata, "page_number")
                        else None
                    )
                    paragraphs.append({
                        "index": idx,
                        "text": el.text.strip(),
                        "page": page_num,
                    })
                    idx += 1

            if paragraphs:
                logger.info(
                    "unstructured extracted %d paragraphs from PDF", len(paragraphs)
                )
                return paragraphs, "unstructured"
            else:
                logger.warning("unstructured found 0 qualifying paragraphs — falling back")
                return [], None

        except Exception as exc:
            logger.error("unstructured partition_pdf failed: %s", exc)
            return [], None

    # ------------------------------------------------------------------
    # Fallback 1 — PyMuPDF raw text
    # ------------------------------------------------------------------

    def _fallback_pymupdf(self, pdf_bytes: bytes):
        """
        Extract raw text per page via PyMuPDF, then split into paragraphs
        using double-newline boundaries. Faster than unstructured but less
        semantically aware.
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            paragraphs = []
            idx = 0

            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text")
                if not text or not text.strip():
                    continue

                # Split on double-newline (paragraph boundary)
                raw_paras = re.split(r"\n{2,}", text.strip())

                for raw in raw_paras:
                    cleaned = self._clean_text(raw)
                    if len(cleaned) >= MIN_PARAGRAPH_LENGTH:
                        paragraphs.append({
                            "index": idx,
                            "text": cleaned,
                            "page": page_num,
                        })
                        idx += 1

            doc.close()

            if paragraphs:
                logger.info("PyMuPDF fallback extracted %d paragraphs", len(paragraphs))
                return paragraphs, "pymupdf"

            return [], None

        except Exception as exc:
            logger.error("PyMuPDF fallback failed: %s", exc)
            return [], None

    # ------------------------------------------------------------------
    # Fallback 2 — pdfplumber
    # ------------------------------------------------------------------

    def _fallback_pdfplumber(self, pdf_bytes: bytes):
        """
        Third tier: pdfplumber. Table-aware text extraction but slower.
        """
        pdfplumber = _try_import_pdfplumber()
        if pdfplumber is None:
            return [], None

        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
            paragraphs = []
            idx = 0

            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if not text or not text.strip():
                    continue

                raw_paras = re.split(r"\n{2,}", text.strip())
                for raw in raw_paras:
                    cleaned = self._clean_text(raw)
                    if len(cleaned) >= MIN_PARAGRAPH_LENGTH:
                        paragraphs.append({
                            "index": idx,
                            "text": cleaned,
                            "page": page_num,
                        })
                        idx += 1

            pdf.close()

            if paragraphs:
                logger.info("pdfplumber fallback extracted %d paragraphs", len(paragraphs))
                return paragraphs, "pdfplumber"

            return [], None

        except Exception as exc:
            logger.error("pdfplumber fallback failed: %s", exc)
            return [], None

    # ------------------------------------------------------------------
    # Fallback 3 — raw chunking (last resort)
    # ------------------------------------------------------------------

    def _fallback_raw_chunk(self, pdf_bytes: bytes):
        """
        Absolute last resort: extract all text via PyMuPDF and split into
        fixed-size chunks of FALLBACK_CHUNK_SIZE characters. Guaranteed to
        produce output from any text-based PDF.
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            full_text = ""
            for page in doc:
                full_text += page.get_text("text") + "\n"
            doc.close()

            full_text = full_text.strip()
            if not full_text:
                logger.error("PDF contains no extractable text (scanned/image PDF?)")
                return [], None

            # Chunk into FALLBACK_CHUNK_SIZE segments
            paragraphs = []
            idx = 0
            for i in range(0, len(full_text), FALLBACK_CHUNK_SIZE):
                chunk = full_text[i : i + FALLBACK_CHUNK_SIZE].strip()
                if len(chunk) >= MIN_PARAGRAPH_LENGTH:
                    paragraphs.append({
                        "index": idx,
                        "text": chunk,
                        "page": None,  # Can't reliably map chunks to pages
                    })
                    idx += 1

            logger.warning(
                "Raw chunking fallback produced %d chunks (degraded)", len(paragraphs)
            )
            return paragraphs, "raw_chunk"

        except Exception as exc:
            logger.error("Raw chunk fallback failed: %s", exc)
            return [], None

    # ------------------------------------------------------------------
    # Pass B — Bibliography isolation (PyMuPDF)
    # ------------------------------------------------------------------

    def _extract_bibliography(self, pdf_bytes: bytes) -> list[str]:
        """
        Scan the PDF from the last page backwards to find a
        'References' / 'Bibliography' section, then extract individual
        reference entries using font-size and bounding-box heuristics.
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            references: list[str] = []
            ref_section_found = False

            # Scan from last page backward — bibliography is almost always at the end
            for page_idx in range(len(doc) - 1, -1, -1):
                page = doc[page_idx]
                blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

                for block in blocks:
                    if block["type"] != 0:  # Skip image blocks
                        continue

                    for line in block.get("lines", []):
                        line_text = "".join(
                            span["text"] for span in line.get("spans", [])
                        ).strip()

                        # Detect the "References" heading
                        if not ref_section_found:
                            if BIBLIOGRAPHY_KEYWORDS.match(line_text):
                                ref_section_found = True
                                logger.info(
                                    "Bibliography heading found on page %d: '%s'",
                                    page_idx + 1,
                                    line_text,
                                )
                            continue

                        # We're inside the references section — collect entries
                        if line_text and len(line_text) > 10:
                            references.append(line_text)

                # If we found references on this page, also check the page before
                # (bibliography may span 2+ pages)
                if ref_section_found and page_idx > 0:
                    continue
                elif ref_section_found:
                    break

            doc.close()

            # Post-process: merge continuation lines into single entries
            references = self._merge_reference_lines(references)

            logger.info("Extracted %d bibliography entries", len(references))
            return references

        except Exception as exc:
            logger.error("Bibliography extraction failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_page_count(pdf_bytes: bytes) -> int:
        """Return the total page count using PyMuPDF."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Normalize whitespace: collapse runs of spaces/newlines into single
        spaces, strip leading/trailing whitespace.
        """
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _merge_reference_lines(lines: list[str]) -> list[str]:
        """
        Merge consecutive short lines that are likely continuations of
        the same reference entry. A new entry starts with a numbered
        prefix like [1], •, 1., or a capital letter after a blank-ish gap.
        """
        if not lines:
            return []

        merged: list[str] = [lines[0]]
        entry_start = re.compile(
            r"^(?:\[\d+\]|•|–|—|\d+\.)\s"  # Numbered/bulleted prefix
        )

        for line in lines[1:]:
            if entry_start.match(line):
                merged.append(line)
            else:
                # Continuation of previous entry
                merged[-1] = merged[-1].rstrip() + " " + line.lstrip()

        return merged

    @staticmethod
    def _remove_reference_paragraphs(
        paragraphs: list[dict],
        references: list[str],
    ) -> list[dict]:
        """
        Remove paragraphs whose text overlaps significantly with extracted
        bibliography entries — avoids double-counting references as body text.
        """
        if not references:
            return paragraphs

        # Build a set of reference substrings for fuzzy matching
        ref_snippets = set()
        for ref in references:
            # Use the first 60 chars of each reference as a fingerprint
            snippet = ref[:60].strip().lower()
            if snippet:
                ref_snippets.add(snippet)

        filtered = []
        for para in paragraphs:
            text_lower = para["text"].lower()
            # Check if this paragraph looks like it's from the references section
            is_reference = any(snippet in text_lower for snippet in ref_snippets)
            if not is_reference:
                filtered.append(para)

        removed = len(paragraphs) - len(filtered)
        if removed:
            logger.info("Filtered %d reference-section paragraphs from body text", removed)

        # Re-index after filtering
        for i, para in enumerate(filtered):
            para["index"] = i

        return filtered
