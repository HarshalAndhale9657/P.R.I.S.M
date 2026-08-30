"""
P.R.I.S.M. — Plagiarism Matcher (Phase 1 core)
==============================================
Deterministic source-attribution matcher. Given a document and a set of
reference sources, it localizes:

  • VERBATIM / near-copy   — contiguous runs of identical words (case/punctuation
                             insensitive) found in a source, via k-gram anchoring
                             + greedy extension. Exact character spans on both sides.
  • PARAPHRASE             — sentence-level semantic similarity (local MiniLM
                             embeddings, cosine). Optional: degrades gracefully to
                             verbatim-only if the embedding model is unavailable.

Pure and self-contained (no FastAPI / spaCy dependency): the matcher takes plain
text in and returns JSON-serializable dicts out, so it is trivially unit-testable
and reused unchanged when we add the academic-DB corpus (Phase 2) and the
multilingual model (Phase 3).
"""

from __future__ import annotations

import re
import logging
import unicodedata
from bisect import bisect_left
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Optional language identification (for labelling cross-lingual / translated matches).
try:
    from langdetect import detect as _ld_detect, DetectorFactory as _LDFactory
    _LDFactory.seed = 0  # deterministic
    _LANGDETECT = True
except Exception:  # pragma: no cover
    _LANGDETECT = False

# A "word" token: unicode word chars plus internal apostrophes (don't / it's).
_WORD_RE = re.compile(r"\w+(?:['’]\w+)*", re.UNICODE)
# Coarse sentence splitter that preserves offsets (deterministic, language-agnostic).
_SENT_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|\n+|$)", re.UNICODE)


def _norm(word: str) -> str:
    """Case- and accent-folded form used only for matching (offsets stay original)."""
    return unicodedata.normalize("NFKD", word).casefold()


@dataclass(frozen=True)
class Token:
    norm: str
    start: int
    end: int


@dataclass(frozen=True)
class Unit:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class SourceDoc:
    id: str
    name: str
    text: str
    origin: str = "upload"          # "upload" | "openalex" | ...
    url: Optional[str] = None       # link to the source, when known


def tokenize(text: str) -> List[Token]:
    return [Token(_norm(m.group()), m.start(), m.end()) for m in _WORD_RE.finditer(text)]


class PlagiarismMatcher:
    """
    Configurable, deterministic matcher.

    Args:
        ngram: seed k-gram length for verbatim anchoring.
        min_verbatim_words: minimum contiguous words for a verbatim match to count.
        paraphrase_threshold: cosine cutoff for a paraphrase match (0..1).
        min_sentence_words: sentences shorter than this are not embedded.
        max_source_sentences: safety cap on embedded source sentences (warns, never silent).
    """

    def __init__(
        self,
        *,
        ngram: int = 5,
        min_verbatim_words: int = 8,
        paraphrase_threshold: float = 0.66,
        min_sentence_words: int = 6,
        max_source_sentences: int = 6000,
    ) -> None:
        if ngram < 1:
            raise ValueError("ngram must be >= 1")
        self.ngram = ngram
        self.min_verbatim_words = max(min_verbatim_words, ngram)
        self.paraphrase_threshold = paraphrase_threshold
        self.min_sentence_words = min_sentence_words
        self.max_source_sentences = max_source_sentences

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, doc_text: str, sources: Sequence[SourceDoc]) -> Dict[str, Any]:
        """Run verbatim + paraphrase matching and return a JSON-serializable report."""
        warnings: List[str] = []
        doc_text = doc_text or ""
        doc_tokens = tokenize(doc_text)
        total_words = len(doc_tokens)

        usable_sources = [s for s in sources if (s.text or "").strip()]
        if not doc_text.strip() or not usable_sources or total_words == 0:
            if not usable_sources:
                warnings.append("No readable reference sources were provided.")
            if total_words == 0:
                warnings.append("No readable text found in the document.")
            return self._empty_report(total_words, warnings, paraphrase_enabled=False)

        verbatim = self._verbatim_matches(doc_tokens, usable_sources)

        paraphrase_enabled = True
        try:
            paraphrase = self._paraphrase_matches(doc_text, usable_sources, verbatim, warnings)
        except _EmbeddingsUnavailable as exc:
            paraphrase_enabled = False
            paraphrase = []
            warnings.append(f"Paraphrase detection disabled: {exc} (verbatim matching still ran).")
        except Exception as exc:  # pragma: no cover — defensive
            paraphrase_enabled = False
            paraphrase = []
            logger.exception("Paraphrase matching failed")
            warnings.append(f"Paraphrase detection failed unexpectedly: {str(exc)[:160]}")

        matches = verbatim + paraphrase
        matches.sort(key=lambda m: (m["doc_start"], m["doc_end"]))
        for i, m in enumerate(matches):
            m["id"] = i
            m["doc_excerpt"] = doc_text[m["doc_start"]:m["doc_end"]]

        overall, per_source = self._aggregate(doc_tokens, matches, usable_sources)
        return {
            "overall": overall,
            "per_source": per_source,
            "matches": matches,
            "warnings": warnings,
            "paraphrase_enabled": paraphrase_enabled,
        }

    # ── Verbatim ──────────────────────────────────────────────────────────────

    def _verbatim_matches(
        self, doc_tokens: List[Token], sources: Sequence[SourceDoc]
    ) -> List[Dict[str, Any]]:
        doc_norm = [t.norm for t in doc_tokens]
        n = len(doc_norm)
        k = self.ngram

        # Combined k-gram index across all sources: k-gram -> [(src_idx, pos), ...]
        src_tokens: List[List[Token]] = []
        src_norm: List[List[str]] = []
        index: Dict[Tuple[str, ...], List[Tuple[int, int]]] = {}
        for s_idx, src in enumerate(sources):
            toks = tokenize(src.text)
            norms = [t.norm for t in toks]
            src_tokens.append(toks)
            src_norm.append(norms)
            for i in range(len(norms) - k + 1):
                index.setdefault(tuple(norms[i:i + k]), []).append((s_idx, i))

        matches: List[Dict[str, Any]] = []
        di = 0
        while di <= n - k:
            key = tuple(doc_norm[di:di + k])
            candidates = index.get(key)
            if not candidates:
                di += 1
                continue

            best_len = 0
            best_src = -1
            best_si = -1
            for s_idx, si in candidates:
                sn = src_norm[s_idx]
                length = k
                while (
                    di + length < n
                    and si + length < len(sn)
                    and doc_norm[di + length] == sn[si + length]
                ):
                    length += 1
                if length > best_len:
                    best_len, best_src, best_si = length, s_idx, si

            if best_len >= self.min_verbatim_words:
                src = sources[best_src]
                stoks = src_tokens[best_src]
                doc_start = doc_tokens[di].start
                doc_end = doc_tokens[di + best_len - 1].end
                src_start = stoks[best_si].start
                src_end = stoks[best_si + best_len - 1].end
                matches.append({
                    "match_type": "verbatim",
                    "similarity": 1.0,
                    "words": best_len,
                    "doc_start": doc_start,
                    "doc_end": doc_end,
                    "source_id": src.id,
                    "source_name": src.name,
                    "source_origin": src.origin,
                    "source_url": src.url,
                    "source_start": src_start,
                    "source_end": src_end,
                    "source_excerpt": src.text[src_start:src_end],
                    "source_context": self._context(src.text, src_start, src_end),
                })
                di += best_len  # greedy, non-overlapping in the document
            else:
                di += 1
        return matches

    # ── Paraphrase ────────────────────────────────────────────────────────────

    def _paraphrase_matches(
        self,
        doc_text: str,
        sources: Sequence[SourceDoc],
        verbatim: List[Dict[str, Any]],
        warnings: List[str],
    ) -> List[Dict[str, Any]]:
        doc_sents = self._sentences(doc_text)
        src_sents: List[Tuple[int, Unit]] = []
        for s_idx, src in enumerate(sources):
            for u in self._sentences(src.text):
                src_sents.append((s_idx, u))

        if not doc_sents or not src_sents:
            return []

        if len(src_sents) > self.max_source_sentences:
            warnings.append(
                f"Reference text is large; paraphrase search limited to the first "
                f"{self.max_source_sentences} of {len(src_sents)} source sentences."
            )
            src_sents = src_sents[: self.max_source_sentences]

        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        embedder = self._get_embedder()
        doc_emb = np.asarray(embedder.embed([u.text for u in doc_sents]))
        src_emb = np.asarray(embedder.embed([u.text for _, u in src_sents]))
        sims = cosine_similarity(doc_emb, src_emb)  # (D, S)

        verbatim_ranges = [(m["doc_start"], m["doc_end"]) for m in verbatim]
        matches: List[Dict[str, Any]] = []
        for di, dsent in enumerate(doc_sents):
            j = int(np.argmax(sims[di]))
            score = float(sims[di][j])
            if score < self.paraphrase_threshold:
                continue
            if self._overlap_ratio(dsent.start, dsent.end, verbatim_ranges) > 0.6:
                continue  # already reported as a verbatim copy
            s_idx, ssent = src_sents[j]
            src = sources[s_idx]
            doc_lang = self._detect_lang(dsent.text)
            src_lang = self._detect_lang(ssent.text)
            is_translated = bool(doc_lang and src_lang and doc_lang != src_lang)
            matches.append({
                "match_type": "translated" if is_translated else "paraphrase",
                "similarity": round(score, 4),
                "words": len(_WORD_RE.findall(dsent.text)),
                "doc_start": dsent.start,
                "doc_end": dsent.end,
                "doc_lang": doc_lang,
                "source_lang": src_lang,
                "source_id": src.id,
                "source_name": src.name,
                "source_origin": src.origin,
                "source_url": src.url,
                "source_start": ssent.start,
                "source_end": ssent.end,
                "source_excerpt": ssent.text,
                "source_context": self._context(src.text, ssent.start, ssent.end),
            })
        return matches

    def _get_embedder(self):
        try:
            from services.local_embeddings import get_instance
            embedder = get_instance()
            # Force model load now so ImportError/model errors surface here.
            embedder.embed(["warmup"])
            return embedder
        except ImportError as exc:
            raise _EmbeddingsUnavailable("sentence-transformers is not installed") from exc
        except Exception as exc:
            raise _EmbeddingsUnavailable(str(exc)[:160]) from exc

    # ── Sentence segmentation (offset-preserving) ─────────────────────────────

    def _sentences(self, text: str) -> List[Unit]:
        units: List[Unit] = []
        for m in _SENT_RE.finditer(text):
            seg = m.group()
            if not seg.strip():
                continue
            lstrip = len(seg) - len(seg.lstrip())
            start = m.start() + lstrip
            end = start + len(seg.strip())
            chunk = text[start:end]
            if len(_WORD_RE.findall(chunk)) >= self.min_sentence_words:
                units.append(Unit(chunk, start, end))
        return units

    # ── Aggregation ───────────────────────────────────────────────────────────

    def _aggregate(
        self,
        doc_tokens: List[Token],
        matches: List[Dict[str, Any]],
        sources: Sequence[SourceDoc],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        total = len(doc_tokens)
        starts = [t.start for t in doc_tokens]

        verbatim_tokens: set[int] = set()
        paraphrase_tokens: set[int] = set()
        translated_tokens: set[int] = set()
        per_source_tokens: Dict[str, set[int]] = {s.id: set() for s in sources}

        for m in matches:
            lo, hi = self._token_range(starts, m["doc_start"], m["doc_end"])
            idx = range(lo, hi)
            t = m["match_type"]
            if t == "verbatim":
                verbatim_tokens.update(idx)
            elif t == "translated":
                translated_tokens.update(idx)
            else:
                paraphrase_tokens.update(idx)
            per_source_tokens.setdefault(m["source_id"], set()).update(idx)

        # Verbatim takes precedence; paraphrase and translated are disjoint by match type.
        paraphrase_only = paraphrase_tokens - verbatim_tokens - translated_tokens
        translated_only = translated_tokens - verbatim_tokens
        matched = verbatim_tokens | paraphrase_tokens | translated_tokens

        def pct(x: int) -> float:
            return round(100.0 * x / total, 2) if total else 0.0

        overall = {
            "similarity_pct": pct(len(matched)),
            "verbatim_pct": pct(len(verbatim_tokens)),
            "paraphrase_pct": pct(len(paraphrase_only)),
            "translated_pct": pct(len(translated_only)),
            "matched_words": len(matched),
            "total_words": total,
            "match_count": len(matches),
            "source_count": len({m["source_id"] for m in matches}),
        }

        per_source = [
            {
                "id": s.id,
                "name": s.name,
                "origin": s.origin,
                "url": s.url,
                "matched_words": len(per_source_tokens.get(s.id, set())),
                "similarity_pct": pct(len(per_source_tokens.get(s.id, set()))),
            }
            for s in sources
        ]
        per_source.sort(key=lambda r: r["matched_words"], reverse=True)
        return overall, per_source

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _token_range(starts: List[int], a: int, b: int) -> Tuple[int, int]:
        """Indices of tokens whose start offset lies in [a, b)."""
        lo = bisect_left(starts, a)
        hi = bisect_left(starts, b)
        return lo, hi

    @staticmethod
    def _detect_lang(text: str) -> Optional[str]:
        """Best-effort language code (ISO 639-1) or None. Needs enough text to be reliable."""
        if not _LANGDETECT:
            return None
        t = (text or "").strip()
        if len(t) < 20:
            return None
        try:
            return _ld_detect(t)
        except Exception:
            return None

    @staticmethod
    def _overlap_ratio(a: int, b: int, ranges: List[Tuple[int, int]]) -> float:
        if b <= a:
            return 0.0
        covered = 0
        for ra, rb in ranges:
            covered += max(0, min(b, rb) - max(a, ra))
        return covered / (b - a)

    @staticmethod
    def _context(text: str, start: int, end: int, pad: int = 140) -> str:
        a = max(0, start - pad)
        b = min(len(text), end + pad)
        prefix = "…" if a > 0 else ""
        suffix = "…" if b < len(text) else ""
        return f"{prefix}{text[a:b]}{suffix}"

    @staticmethod
    def _empty_report(total_words: int, warnings: List[str], paraphrase_enabled: bool) -> Dict[str, Any]:
        return {
            "overall": {
                "similarity_pct": 0.0, "verbatim_pct": 0.0, "paraphrase_pct": 0.0, "translated_pct": 0.0,
                "matched_words": 0, "total_words": total_words,
                "match_count": 0, "source_count": 0,
            },
            "per_source": [],
            "matches": [],
            "warnings": warnings,
            "paraphrase_enabled": paraphrase_enabled,
        }


class _EmbeddingsUnavailable(RuntimeError):
    """Raised internally when the local embedding model cannot be used."""
