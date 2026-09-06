"""
P.R.I.S.M. — /api/v1/check
==========================
Submit an originality check (202 + job id) and poll it. Validation that can
fail fast (file type, per-file and aggregate size, reference count) happens
here synchronously; everything expensive runs in the worker.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.auth import Principal, current_principal
from app.limits import enforce_rate_limit
from app.schemas import ErrorResponse, JobStatusResponse, SubmitCheckResponse
from worker import CheckRequest, CheckRunner, QueueFull

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["check"])

_ALLOWED_EXT = (".pdf", ".txt", ".md")
_ALLOWED_MIME = ("application/pdf", "text/plain", "text/markdown")


def _is_supported(file: UploadFile) -> bool:
    name = (file.filename or "").lower()
    return name.endswith(_ALLOWED_EXT) or (file.content_type or "") in _ALLOWED_MIME


def _mb(n: int) -> int:
    return n // (1024 * 1024)


@router.post(
    "/check",
    status_code=202,
    response_model=SubmitCheckResponse,
    responses={
        400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 402: {"model": ErrorResponse},
        413: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 503: {"model": ErrorResponse},
    },
    summary="Submit an originality check",
)
async def submit_check(
    request: Request,
    principal: Optional[Principal] = Depends(current_principal),
    file: UploadFile = File(..., description="The manuscript to check (PDF, TXT or MD)."),
    references: List[UploadFile] = File(default=[], description="Reference sources to compare against."),
    use_academic: bool = Form(default=False, description="Also search OpenAlex + arXiv abstracts."),
):
    settings = request.app.state.settings
    runner: CheckRunner = request.app.state.runner

    # Signed-in users are governed by their quota; anonymous ones by the per-IP limiter (ADR-0030).
    if principal is None:
        enforce_rate_limit(request)
    else:
        _enforce_quota(request, principal)

    if not _is_supported(file):
        raise HTTPException(status_code=400, detail="Only PDF, TXT or Markdown files are supported.")
    paper_bytes = await file.read()
    if not paper_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    if len(paper_bytes) > settings.max_file_bytes:
        raise HTTPException(status_code=413, detail=f"File too large — maximum {_mb(settings.max_file_bytes)} MB.")
    if not references and not (use_academic and settings.academic_enabled):
        raise HTTPException(
            status_code=400,
            detail="Upload at least one reference source, or enable academic-database search.",
        )

    base_warnings: List[str] = []
    if len(references) > settings.max_reference_files:
        base_warnings.append(
            f"Only the first {settings.max_reference_files} of {len(references)} reference files were used."
        )

    total = len(paper_bytes)
    refs: List[Tuple[str, bytes]] = []
    for i, ref in enumerate(references[: settings.max_reference_files]):
        label = ref.filename or f"Source {i + 1}"
        if not _is_supported(ref):
            base_warnings.append(f"Skipped '{label}': unsupported file type.")
            continue
        raw = await ref.read()
        if not raw:
            base_warnings.append(f"Skipped '{label}': empty file.")
            continue
        if len(raw) > settings.max_file_bytes:
            base_warnings.append(f"Skipped '{label}': exceeds {_mb(settings.max_file_bytes)} MB limit.")
            continue
        total += len(raw)
        if total > settings.max_request_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload too large — maximum {_mb(settings.max_request_bytes)} MB per check "
                       f"(paper plus references).",
            )
        refs.append((label, raw))

    req = CheckRequest(
        paper=(file.filename or "document", paper_bytes),
        references=refs,
        use_academic=use_academic and settings.academic_enabled,
        base_warnings=base_warnings,
    )
    try:
        rec = runner.submit(req, owner=principal.user_id if principal else None)
    except QueueFull:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={"detail": "The checker is busy right now. Please retry in about 30 seconds."},
        )
    if principal is not None:
        # Acceptance is what counts against the quota, not completion (see worker.usage).
        request.app.state.usage.record(principal.user_id)
    return SubmitCheckResponse(job_id=rec.id, status="queued", status_url=f"/api/v1/check/{rec.id}")


def _enforce_quota(request: Request, principal: Principal) -> None:
    settings = request.app.state.settings
    if settings.quota_checks <= 0:
        return
    import time as _time
    since = _time.time() - settings.quota_window_seconds
    used = request.app.state.usage.count(principal.user_id, since)
    if used >= settings.quota_checks:
        hours = max(1, settings.quota_window_seconds // 3600)
        raise HTTPException(
            status_code=402,
            detail=f"You have used all {settings.quota_checks} checks for the last {hours} hours. "
                   f"Upgrade your plan to run more.",
            headers={"X-Quota-Limit": str(settings.quota_checks), "X-Quota-Used": str(used)},
        )


@router.get(
    "/check/{job_id}",
    response_model=JobStatusResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    summary="Poll a submitted check",
)
async def check_status(job_id: str, request: Request,
                       principal: Optional[Principal] = Depends(current_principal)):
    runner: CheckRunner = request.app.state.runner
    rec = runner.status(job_id)
    # A job that belongs to someone else reads as non-existent — 404, never 403 (ADR-0030).
    if rec is None or (rec.owner is not None and (principal is None or principal.user_id != rec.owner)):
        raise HTTPException(status_code=404, detail="Unknown or expired job id.")
    return JobStatusResponse(job_id=rec.id, status=rec.status, result=rec.result, error=rec.error)
