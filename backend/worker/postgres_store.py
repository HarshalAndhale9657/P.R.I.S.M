"""
P.R.I.S.M. — Postgres job store (W7, ADR-0029)
==============================================
The second implementation of ``worker.store.JobStore``. Same five methods, same
TTL semantics, same ``JobRecord`` — the routers and the runner do not know which
one they are talking to, and the contract tests in ``tests/test_job_store_contract.py``
run every assertion against both.

What changes when this is the store: job *state* outlives the process and is
visible to every replica, so a client can poll ``GET /api/v1/check/{id}`` on a
different instance from the one that accepted the upload, and a restart no longer
loses every in-flight result. What does **not** change: execution is still the
in-process ``BoundedExecutor`` on the replica that accepted the job. This is the
durable-state half of W7, not a distributed queue.

Design choices, each for a reason:

* **Epoch floats, not timestamps.** ``created``/``updated`` are ``DOUBLE PRECISION``
  seconds exactly as ``JobRecord`` holds them, so the TTL arithmetic is the *same
  expression* as the in-memory store's — no timezone, no clock-source drift between
  the app and the database, and ``sweep(now=...)`` stays injectable for tests.
* **A column whitelist on ``update``.** The runner only ever sets ``status``,
  ``result`` and ``error``. Anything else is a bug, and a ``**fields`` API that
  interpolates keys into SQL is how bugs become injections; unknown keys raise.
* **Schema is created on start, idempotently.** One table, one index, no migration
  framework: the project's rule is no dependency without a measured need, and a
  single ``CREATE TABLE IF NOT EXISTS`` is auditable in a way a migrations folder is not.
* **Ephemeral-by-default still holds.** Rows expire on the same ``ttl_seconds`` as
  memory did, are swept on every ``create`` and on read, and ``max_jobs`` still bounds
  the table by count. Durability buys restarts and replicas, not retention.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from worker.store import JobRecord

_UPDATABLE = frozenset({"status", "result", "error"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    id      TEXT PRIMARY KEY,
    status  TEXT NOT NULL DEFAULT 'queued',
    created DOUBLE PRECISION NOT NULL,
    updated DOUBLE PRECISION NOT NULL,
    result  JSONB,
    error   TEXT
);
CREATE INDEX IF NOT EXISTS {table}_updated_idx ON {table} (updated);
"""


def _validate_table(name: str) -> str:
    if not name.isidentifier() or name.startswith("pg_"):
        raise ValueError(f"unsafe table name {name!r}")
    return name


class PostgresJobStore:
    """``JobStore`` over Postgres via psycopg 3 and a small connection pool."""

    kind = "postgres"

    def __init__(
        self,
        dsn: str,
        *,
        ttl_seconds: int = 1800,
        max_jobs: int = 200,
        table: str = "prism_jobs",
        min_size: int = 1,
        max_size: int = 4,
    ) -> None:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover - guarded by requirements
            raise RuntimeError("PRISM_DATABASE_URL is set but psycopg is not installed") from exc
        self.ttl = ttl_seconds
        self.max_jobs = max_jobs
        self.table = _validate_table(table)
        self._pool = ConnectionPool(dsn, min_size=min_size, max_size=max_size, open=True)
        self._ensure_schema()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(_SCHEMA.format(table=self.table))

    def close(self) -> None:
        self._pool.close()

    # ── JobStore protocol ─────────────────────────────────────────────────────

    def create(self) -> JobRecord:
        rec = JobRecord(id=uuid.uuid4().hex)
        with self._pool.connection() as conn:
            self._sweep_conn(conn, time.time())
            conn.execute(
                f"INSERT INTO {self.table} (id, status, created, updated) VALUES (%s, %s, %s, %s)",
                (rec.id, rec.status, rec.created, rec.updated),
            )
            # Bound by count, oldest first — the same eviction the in-memory store does.
            conn.execute(
                f"DELETE FROM {self.table} WHERE id IN ("
                f"  SELECT id FROM {self.table} ORDER BY created DESC OFFSET %s)",
                (self.max_jobs,),
            )
        return rec

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"SELECT id, status, created, updated, result, error FROM {self.table} WHERE id = %s",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            rec = JobRecord(id=row[0], status=row[1], created=row[2], updated=row[3],
                            result=row[4], error=row[5])
            if time.time() - rec.updated > self.ttl:
                conn.execute(f"DELETE FROM {self.table} WHERE id = %s", (job_id,))
                return None
            return rec

    def update(self, job_id: str, **fields: Any) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {sorted(unknown)}; allowed: {sorted(_UPDATABLE)}")
        if not fields:
            return
        from psycopg.types.json import Jsonb

        assignments = ", ".join(f"{k} = %s" for k in fields)
        values = [Jsonb(v) if k == "result" and v is not None else v for k, v in fields.items()]
        with self._pool.connection() as conn:
            conn.execute(
                f"UPDATE {self.table} SET {assignments}, updated = %s WHERE id = %s",
                (*values, time.time(), job_id),
            )

    def sweep(self, now: Optional[float] = None) -> int:
        with self._pool.connection() as conn:
            return self._sweep_conn(conn, time.time() if now is None else now)

    def _sweep_conn(self, conn, now: float) -> int:
        cur = conn.execute(f"DELETE FROM {self.table} WHERE %s - updated > %s", (now, self.ttl))
        return cur.rowcount or 0

    def __len__(self) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()
            return int(row[0]) if row else 0

    # ── Operator visibility ───────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        p = self._pool.get_stats()
        return {"pool_size": p.get("pool_size"), "pool_available": p.get("pool_available"),
                "requests_waiting": p.get("requests_waiting")}
