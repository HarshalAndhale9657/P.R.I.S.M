"""
P.R.I.S.M. — Pipeline orchestrator
==================================
Runs an ordered list of stages over a CheckContext and records per-stage wall
time in ``ctx.artifacts["timings_ms"]`` — the only place latency is measured,
so the number in a result is the number an operator sees in the logs.

A `PipelineError` (user-safe) propagates unchanged; any other exception is
logged with the failing stage's name and re-raised for the runner to surface
generically.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Sequence

from .base import CheckContext, PipelineError, Stage

logger = logging.getLogger(__name__)


def run_pipeline(ctx: CheckContext, stages: Sequence[Stage]) -> CheckContext:
    """Execute stages in order, threading the context through each."""
    timings = ctx.artifacts.setdefault("timings_ms", {})
    for stage in stages:
        name = getattr(stage, "name", stage.__class__.__name__)
        t0 = time.perf_counter()
        try:
            ctx = stage.run(ctx)
        except PipelineError:
            raise
        except Exception:
            logger.exception("[pipeline] stage %r failed", name)
            raise
        finally:
            timings[name] = round((time.perf_counter() - t0) * 1000.0, 1)
    return ctx


def build_check_stages(
    *,
    matcher,
    search_fn,
    use_academic: bool,
    rerank: bool = False,
    rerank_model: str = "cross-encoder-stsb",
    max_pdf_pages: int = 300,
    max_document_chars: int = 2_000_000,
) -> List[Stage]:
    """The live originality-check pipeline: parse -> retrieve -> match -> rerank -> localize -> triage.

    `rerank` runs a cross-encoder over borderline semantic matches. It measurably
    cuts false positives (MRPC FPR 0.643 -> 0.403) but costs one model forward
    pass per borderline pair on CPU, so it is opt-in (settings.rerank).
    """
    from .stages import LocalizeStage, MatchStage, ParseStage, RerankStage, RetrieveStage, TriageStage

    return [
        ParseStage(max_pdf_pages=max_pdf_pages, max_chars=max_document_chars),
        RetrieveStage(search_fn, use_academic=use_academic),
        MatchStage(matcher),
        RerankStage(
            enabled=rerank,
            model_key=rerank_model,
            confident_threshold=getattr(matcher, "confident_threshold", 0.78),
        ),
        LocalizeStage(),
        TriageStage(),
    ]


def default_check_stages(matcher, search_fn, *, use_academic: bool, rerank: Optional[bool] = None) -> List[Stage]:
    """Backwards-compatible alias (pre-ADR-0019 name). Prefer `build_check_stages`."""
    return build_check_stages(matcher=matcher, search_fn=search_fn, use_academic=use_academic,
                              rerank=bool(rerank))
