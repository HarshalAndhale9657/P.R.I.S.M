"""
P.R.I.S.M. — Request/job context variables
==========================================
The two ``ContextVar``s that stamp every log line with the request and job it
belongs to. They live here, in the dependency-free ``utils`` layer, because the
worker needs ``job_id_var`` and the HTTP layer needs ``request_id_var`` — and
neither may import the other. (``worker.runner`` used to import them from
``app.logging_config``, which pulls in ``app/__init__`` → ``factory`` → ``worker``:
a circular import that only stayed hidden because pytest happened to collect an
``app``-importing test module first. ADR-0029.)
"""
from __future__ import annotations

import contextvars
from typing import Optional

request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
job_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("job_id", default=None)

__all__ = ["request_id_var", "job_id_var"]
