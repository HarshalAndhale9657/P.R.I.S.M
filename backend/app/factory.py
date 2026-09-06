"""
P.R.I.S.M. — application factory
================================
`create_app()` wires settings → logging → middleware → worker → routers. It is
the single composition root: every collaborator the request path needs hangs
off `app.state`, and tests build an app with their own `Settings` instead of
mutating module globals.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from functools import partial
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.academic_corpus import search as academic_search
from services.embedding_cache import configure_cache
from services.fulltext import FullTextFetcher
from services.plagiarism_matcher import PlagiarismMatcher
from worker import BoundedExecutor, CheckRunner, InMemoryJobStore

from .auth import JWTVerifier
from .limits import RateLimiter
from .logging_config import configure_logging
from .middleware import BodySizeGuardMiddleware, RequestIdMiddleware
from .routers import check, health
from .settings import APP_VERSION, Settings, get_settings

logger = logging.getLogger("prism")

_DESCRIPTION = """
Source-attribution originality checker. Upload a manuscript plus reference
sources (and/or search open-access abstracts) and receive localized verbatim,
paraphrase and translated matches with an explicit confidence band.

This is a self-check aid, not a determination of misconduct. Coverage is limited
to what you upload plus OpenAlex/arXiv abstracts — never the full web.
"""


def _init_sentry(dsn: str, env: str) -> None:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, environment=env, release=APP_VERSION,
                        traces_sample_rate=0.0, send_default_pii=False)
        logger.info("Sentry enabled")
    except ImportError:  # pragma: no cover
        logger.warning("PRISM_SENTRY_DSN set but sentry-sdk is not installed")


def _warmup(app: FastAPI) -> None:
    """Load the embedder on a background thread so readiness reflects reality."""
    def _load() -> None:
        try:
            from modelhub import get_embedder
            get_embedder().embed(["warm-up"])
            app.state.model_loaded = True
            logger.info("embedding model warm")
        except Exception:
            logger.exception("model warm-up failed; paraphrase matching will degrade")
    threading.Thread(target=_load, name="prism-warmup", daemon=True).start()


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.sentry_dsn:
        _init_sentry(settings.sentry_dsn, settings.env)

    configure_cache(settings.embedding_cache_entries)
    matcher = PlagiarismMatcher(
        paraphrase_threshold=settings.paraphrase_threshold,
        confident_threshold=settings.confident_threshold,
        max_source_sentences=settings.max_source_sentences,
        numeric_guard=settings.numeric_guard,
        numeric_guard_gate=settings.numeric_guard_gate,
        confidence_scaling=settings.confidence_scaling,
        confidence_scale_k=settings.confidence_scale_k,
        confidence_scale_pivot=settings.confidence_scale_pivot,
        confidence_ceiling=settings.confidence_ceiling,
    )
    # ADR-0029: job *state* is durable and shared when a DSN is configured; execution
    # stays on the replica that accepted the job either way.
    if settings.database_url:
        from worker.postgres_store import PostgresJobStore
        from worker.usage import PostgresUsageLedger
        store = PostgresJobStore(settings.database_url, max_jobs=settings.max_jobs,
                                 ttl_seconds=settings.job_ttl_seconds, max_size=settings.database_pool_size)
        usage = PostgresUsageLedger(pool=store._pool)
    else:
        from worker.usage import InMemoryUsageLedger
        store = InMemoryJobStore(max_jobs=settings.max_jobs, ttl_seconds=settings.job_ttl_seconds)
        usage = InMemoryUsageLedger()
    executor = BoundedExecutor(max_workers=settings.worker_threads, max_pending=settings.max_pending_jobs)
    fetcher = None
    if settings.academic_fulltext:
        fetcher = FullTextFetcher(
            timeout=settings.academic_fulltext_timeout_seconds,
            max_bytes=settings.academic_fulltext_max_bytes,
            max_pdf_pages=settings.max_pdf_pages,
            max_chars=settings.max_document_chars,
            user_agent=f"PRISM-OriginalityChecker/{APP_VERSION}"
                       + (f" mailto:{settings.contact_email}" if settings.contact_email else ""),
        )
    runner = CheckRunner(
        settings=settings,
        store=store,
        executor=executor,
        matcher=matcher,
        academic_search=partial(
            academic_search,
            providers=settings.academic_providers,
            timeout=settings.academic_timeout_seconds,
            contact_email=settings.contact_email or None,
            s2_api_key=settings.s2_api_key or None,
            fetcher=fetcher,
            fulltext_max_docs=settings.academic_fulltext_max_docs,
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("PRISM %s starting (env=%s, workers=%d, pending_cap=%d, rerank=%s, store=%s)",
                    APP_VERSION, settings.env, settings.worker_threads, settings.max_pending_jobs,
                    settings.rerank, getattr(store, "kind", "memory"))
        if settings.warmup_models:
            _warmup(app)
        yield
        executor.shutdown(wait=False)
        close = getattr(store, "close", None)
        if close:
            close()

    app = FastAPI(
        title="P.R.I.S.M. Originality Checker API",
        description=_DESCRIPTION,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_prod else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.runner = runner
    app.state.rate_limiter = RateLimiter(settings.rate_limit_submissions, settings.rate_limit_window_seconds)
    app.state.auth = JWTVerifier(secret=settings.auth_jwt_secret, jwks_url=settings.auth_jwks_url,
                                 issuer=settings.auth_issuer, audience=settings.auth_audience,
                                 leeway_seconds=settings.auth_leeway_seconds)
    app.state.usage = usage
    app.state.model_loaded = False

    # Order matters: outermost first. Request-id wraps everything so even a 413 carries one.
    app.add_middleware(BodySizeGuardMiddleware, max_bytes=settings.max_request_bytes + 1024 * 1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health.router)
    app.include_router(check.router)
    return app
