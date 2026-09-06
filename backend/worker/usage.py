"""
P.R.I.S.M. — Usage ledger: per-user check quota (W7, ADR-0030)
==============================================================
A job store cannot answer "how many checks has this user run today": jobs expire
on a 30-minute TTL, and a daily quota must survive that. So usage is its own
append-only ledger — one row per accepted check — with the same two backends and
the same contract discipline as ``JobStore``.

The ledger records **acceptance**, not completion: a check that fails after being
queued still consumed capacity, and a limit that only counts successes is a limit
that can be gamed by cancelling.

``count`` is a window query, ``sweep`` drops rows older than the longest window
anyone will ask about. Anonymous users are not here at all — they are governed by
the per-IP limiter in ``app.limits``.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Protocol


class UsageLedger(Protocol):
    def record(self, owner: str, now: Optional[float] = None) -> None: ...
    def count(self, owner: str, since: float) -> int: ...
    def sweep(self, older_than: float) -> int: ...


class InMemoryUsageLedger:
    kind = "memory"

    def __init__(self) -> None:
        self._hits: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, owner: str, now: Optional[float] = None) -> None:
        with self._lock:
            self._hits[owner].append(time.time() if now is None else now)

    def count(self, owner: str, since: float) -> int:
        with self._lock:
            return sum(1 for t in self._hits.get(owner, ()) if t >= since)

    def sweep(self, older_than: float) -> int:
        removed = 0
        with self._lock:
            for owner in list(self._hits):
                kept = [t for t in self._hits[owner] if t >= older_than]
                removed += len(self._hits[owner]) - len(kept)
                if kept:
                    self._hits[owner] = kept
                else:
                    del self._hits[owner]
        return removed


_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    owner TEXT NOT NULL,
    at    DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS {table}_owner_at_idx ON {table} (owner, at);
"""


class PostgresUsageLedger:
    """Shares nothing with ``PostgresJobStore`` but the pool: pass one in to reuse it."""

    kind = "postgres"

    def __init__(self, dsn: str = "", *, pool: Any = None, table: str = "prism_usage",
                 min_size: int = 1, max_size: int = 4) -> None:
        from worker.postgres_store import _validate_table

        self.table = _validate_table(table)
        self._owns_pool = pool is None
        if pool is None:
            from psycopg_pool import ConnectionPool
            pool = ConnectionPool(dsn, min_size=min_size, max_size=max_size, open=True)
        self._pool = pool
        with self._pool.connection() as conn:
            conn.execute(_SCHEMA.format(table=self.table))

    def close(self) -> None:
        if self._owns_pool:
            self._pool.close()

    def record(self, owner: str, now: Optional[float] = None) -> None:
        with self._pool.connection() as conn:
            conn.execute(f"INSERT INTO {self.table} (owner, at) VALUES (%s, %s)",
                         (owner, time.time() if now is None else now))

    def count(self, owner: str, since: float) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {self.table} WHERE owner = %s AND at >= %s",
                               (owner, since)).fetchone()
            return int(row[0]) if row else 0

    def sweep(self, older_than: float) -> int:
        with self._pool.connection() as conn:
            cur = conn.execute(f"DELETE FROM {self.table} WHERE at < %s", (older_than,))
            return cur.rowcount or 0


__all__ = ["UsageLedger", "InMemoryUsageLedger", "PostgresUsageLedger"]
