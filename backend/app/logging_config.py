"""
P.R.I.S.M. — Logging
====================
One configuration point. Two formats:

* ``text`` — human-readable, for local development.
* ``json`` — one object per line with ``request_id`` / ``job_id`` fields, for
  production log shipping.

Correlation ids travel in ``contextvars`` so any log line emitted while a
request or a job is being processed carries them without threading arguments
through every function. Worker threads copy the context at submit time (see
``worker.executor``), so a job's log lines carry the id of the request that
created it.
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Optional

request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
job_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("job_id", default=None)


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        record.job_id = job_id_var.get() or "-"
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "job_id": getattr(record, "job_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_TEXT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | rid=%(request_id)s job=%(job_id)s | %(message)s"


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Idempotent: replaces handlers on the root logger."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())
    handler.setFormatter(_JsonFormatter() if fmt == "json" else logging.Formatter(_TEXT_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)
    # Uvicorn's access log is noisy and lacks our fields; keep its error log. The HF/httpx
    # stack logs every model-file HEAD request at INFO during warm-up — not operational signal.
    for noisy in ("uvicorn.access", "httpx", "httpcore", "huggingface_hub", "urllib3", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
