"""
P.R.I.S.M. — health endpoints
=============================
* ``GET /health``        — liveness + a small operational snapshot. Always 200 if
  the process is up (a load balancer should not restart us while the model is
  still loading).
* ``GET /health/ready``  — readiness. 503 until the embedding model is loaded
  when warm-up is enabled; otherwise 200 (the model loads lazily on first use).
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.schemas import EmbeddingCacheStats, HealthResponse, QueueStats
from app.settings import APP_VERSION
from services.embedding_cache import get_cache

router = APIRouter(tags=["health"])


def _snapshot(request: Request) -> HealthResponse:
    st = request.app.state
    model_loaded = bool(getattr(st, "model_loaded", False))
    status = "ok"
    if st.settings.warmup_models and not model_loaded:
        status = "starting"
    cache = get_cache()
    return HealthResponse(
        status=status,
        version=APP_VERSION,
        env=st.settings.env,
        model_loaded=model_loaded,
        rerank_enabled=st.settings.rerank,
        queue=QueueStats(**st.runner.executor.stats()),
        jobs_in_memory=len(st.runner.store),
        store=getattr(st.runner.store, "kind", "memory"),
        auth=("required" if st.settings.auth_required else ("optional" if st.auth.configured else "off")),
        embedding_cache=EmbeddingCacheStats(entries=len(cache), capacity=cache.max_entries,
                                            **cache.stats().as_dict()),
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness + operational snapshot")
async def health(request: Request):
    return _snapshot(request)


@router.get("/health/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}},
            summary="Readiness (503 while models warm up)")
async def ready(request: Request):
    snap = _snapshot(request)
    if snap.status == "starting":
        return JSONResponse(status_code=503, content=snap.model_dump())
    return snap


@router.get("/", include_in_schema=False)
async def root(request: Request):
    return _snapshot(request)
