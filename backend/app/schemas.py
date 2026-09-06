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


class CoachCard(BaseModel):
    """Per-flag coaching phrased by a model (ADR-0031). Always labelled; never a rewrite."""
    what_it_is: str
    why_flagged: str
    honest_fix: str
    do_not: str
    filtered: List[str] = Field(default_factory=list, description="Fields the post-filter replaced with rule text.")
    model: Optional[str] = None
    cached: bool = False
    ai_written: bool = True
    source_visible: bool = True


class CoachSummary(BaseModel):
    coached: int = 0
    calls: int = 0
    cached: int = 0
    filtered_fields: int = 0
    model: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    skipped_reason: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    method: str = ""


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
    coach: Optional[CoachCard] = None


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
    # ADR-0031 — absent from the contract at first, so Pydantic silently dropped them from responses.
    coach_model: Optional[str] = Field(default=None, description="Model that phrased the coaching, if any.")
    coach_estimated_cost_usd: float = Field(default=0.0, description="List-price estimate of this check's coaching calls.")


class ChecklistItem(BaseModel):
    kind: Literal["flag", "standing"]
    type: Optional[str] = None
    label: str
    count: int = 1
    priority: int = 3


class Report(BaseModel):
    """Submission-risk report (ADR-0032). A band with its reason — never a pass/fail."""
    band: Literal["act", "look", "clear"]
    label: str
    reason: str
    needs_action: int
    review_count: int
    confident_pct: float
    similarity_pct: float
    checklist: List[ChecklistItem]
    disclosure: str
    ai_text_detection: str
    footer: str
    coverage: str


class RecheckSnapshot(BaseModel):
    similarity_pct: float
    confident_pct: float
    review_count: int
    match_count: int
    needs_action: int
    band: Optional[str] = None


class RecheckExample(BaseModel):
    match_type: Optional[str] = None
    source_name: Optional[str] = None
    source_excerpt: str = ""
    type: Optional[str] = None


class Recheck(BaseModel):
    """Before/after against an earlier job of the same manuscript (ADR-0032)."""
    previous_job_id: Optional[str] = None
    same_filename: bool
    before: RecheckSnapshot
    after: RecheckSnapshot
    delta: Dict[str, float]
    resolved: int
    new: int
    remaining: int
    resolved_examples: List[RecheckExample] = Field(default_factory=list)
    new_examples: List[RecheckExample] = Field(default_factory=list)
    method: str


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
    coach_summary: Optional[CoachSummary] = None
    report: Optional[Report] = None
    recheck: Optional[Recheck] = None
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
    jobs_in_memory: int = Field(description="Jobs currently held by the store (name kept for compatibility).")
    store: Literal["memory", "postgres"] = Field(default="memory", description="Where job state lives (ADR-0029).")
    auth: Literal["off", "optional", "required"] = Field(
        default="off", description="off = no verifier configured; optional = tokens verified when sent; required (ADR-0030).")
    embedding_cache: Optional[EmbeddingCacheStats] = None


class ErrorResponse(BaseModel):
    detail: str
