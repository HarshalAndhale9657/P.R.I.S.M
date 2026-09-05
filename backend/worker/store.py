"""
P.R.I.S.M. — Job store + result cache
=====================================
``JobStore`` is the seam between the API and wherever job state lives. Today
that is process memory (``InMemoryJobStore``); W7 adds a Postgres
implementation behind the same Protocol so the routers never change.

Both stores are **TTL-bounded**: a manuscript's text is held only as long as
the user could plausibly still be polling for it (``ttl_seconds``), then purged.
That is the "ephemeral-by-default" promise in code, not in a policy document.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, Optional, Protocol, TypeVar


@dataclass
class JobRecord:
    id: str
    status: str = "queued"                       # queued | running | done | error
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class JobStore(Protocol):
    def create(self) -> JobRecord: ...
    def get(self, job_id: str) -> Optional[JobRecord]: ...
    def update(self, job_id: str, **fields: Any) -> None: ...
    def sweep(self, now: Optional[float] = None) -> int: ...
    def __len__(self) -> int: ...


class InMemoryJobStore:
    """Thread-safe, insertion-ordered, bounded by count *and* age."""

    def __init__(self, *, max_jobs: int = 200, ttl_seconds: int = 1800) -> None:
        self.max_jobs = max_jobs
        self.ttl = ttl_seconds
        self._jobs: OrderedDict[str, JobRecord] = OrderedDict()
        self._lock = threading.Lock()

    def create(self) -> JobRecord:
        rec = JobRecord(id=uuid.uuid4().hex)
        with self._lock:
            self._sweep_locked(time.time())
            self._jobs[rec.id] = rec
            while len(self._jobs) > self.max_jobs:
                self._jobs.popitem(last=False)
        return rec

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                return None
            if time.time() - rec.updated > self.ttl:
                del self._jobs[job_id]
                return None
            # Return a snapshot so callers can't mutate shared state outside the lock.
            return JobRecord(id=rec.id, status=rec.status, created=rec.created,
                             updated=rec.updated, result=rec.result, error=rec.error)

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                return
            for k, v in fields.items():
                setattr(rec, k, v)
            rec.updated = time.time()

    def sweep(self, now: Optional[float] = None) -> int:
        with self._lock:
            return self._sweep_locked(time.time() if now is None else now)

    def _sweep_locked(self, now: float) -> int:
        stale = [k for k, r in self._jobs.items() if now - r.updated > self.ttl]
        for k in stale:
            del self._jobs[k]
        return len(stale)

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)


K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Small LRU with per-entry expiry. Used for idempotent re-submits (same content hash)."""

    def __init__(self, *, max_size: int = 64, ttl_seconds: int = 1800) -> None:
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._data: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: K) -> Optional[V]:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            ts, value = item
            if time.time() - ts > self.ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def put(self, key: K, value: V) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_size:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
