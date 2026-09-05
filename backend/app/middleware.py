"""
P.R.I.S.M. — HTTP middleware
============================
* ``RequestIdMiddleware`` — accepts or mints an ``X-Request-ID``, stores it in
  the logging context, and echoes it on the response so a user-reported id can
  be grepped straight out of the logs.
* ``BodySizeGuardMiddleware`` — rejects requests whose declared
  ``Content-Length`` exceeds the aggregate upload cap *before* the body is read.
  The endpoint re-checks actual bytes (a client can lie about the header), but
  this catches the honest oversized upload cheaply.
"""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .logging_config import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response


class BodySizeGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Upload too large — maximum {self.max_bytes // (1024 * 1024)} MB per check."},
            )
        return await call_next(request)
