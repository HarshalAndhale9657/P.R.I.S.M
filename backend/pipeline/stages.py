"""
P.R.I.S.M. — Pipeline stage implementations
===========================================
Live stages (W1): RetrieveStage, MatchStage, LocalizeStage.
Skeleton stages (filled W3-W9): RerankStage, AiRiskStage, TriageStage,
CoachStage, ReportStage — declared so the architecture is visible and the wiring
is stable, but pass-through today (zero behaviour change).

Dependencies (matcher, academic-search fn) are INJECTED, never imported from
`main`, so there is no circular import and the tests can still monkeypatch
`main.plagiarism_matcher.check` / `main.academic_search` — `main._compute_check`
passes the current module globals in at call time.
"""
from __future__ import annotations

import logging
from bisect import bisect_right
from typing import Any, Callable, List, Protocol, Sequence, Tuple

from .base import CheckContext, SourceDoc, Stage

logger = logging.getLogger(__name__)


# ── Structural typing for the injected collaborators ─────────────────────────
class Matcher(Protocol):
    def check(self, doc_text: str, sources: Sequence[SourceDoc]) -> dict: ...


# search(doc_text) -> (sources, warnings)   (matches services.academic_corpus.search)
SearchFn = Callable[[str], Tuple[List[SourceDoc], List[str]]]


# ── Live stages ──────────────────────────────────────────────────────────────
class RetrieveStage:
    """Gather candidate academic sources (opt-in) and append them to the context.

    Uploaded references are already in `ctx.sources` (added by the caller). When
    `use_academic` is set, this calls the injected search fn and merges results.
    Never raises: retrieval failure degrades to a warning.
    """
    name = "retrieve"

    def __init__(self, search_fn: SearchFn, *, use_academic: bool) -> None:
        self._search = search_fn
        self._use_academic = use_academic

    def run(self, ctx: CheckContext) -> CheckContext:
        ctx.artifacts.setdefault("academic_used", False)
        if not self._use_academic:
            return ctx
        try:
            acad_sources, acad_warnings = self._search(ctx.document.text)
            ctx.sources.extend(acad_sources)
            ctx.extend_warnings(acad_warnings)
            ctx.artifacts["academic_used"] = len(acad_sources) > 0
        except Exception:
            logger.exception("[pipeline.retrieve] academic search failed")
            ctx.warn("Academic-database search failed unexpectedly; continued with uploaded references.")
        return ctx


class MatchStage:
    """Run the (injected) plagiarism matcher and store its report in artifacts."""
    name = "match"

    def __init__(self, matcher: Matcher) -> None:
        self._matcher = matcher

    def run(self, ctx: CheckContext) -> CheckContext:
        result = self._matcher.check(ctx.document.text, ctx.sources)
        ctx.artifacts["overall"] = result["overall"]
        ctx.artifacts["per_source"] = result["per_source"]
        ctx.artifacts["matches"] = result["matches"]
        ctx.artifacts["paraphrase_enabled"] = result.get("paraphrase_enabled")
        ctx.extend_warnings(result.get("warnings"))
        return ctx


class LocalizeStage:
    """Map each match's document span to its paragraph index + page."""
    name = "localize"

    def run(self, ctx: CheckContext) -> CheckContext:
        paragraphs = ctx.document.paragraphs
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


# ── Skeleton stages (declared now, implemented in later weeks) ───────────────
class _SkeletonStage:
    """A pass-through stage placeholder. Subclasses set `name`. Implemented later."""
    name = "skeleton"

    def run(self, ctx: CheckContext) -> CheckContext:  # pragma: no cover - trivial
        return ctx


class RerankStage:
    """W4 — cross-encoder rerank of *borderline* semantic matches.

    A bi-encoder embeds each sentence independently, so it cannot see how the two
    sentences relate; a cross-encoder reads the pair jointly. Measured on public
    data, this cut MRPC false positives **0.643 -> 0.403** at t=0.66 and lifted
    recall@FPR<=0.15 from 0.44 to 0.61 (docs/PROGRESS.md).

    Cost control — a cross-encoder is one forward pass per pair, on CPU in
    production, so we rerank only where it can change the answer:
      * verbatim matches are exact overlap -> never reranked;
      * scores below `lo` or above `hi` are not borderline -> left alone;
      * at most `max_pairs`, highest-similarity first.

    The bi-encoder `similarity` is preserved (it is what the UI shows and what the
    percentages are built from); the cross-encoder result is recorded as
    `rerank_score` and used to re-decide `confidence` (ADR-0017's band). Confidence
    aggregates are then recomputed so they never go stale.

    Fails soft: if the model is unavailable the stage warns and leaves matches as-is.
    """
    name = "rerank"

    def __init__(
        self,
        *,
        enabled: bool = False,
        model_key: str = "cross-encoder-stsb",
        lo: float = 0.60,
        hi: float = 0.92,
        max_pairs: int = 200,
        confident_threshold: float = 0.78,
    ) -> None:
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
        # Highest-similarity first: when the cap bites, we spend the budget verifying
        # the STRONGEST claims. Those are the ones currently labelled "confident", so a
        # wrong call there is a false accusation — the failure mode we care most about.
        # (Lower-scoring pairs are already labelled "review", so a missed promotion is
        # a far cheaper error than a missed demotion.)
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

        for m, s in zip(cand, raw):
            score = max(0.0, min(1.0, float(s)))
            m["rerank_score"] = round(score, 4)
            m["reranked"] = True
            # The cross-encoder decides the band; the displayed similarity stays
            # the bi-encoder cosine so the number the user sees keeps its meaning.
            m["confidence"] = "confident" if score >= self.confident_threshold else "review"

        # Recompute confidence coverage — the band changed for some matches.
        from services.plagiarism_matcher import confidence_breakdown, tokenize
        overall = ctx.artifacts.get("overall")
        if isinstance(overall, dict):
            overall.update(confidence_breakdown(tokenize(ctx.document.text), matches))
        ctx.artifacts["reranked_count"] = len(cand)
        return ctx


class AiRiskStage(_SkeletonStage):
    """Later: honesty-gated AI-generated-text risk band (deferred per ADR-0016)."""
    name = "ai_risk"


class TriageStage(_SkeletonStage):
    """W8: classify each match by remediation type (quote/cite/boilerplate/...)."""
    name = "triage"


class CoachStage(_SkeletonStage):
    """W9: per-flag honest-fix coaching (source-visible, never rewrite-to-evade)."""
    name = "coach"


class ReportStage(_SkeletonStage):
    """W10: assemble the submission-risk report payload."""
    name = "report"
