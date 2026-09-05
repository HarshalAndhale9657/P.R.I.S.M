"""Pluggable originality-check pipeline (ADR-0015 / 0016 / 0019)."""
from .base import CheckContext, Document, PipelineError, RawInput, SourceDoc, Stage
from .orchestrator import build_check_stages, default_check_stages, run_pipeline
from .stages import (
    CoachStage,
    LocalizeStage,
    MatchStage,
    ParseStage,
    ReportStage,
    RerankStage,
    RetrieveStage,
    TriageStage,
)

__all__ = [
    "CheckContext", "Document", "PipelineError", "RawInput", "SourceDoc", "Stage",
    "build_check_stages", "default_check_stages", "run_pipeline",
    "ParseStage", "RetrieveStage", "MatchStage", "RerankStage", "LocalizeStage",
    "TriageStage", "CoachStage", "ReportStage",
]
