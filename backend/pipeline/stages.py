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


class RerankStage(_SkeletonStage):
    """W4: cross-encoder rerank of top-k candidate matches (hard paraphrases)."""
    name = "rerank"


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
