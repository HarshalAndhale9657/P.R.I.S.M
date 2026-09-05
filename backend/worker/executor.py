"""
P.R.I.S.M. — Bounded executor
=============================
``concurrent.futures.ThreadPoolExecutor`` has an unbounded queue: under a flood
every submission is accepted and its payload sits in memory until a worker gets
to it. ``BoundedExecutor`` adds a hard cap on *pending* work so the API can
answer ``503 Retry-After`` instead of swallowing RAM.

Submitted callables run with a copy of the submitting request's ``contextvars``
so job log lines keep the originating ``request_id``.
"""
from __future__ import annotations

import contextvars
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict


class QueueFull(RuntimeError):
    """Raised by submit() when the pending queue is at capacity."""


class BoundedExecutor:
    def __init__(self, *, max_workers: int, max_pending: int, thread_name_prefix: str = "prism-check") -> None:
        self.max_workers = max_workers
        self.max_pending = max_pending
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=thread_name_prefix)
        self._lock = threading.Lock()
        self._pending = 0
        self._running = 0

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        with self._lock:
            if self._pending >= self.max_pending:
                raise QueueFull(f"{self._pending} checks already queued")
            self._pending += 1
        ctx = contextvars.copy_context()

        def _run() -> Any:
            with self._lock:
                self._pending -= 1
                self._running += 1
            try:
                return ctx.run(fn, *args, **kwargs)
            finally:
                with self._lock:
                    self._running -= 1

        try:
            return self._pool.submit(_run)
        except Exception:
            with self._lock:
                self._pending -= 1
            raise

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"running": self._running, "pending": self._pending, "capacity": self.max_pending}

    def shutdown(self, wait: bool = False) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=True)
