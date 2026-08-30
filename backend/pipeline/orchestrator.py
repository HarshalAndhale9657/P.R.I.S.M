"""
P.R.I.S.M. — Pipeline orchestrator
==================================
Runs an ordered list of stages over a CheckContext. A `PipelineError` (user-safe)
propagates unchanged; any other exception is logged and re-raised so the caller
maps it to a generic error (no internal-detail leakage) — matching the existing
`main._server_error` / job-error contract.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional, Sequence

from .base import CheckContext, PipelineError, Stage

logger = logging.getLogger(__name__)


def run_pipeline(ctx: CheckContext, stages: Sequence[Stage]) -> CheckContext:
    """Execute stages in order, threading the context through each."""
    for stage in stages:
        name = getattr(stage, "name", stage.__class__.__name__)
        try:
            ctx = stage.run(ctx)
        except PipelineError:
            raise  # user-safe; let the caller surface it
        except Exception:
            logger.exception("[pipeline] stage %r failed", name)
            raise
    return ctx


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def default_check_stages(matcher, search_fn, *, use_academic: bool,
                         rerank: Optional[bool] = None) -> List[Stage]:
    """The live originality-check pipeline.

    Live: retrieve -> match -> rerank (opt-in) -> localize.
    Still skeletons (added as they land, W8+): ai_risk, triage, coach, report.

    `rerank` runs a cross-encoder over borderline semantic matches. It measurably
    cuts false positives (MRPC FPR 0.643 -> 0.403) but costs one extra model
    forward pass per borderline pair on CPU, so it is **opt-in**: pass
    `rerank=True` or set `PRISM_RERANK=1`. See docs/PROGRESS.md before flipping
    the default — the latency budget is <60s per check.
    """
    from .stages import RetrieveStage, MatchStage, LocalizeStage, RerankStage

    enabled = _env_flag("PRISM_RERANK", False) if rerank is None else rerank
    return [
        RetrieveStage(search_fn, use_academic=use_academic),
        MatchStage(matcher),
        RerankStage(
            enabled=enabled,
            model_key=os.getenv("PRISM_RERANK_MODEL", "cross-encoder-stsb"),
            confident_threshold=getattr(matcher, "confident_threshold", 0.78),
        ),
        LocalizeStage(),
    ]
