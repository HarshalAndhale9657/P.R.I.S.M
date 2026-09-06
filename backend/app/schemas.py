"""
P.R.I.S.M. — API contract (Pydantic response models)
=====================================================
These are the *public* shapes of ``/api/v1/check``. FastAPI validates every
response against them, so a stage that silently changes a field name breaks a
test instead of a user. They also make ``/openapi.json`` a real contract — the
frontend, the downloadable report and any future SDK read the same schema.

Field semantics (see ADR-0017 for the confidence band):

* ``similarity`` — the bi-encoder cosine (or 1.0 for verbatim). What the UI shows.
* ``confidence`` — ``confident`` at/above the confidence cutoff, ``review`` in the
  explicit inconclusive band. A ``review`` match must never be presented as a
  confirmed copy.
* ``rerank_score`` — present only when the cross-encoder ran on this match.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

MatchType = Literal["verbatim", "paraphrase", "translated"]
Confidence = Literal["confident", "review"]
JobState = Literal["queued", "running", "done", "error"]


class Paragraph(BaseModel):
    index: int
    page: Optional[int] = None
    start: int
    end: int


SourceKind = Literal["fulltext", "abstract"]


class SourceRef(BaseModel):
    id: str
    name: str
    origin: str = "upload"
    url: Optional[str] = None
    kind: SourceKind = Field(default="fulltext", description="Whether the matched text was the full document or only an abstract.")


TriageType = Literal[
    "verbatim_uncited", "paraphrase_uncited", "verbatim_cited_unquoted", "quoted_uncited",
    "paraphrase_cited", "needs_review", "common_phrase", "quoted_cited",
]


class TriageSignals(BaseModel):
    quoted: bool
    cited: bool
    citation_markers: List[str] = Field(default_factory=list)
    shared_by_sources: int = 1
    stopword_ratio: float = 0.0
    numeric_conflict: bool = False


class Triage(BaseModel):
    """Deterministic remediation typing for one match (ADR-0022). Coaching, never a verdict."""
    type: TriageType
    priority: int = Field(ge=1, le=5, description="1 = act first … 5 = nothing to fix")
    label: str
    what: str
    fix: str
    note: Optional[str] = None
    signals: TriageSignals


class TriageActionItem(BaseModel):
    type: TriageType
    priority: int
    label: str
    count: int


class TriageSummary(BaseModel):
    counts: Dict[str, int]
    action_items: List[TriageActionItem]
    needs_action: int = Field(description="Matches at priority 1–2: fix before submitting.")
    method: str


class Match(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    match_type: MatchType
    similarity: float = Field(ge=0.0, le=1.0)
    confidence: Confidence
    words: int
    doc_start: int
    doc_end: int
    doc_excerpt: str
    doc_lang: Optional[str] = None
    source_lang: Optional[str] = None
    source_id: str
    source_name: str
    source_origin: str = "upload"
    source_url: Optional[str] = None
    source_start: int
    source_end: int
    source_excerpt: str
    source_context: str
    paragraph_index: Optional[int] = None
    page: Optional[int] = None
    rerank_score: Optional[float] = None
    reranked: Optional[bool] = None
    numeric_conflict: bool = Field(
        default=False,
        description="This match and its source state numbers but share none — same shape, different figures "
                    "(ADR-0026). It is why the band is `review` rather than `confident`.",
    )
    triage: Optional[Triage] = None


class Overall(BaseModel):
    similarity_pct: float
    verbatim_pct: float
    paraphrase_pct: float
    translated_pct: float
    confident_pct: float
    review_pct: float
    matched_words: int
    total_words: int
    match_count: int
    review_count: int
    source_count: int


class PerSource(BaseModel):
    id: str
    name: str
    origin: str = "upload"
    url: Optional[str] = None
    kind: SourceKind = "fulltext"
    matched_words: int
    similarity_pct: float


class EngineInfo(BaseModel):
    """What produced this result — so a report can state its method honestly."""
    version: str
    bi_encoder: str
    paraphrase_threshold: float
    confident_threshold: float = Field(description="The confidence cutoff actually applied to this check.")
    confident_threshold_base: Optional[float] = Field(
        default=None, description="The configured base cutoff before corpus-size scaling (ADR-0024).")
    corpus_sentences: int = Field(default=0, description="Source sentences each passage was scored against.")
    reranked: bool
    rerank_model: Optional[str] = None
    coverage: str = Field(
        description="Plain-language statement of what was (and was not) checked against.",
    )


class CheckResult(BaseModel):
    filename: str
    status: Literal["success"] = "success"
    document_text: str
    paragraphs: List[Paragraph]
    page_count: Optional[int] = None
    academic_used: bool
    sources: List[SourceRef]
    overall: Overall
    per_source: List[PerSource]
    matches: List[Match]
    paraphrase_enabled: Optional[bool] = None
    warnings: List[str] = Field(default_factory=list)
    triage_summary: Optional[TriageSummary] = None
    timings_ms: Dict[str, float] = Field(default_factory=dict)
    engine: EngineInfo


class SubmitCheckResponse(BaseModel):
    job_id: str
    status: JobState
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobState
    result: Optional[CheckResult] = None
    error: Optional[str] = None


class QueueStats(BaseModel):
    running: int
    pending: int
    capacity: int


class EmbeddingCacheStats(BaseModel):
    """Operational view of the sentence-embedding cache (ADR-0023)."""
    entries: int
    capacity: int
    hits: int
    misses: int
    evictions: int
    hit_rate: float


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "starting"]
    version: str
    env: str
    model_loaded: bool
    rerank_enabled: bool
    queue: QueueStats
    jobs_in_memory: int
    embedding_cache: Optional[EmbeddingCacheStats] = None


class ErrorResponse(BaseModel):
    detail: str
