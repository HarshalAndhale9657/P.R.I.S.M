"""
P.R.I.S.M. — Pipeline core (ADR-0015 / ADR-0016 re-architecture)
================================================================
Clean, pluggable stages so each step of an originality check can be swapped and
evaluated independently:

    parse -> retrieve -> match -> rerank -> ai_risk -> triage -> coach -> report

W1 implements the seams plus the three *live* stages (retrieve, match, localize).
rerank / ai_risk / triage / coach / report are declared as skeleton stages to be
filled in later weeks (W3-W9) — they are pass-throughs today so behaviour is
unchanged. The existing matcher (`services.plagiarism_matcher`) and academic
corpus (`services.academic_corpus`) are *injected* into the stages, so the
monkeypatch seams the tests rely on (`main.plagiarism_matcher.check`,
`main.academic_search`) still hold when `main._compute_check` runs the pipeline.

Pure data-in / data-out: a stage takes a `CheckContext` and returns it, mutating
`ctx.artifacts` / `ctx.sources` / `ctx.warnings`. No FastAPI dependency, so the
whole pipeline is trivially unit-testable and reusable by the eval harness.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# Reuse the matcher's canonical source type across the pipeline (DRY — the matcher,
# main.py and the corpus all already speak SourceDoc).
from services.plagiarism_matcher import SourceDoc

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """A user-safe error raised by a stage; the app maps it to a job error.

    Distinct from unexpected exceptions: PipelineError messages are safe to show
    to a user (e.g. "No readable text found"), whereas other exceptions are
    logged server-side and surfaced generically.
    """


@dataclass
class Document:
    """The manuscript under check, plus offset-preserving paragraph anchors."""
    name: str
    text: str
    paragraphs: List[Dict[str, Any]] = field(default_factory=list)  # {index, page, start, end, text}


@dataclass
class CheckContext:
    """Everything a stage may read or write, threaded through the pipeline.

    `artifacts` accumulates stage outputs under stable keys:
      overall, per_source, matches, paraphrase_enabled  (match)
      academic_used                                      (retrieve)
      ai_risk, triage, coaching, report                  (later stages)
    """
    document: Document
    sources: List[SourceDoc] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def warn(self, message: str) -> None:
        if message:
            self.warnings.append(message)

    def extend_warnings(self, messages: Optional[List[str]]) -> None:
        for m in messages or []:
            self.warn(m)


@runtime_checkable
class Stage(Protocol):
    """A pipeline step. Implementations set `name` and transform the context."""
    name: str

    def run(self, ctx: CheckContext) -> CheckContext: ...
