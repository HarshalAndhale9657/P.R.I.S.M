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
from typing import List, Sequence

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


def default_check_stages(matcher, search_fn, *, use_academic: bool) -> List[Stage]:
    """The live originality-check pipeline (W1).

    Skeleton stages (rerank/ai_risk/triage/coach/report) are intentionally NOT
    wired in yet — they are pass-throughs and add nothing until implemented in
    W3-W9. Import and append them here when each lands.
    """
    from .stages import RetrieveStage, MatchStage, LocalizeStage
    return [
        RetrieveStage(search_fn, use_academic=use_academic),
        MatchStage(matcher),
        LocalizeStage(),
    ]
