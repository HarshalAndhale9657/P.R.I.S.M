"""
P.R.I.S.M. — Pipeline core (ADR-0015 / ADR-0016 / ADR-0019)
===========================================================
Clean, pluggable stages so each step of an originality check can be swapped and
evaluated independently:

    parse -> retrieve -> match -> rerank -> localize -> [triage -> coach -> report]

Live: parse, retrieve, match, rerank (opt-in), localize. The bracketed stages are
declared skeletons for W8–W10.

Pure data-in / data-out: a stage takes a `CheckContext` and returns it, mutating
`ctx.document` / `ctx.sources` / `ctx.artifacts` / `ctx.warnings`. No FastAPI
dependency, so the whole pipeline is unit-testable and reusable by the eval
harness. Collaborators (matcher, academic search) are *injected*.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# The matcher's canonical source type is shared across the pipeline (DRY).
from services.plagiarism_matcher import SourceDoc

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """A user-safe error raised by a stage; the runner surfaces its message verbatim.

    Anything else raised inside a stage is logged server-side and shown generically.
    """


@dataclass(frozen=True)
class RawInput:
    """An uploaded file before parsing."""
    name: str
    data: bytes


@dataclass
class Document:
    """The manuscript under check, plus offset-preserving paragraph anchors."""
    name: str
    text: str
    paragraphs: List[Dict[str, Any]] = field(default_factory=list)  # {index, page, start, end, text}
    page_count: Optional[int] = None


@dataclass
class CheckContext:
    """Everything a stage may read or write, threaded through the pipeline.

    `artifacts` accumulates stage outputs under stable keys:
      overall, per_source, matches, paraphrase_enabled   (match)
      academic_used                                       (retrieve)
      reranked_count                                      (rerank)
      timings_ms                                          (orchestrator)
    """
    document: Optional[Document] = None
    raw_document: Optional[RawInput] = None
    raw_sources: List[RawInput] = field(default_factory=list)
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

    def require_document(self) -> Document:
        if self.document is None:
            raise PipelineError("No document to check.")
        return self.document


@runtime_checkable
class Stage(Protocol):
    """A pipeline step. Implementations set `name` and transform the context."""
    name: str

    def run(self, ctx: CheckContext) -> CheckContext: ...
