"""
P.R.I.S.M. — Runtime configuration
==================================
Every operational knob lives here, read once from the environment (prefix
``PRISM_``) with a documented default. Nothing else in the codebase reads
``os.environ`` for behaviour, so the deploy surface is exactly this file.

Values are chosen for a single 4-vCPU / 8 GB box (LAUNCH_PLAN §4). The memory
model is deliberately arithmetic, not hope: every queued check can hold at most
``max_request_bytes`` of raw upload, and at most ``max_pending_jobs`` checks can
be queued, so worst-case upload memory is bounded by their product.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.9.0"
MiB = 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PRISM_", env_file=".env", extra="ignore")

    # ── Deployment ──────────────────────────────────────────────────────────
    env: Literal["dev", "test", "prod"] = "dev"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"
    trust_proxy: bool = Field(
        default=False,
        description="Honour X-Forwarded-For for rate limiting. Only enable behind a reverse proxy you control.",
    )
    log_format: Literal["text", "json"] = "text"
    log_level: str = "INFO"
    sentry_dsn: str = ""

    # ── Upload guards ───────────────────────────────────────────────────────
    max_file_bytes: int = 20 * MiB
    max_request_bytes: int = Field(
        default=60 * MiB,
        description="Aggregate cap on paper + all references in one check (413 above).",
    )
    max_reference_files: int = 25
    max_pdf_pages: int = 300
    max_document_chars: int = 2_000_000

    # ── Worker / queue ──────────────────────────────────────────────────────
    worker_threads: int = Field(default=2, description="Concurrent checks. Torch already multi-threads inside each.")
    max_pending_jobs: int = Field(default=16, description="Queued (not yet running) checks before 503.")
    job_ttl_seconds: int = Field(default=1800, description="Results are purged from memory after this.")
    max_jobs: int = 200
    result_cache_size: int = 64
    result_cache_ttl_seconds: int = 1800

    # ── Rate limiting (per client IP; in-process) ───────────────────────────
    rate_limit_submissions: int = Field(default=12, description="Submissions allowed per window per IP. 0 disables.")
    rate_limit_window_seconds: int = 600

    # ── Matching ────────────────────────────────────────────────────────────
    paraphrase_threshold: float = 0.66      # reporting floor (ADR-0013 / ADR-0017)
    confident_threshold: float = 0.78       # confidence cutoff (ADR-0017)
    confidence_scaling: bool = Field(
        default=True,
        description="Raise the confidence cutoff as the source corpus grows (ADR-0024). The matcher takes a max "
                    "over every source sentence, so a fixed cutoff over-asserts at scale. Off = fixed cutoff.",
    )
    confidence_scale_k: float = Field(default=0.06, description="Cutoff increase per decade of corpus size.")
    confidence_scale_pivot: int = Field(default=500, description="Corpus size at which the base cutoff applies.")
    confidence_ceiling: float = Field(default=0.92, description="The scaled cutoff never exceeds this.")
    max_source_sentences: int = 6000
    embedding_cache_entries: int = Field(
        default=50_000,
        description="Cached sentence embeddings (ADR-0023). ~1.5 KB each at 384 dims, so 50k ≈ 75 MB. "
                    "Set 0 to disable. A re-check after edits is ~6x faster with this warm.",
    )
    rerank: bool = Field(default=False, description="Cross-encoder rerank of borderline matches (W4, opt-in).")
    rerank_model: str = "cross-encoder-stsb"
    warmup_models: bool = Field(default=False, description="Load the embedder at startup so /health/ready is honest.")

    # ── Academic corpus ─────────────────────────────────────────────────────
    academic_enabled: bool = True
    academic_timeout_seconds: float = 10.0
    contact_email: str = Field(
        default="",
        description="Sent in the User-Agent to OpenAlex (polite pool) and arXiv. Set it in production.",
    )
    s2_api_key: str = Field(
        default="",
        description="Semantic Scholar API key. The provider is enabled only when set (unauthenticated calls get 429).",
    )
    academic_fulltext: bool = Field(
        default=True,
        description="Download open-access PDFs for the most relevant candidates and match against full text (W4b).",
    )
    academic_fulltext_max_docs: int = Field(default=8, description="Max OA PDFs fetched per check.")
    academic_fulltext_max_bytes: int = 15 * MiB
    academic_fulltext_timeout_seconds: float = 15.0

    @property
    def academic_providers(self) -> tuple:
        base = ("openalex", "arxiv")
        return base + (("semanticscholar",) if self.s2_api_key else ())

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
