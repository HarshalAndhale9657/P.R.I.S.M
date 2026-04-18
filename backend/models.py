"""
P.R.I.S.M. — Pydantic Response Models & Edge-Case Types
=========================================================

Structured models for API responses, warnings, and degraded-mode
indicators. Every edge case produces a typed Warning object that
the frontend can display contextually.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


# ─── Warning / Edge-Case Classification ─────────────────────────────────────

class WarningSeverity(str, Enum):
    """Severity levels for pipeline warnings."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class WarningCode(str, Enum):
    """
    Codified edge-case identifiers.
    Frontend can pattern-match on these to render specific UI hints.
    """
    # PDF parsing
    PDF_DEGRADED_MODE = "pdf_degraded_mode"
    PDF_NO_TEXT = "pdf_no_text"
    PDF_SCANNED = "pdf_scanned"
    PDF_EMPTY_FILE = "pdf_empty_file"
    PDF_CORRUPT = "pdf_corrupt"

    # Feature extraction
    FEATURES_SHORT_PAPER = "features_short_paper"
    FEATURES_TOO_FEW_VALID = "features_too_few_valid"

    # Clustering
    CLUSTER_SKIPPED_SHORT = "cluster_skipped_short"
    CLUSTER_NOISE_OVERRIDE = "cluster_noise_override"
    CLUSTER_ZERO_VARIANCE = "cluster_zero_variance"
    CLUSTER_SINGLE_AUTHOR = "cluster_single_author"

    # GPT / AI reasoning
    GPT_UNAVAILABLE = "gpt_unavailable"
    GPT_TIMEOUT = "gpt_timeout"
    GPT_PARTIAL_RESULTS = "gpt_partial_results"
    GPT_RATE_LIMITED = "gpt_rate_limited"

    # Source tracing
    SOURCE_ARXIV_TIMEOUT = "source_arxiv_timeout"
    SOURCE_ARXIV_RATE_LIMITED = "source_arxiv_rate_limited"
    SOURCE_NO_MATCHES = "source_no_matches"
    SOURCE_EMBEDDING_FAILED = "source_embedding_failed"

    # Citation forensics
    CITATION_NONE_FOUND = "citation_none_found"
    CITATION_NO_YEARS = "citation_no_years"

    # General
    PARTIAL_RESULTS = "partial_results"


class PipelineWarning(BaseModel):
    """
    A single warning produced by any pipeline stage.
    Accumulates in the response so the frontend can display
    contextual alerts without crashing.
    """
    code: WarningCode
    severity: WarningSeverity
    stage: str = Field(..., description="Pipeline stage that generated the warning (e.g., 'pdf_parser', 'clustering')")
    message: str = Field(..., description="Human-readable description")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Machine-readable extra context")


# ─── Edge-Case Accumulator ──────────────────────────────────────────────────

class PipelineContext:
    """
    Mutable context object threaded through all pipeline stages.
    Collects warnings, tracks degraded mode, and allows stages
    to signal downstream stages to skip or adjust behaviour.
    """

    def __init__(self):
        self.warnings: List[PipelineWarning] = []
        self.degraded_mode: bool = False
        self.skip_clustering: bool = False
        self.skip_gpt: bool = False
        self.skip_source_tracing: bool = False
        self.partial_results: bool = False

    def add_warning(
        self,
        code: WarningCode,
        severity: WarningSeverity,
        stage: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.warnings.append(PipelineWarning(
            code=code,
            severity=severity,
            stage=stage,
            message=message,
            details=details,
        ))
        if severity == WarningSeverity.ERROR:
            self.partial_results = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "warnings": [w.model_dump() for w in self.warnings],
            "warning_count": len(self.warnings),
            "degraded_mode": self.degraded_mode,
            "partial_results": self.partial_results,
        }
