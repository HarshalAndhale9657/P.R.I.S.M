"""
P.R.I.S.M. pipeline package — pluggable originality-check stages (ADR-0015/0016).

Public API:
    from pipeline import (
        CheckContext, Document, SourceDoc, Stage, PipelineError,
        run_pipeline, default_check_stages,
    )
"""
from .base import CheckContext, Document, PipelineError, SourceDoc, Stage
from .orchestrator import default_check_stages, run_pipeline

__all__ = [
    "CheckContext",
    "Document",
    "SourceDoc",
    "Stage",
    "PipelineError",
    "run_pipeline",
    "default_check_stages",
]
