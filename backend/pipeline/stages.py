"""
P.R.I.S.M. — Pipeline stage implementations
===========================================
Live stages: ParseStage, RetrieveStage, MatchStage, RerankStage (opt-in), LocalizeStage, TriageStage.
CoachStage (W9, ADR-0031) phrases the fix after triage. The submission-risk report and the
before/after re-check (W10, ADR-0032) are assembled by the runner from the finished result,
not by a stage — they need the coverage statement and the previous job, which only the
runner has.

Dependencies (matcher, academic-search fn) are INJECTED, never imported from the
app layer, so there is no circular import and tests substitute fakes freely.
"""
from __future__ import annotations

import logging
from bisect import bisect_right
from typing import Callable, List, Protocol, Sequence, Tuple

from services.document_parser import ParseLimitExceeded, parse_document

from .base import CheckContext, Document, PipelineError, SourceDoc

logger = logging.getLogger(__name__)


# ── Structural typing for the injected collaborators ─────────────────────────
class Matcher(Protocol):
    def check(self, doc_text: str, sources: Sequence[SourceDoc]) -> dict: ...


# search(doc_text) -> (sources, warnings)   (matches services.academic_corpus.search)
SearchFn = Callable[[str], Tuple[List[SourceDoc], List[str]]]


# ── Parse ─────────────────────────────────────────────────────────────────────
class ParseStage:
    """Turn raw uploads into `ctx.document` and uploaded `ctx.sources`.

    Raises PipelineError (user-safe) when the manuscript has no readable text or
    exceeds a size limit. A reference that cannot be read is *skipped with a
    warning*, never fatal — one bad PDF should not sink the whole check.
    """
    name = "parse"

    def __init__(self, *, max_pdf_pages: int = 300, max_chars: int = 2_000_000) -> None:
        self.max_pdf_pages = max_pdf_pages
        self.max_chars = max_chars

    def run(self, ctx: CheckContext) -> CheckContext:
        if ctx.document is None:
            if ctx.raw_document is None:
                raise PipelineError("No document was provided.")
            try:
                parsed = parse_document(ctx.raw_document.name, ctx.raw_document.data,
                                        max_pdf_pages=self.max_pdf_pages, max_chars=self.max_chars)
            except ParseLimitExceeded as exc:
                raise PipelineError(str(exc)) from exc
            ctx.extend_warnings(parsed.warnings)
            if not parsed.text.strip():
                raise PipelineError(
                    "No readable text found in the document (it may be scanned or image-only)."
                )
            ctx.document = Document(name=ctx.raw_document.name, text=parsed.text,
                                    paragraphs=parsed.paragraphs, page_count=parsed.page_count)

        for i, raw in enumerate(ctx.raw_sources):
            try:
                parsed = parse_document(raw.name, raw.data,
                                        max_pdf_pages=self.max_pdf_pages, max_chars=self.max_chars)
            except ParseLimitExceeded as exc:
                ctx.warn(f"Skipped '{raw.name}': {exc}")
                continue
            if parsed.text.strip():
                ctx.sources.append(SourceDoc(id=f"src-{i}", name=raw.name, text=parsed.text))
            else:
                ctx.warn(f"Skipped '{raw.name}': no readable text extracted.")
        ctx.raw_sources = []  # parsed; drop the bytes so the context is lighter downstream
        return ctx


# ── Retrieve ──────────────────────────────────────────────────────────────────
class RetrieveStage:
    """Gather candidate academic sources (opt-in) and append them to the context.

    Never raises: retrieval failure degrades to a warning. After this stage, if
    there are still no sources at all, that is a user-safe error.
    """
    name = "retrieve"

    def __init__(self, search_fn: SearchFn, *, use_academic: bool) -> None:
        self._search = search_fn
        self._use_academic = use_academic

    def run(self, ctx: CheckContext) -> CheckContext:
        ctx.artifacts.setdefault("academic_used", False)
        if self._use_academic:
            try:
                acad_sources, acad_warnings = self._search(ctx.require_document().text)
                ctx.sources.extend(acad_sources)
                ctx.extend_warnings(acad_warnings)
                ctx.artifacts["academic_used"] = len(acad_sources) > 0
            except Exception:
                logger.exception("[pipeline.retrieve] academic search failed")
                ctx.warn("Academic-database search failed unexpectedly; continued with uploaded references.")
        if not ctx.sources:
            raise PipelineError(
                "No usable sources to compare against (no readable references and no academic matches found)."
            )
        return ctx


# ── Match ─────────────────────────────────────────────────────────────────────
class MatchStage:
    """Run the (injected) plagiarism matcher and store its report in artifacts."""
    name = "match"

    def __init__(self, matcher: Matcher) -> None:
        self._matcher = matcher

    def run(self, ctx: CheckContext) -> CheckContext:
        result = self._matcher.check(ctx.require_document().text, ctx.sources)
        ctx.artifacts["overall"] = result["overall"]
        ctx.artifacts["per_source"] = result["per_source"]
        ctx.artifacts["matches"] = result["matches"]
        ctx.artifacts["paraphrase_enabled"] = result.get("paraphrase_enabled")
        # The confidence cutoff scales with corpus size (ADR-0024); carry the one actually
        # applied so the rerank stage and the report agree with the matcher.
        ctx.artifacts["confident_threshold_used"] = result.get("confident_threshold_used")
        ctx.artifacts["corpus_sentences"] = result.get("corpus_sentences", 0)
        ctx.extend_warnings(result.get("warnings"))
        return ctx


# ── Localize ──────────────────────────────────────────────────────────────────
class LocalizeStage:
    """Map each match's document span to its paragraph index + page."""
    name = "localize"

    def run(self, ctx: CheckContext) -> CheckContext:
        paragraphs = ctx.require_document().paragraphs
        matches = ctx.artifacts.get("matches", [])
        para_starts = [p["start"] for p in paragraphs]
        for m in matches:
            pi = bisect_right(para_starts, m["doc_start"]) - 1
            if 0 <= pi < len(paragraphs):
                m["paragraph_index"] = paragraphs[pi]["index"]
                m["page"] = paragraphs[pi]["page"]
            else:
                m["paragraph_index"] = None
                m["page"] = None
        return ctx


# ── Rerank (W4, opt-in) ───────────────────────────────────────────────────────
class RerankStage:
    """Cross-encoder rerank of *borderline* semantic matches.

    A bi-encoder embeds each sentence independently, so it cannot see how the two
    sentences relate; a cross-encoder reads the pair jointly. Measured on public
    data this cut MRPC false positives 0.643 -> 0.403 at t=0.66 (docs/PROGRESS.md).

    Cost control — one forward pass per pair, on CPU — so we rerank only where it
    can change the answer: verbatim is exact overlap (never reranked); scores
    outside [lo, hi] are not borderline; at most `max_pairs`, highest-similarity
    first, so when the cap bites the budget is spent verifying the *strongest*
    claims (the ones labelled "confident", where a wrong call is a false accusation).

    The bi-encoder `similarity` is preserved (it is what the UI shows); the
    cross-encoder result is recorded as `rerank_score` and re-decides `confidence`.
    Fails soft: if the model is unavailable the stage warns and leaves matches as-is.
    """
    name = "rerank"

    def __init__(self, *, enabled: bool = False, model_key: str = "cross-encoder-stsb",
                 lo: float = 0.60, hi: float = 0.92, max_pairs: int = 200,
                 confident_threshold: float = 0.78) -> None:
        self.enabled = enabled
        self.model_key = model_key
        self.lo = lo
        self.hi = hi
        self.max_pairs = max_pairs
        self.confident_threshold = confident_threshold

    def _candidates(self, matches):
        cand = [
            m for m in matches
            if m.get("match_type") in ("paraphrase", "translated")
            and self.lo <= float(m.get("similarity", 0.0)) <= self.hi
            and (m.get("doc_excerpt") or "").strip()
            and (m.get("source_excerpt") or "").strip()
        ]
        cand.sort(key=lambda m: float(m.get("similarity", 0.0)), reverse=True)
        return cand[: self.max_pairs]

    def run(self, ctx: CheckContext) -> CheckContext:
        if not self.enabled:
            return ctx
        matches = ctx.artifacts.get("matches") or []
        cand = self._candidates(matches)
        if not cand:
            return ctx

        try:
            from modelhub import get_cross_encoder
            ce = get_cross_encoder(self.model_key)
            pairs = [(m["doc_excerpt"], m["source_excerpt"]) for m in cand]
            raw = ce.predict(pairs, show_progress_bar=False)
        except Exception as exc:
            logger.exception("[pipeline.rerank] cross-encoder unavailable")
            ctx.warn(f"Cross-encoder reranking was skipped ({str(exc)[:120]}); "
                     "similarity scores are from the sentence embedder only.")
            return ctx

        cutoff = ctx.artifacts.get("confident_threshold_used") or self.confident_threshold
        for m, s in zip(cand, raw):
            score = max(0.0, min(1.0, float(s)))
            m["rerank_score"] = round(score, 4)
            m["reranked"] = True
            m["confidence"] = "confident" if score >= cutoff else "review"

        from services.plagiarism_matcher import confidence_breakdown, tokenize
        overall = ctx.artifacts.get("overall")
        if isinstance(overall, dict):
            overall.update(confidence_breakdown(tokenize(ctx.require_document().text), matches))
        ctx.artifacts["reranked_count"] = len(cand)
        return ctx


class TriageStage:
    """W8 — classify each match by the honest fix it needs (ADR-0022).

    Deterministic rules over quotation marks, nearby citation markers, the confidence
    band and cross-source repetition (services.triage). Annotates each match with
    `triage` and stores `triage_summary` (counts, prioritised action items, method note).
    Runs after LocalizeStage so paragraph context is available. Never raises: a failure
    leaves matches un-triaged with a warning rather than sinking the check.
    """
    name = "triage"

    def run(self, ctx: CheckContext) -> CheckContext:
        from services.triage import triage_matches

        doc = ctx.require_document()
        matches = ctx.artifacts.get("matches") or []
        try:
            ctx.artifacts["triage_summary"] = triage_matches(doc.text, doc.paragraphs, matches, ctx.sources)
        except Exception:
            logger.exception("[pipeline.triage] failed; matches left un-triaged")
            ctx.warn("Flag triage was skipped because of an internal error; matches are shown without remediation types.")
        return ctx


class CoachStage:
    """W9 — per-flag honest coaching, phrased by a model, decided by the rules (ADR-0031).

    Runs after TriageStage. At most `max_per_check` model calls, highest-priority flags
    first; every field the model returns is post-filtered through the matcher so it can
    never hand the author copied text, and through an evasion lexicon so it can never
    coach disguise (ADR-0014). Never raises: without a client, or on any failure, the
    author sees the rule text and `coach_summary.skipped_reason` says why.
    """
    name = "coach"

    def __init__(self, *, client=None, cache=None, budget=None, max_per_check: int = 3,
                 timeout: float = 20.0) -> None:
        from services.coach import CoachBudget
        from utils.ttl_cache import TTLCache

        self.client = client
        self.cache = cache if cache is not None else TTLCache(max_size=2000, ttl_seconds=86400)
        self.budget = budget if budget is not None else CoachBudget()
        self.max_per_check = max_per_check
        self.timeout = timeout

    def run(self, ctx: CheckContext) -> CheckContext:
        from services.coach import coach_matches

        matches = ctx.artifacts.get("matches") or []
        try:
            ctx.artifacts["coach_summary"] = coach_matches(
                matches, client=self.client, cache=self.cache, budget=self.budget,
                max_per_check=self.max_per_check, timeout=self.timeout)
        except Exception:
            logger.exception("[pipeline.coach] failed; matches left with rule text only")
            ctx.artifacts["coach_summary"] = {"coached": 0, "calls": 0, "cached": 0, "filtered_fields": 0,
                                              "model": None, "skipped_reason": "internal error", "errors": [],
                                              "method": "Coaching was skipped because of an internal error."}
        return ctx

