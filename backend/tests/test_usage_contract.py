"""The ``UsageLedger`` contract, against every implementation (ADR-0030).

Same discipline as the job-store contract: memory always, Postgres when
``PRISM_TEST_DATABASE_URL`` is set (CI supplies it and fails if skipped).
"""
import os
import time

import pytest

from worker.usage import InMemoryUsageLedger

PG_DSN = os.environ.get("PRISM_TEST_DATABASE_URL")


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.skipif(
    not PG_DSN, reason="PRISM_TEST_DATABASE_URL not set - Postgres contract verified in CI"))])
def ledger(request):
    if request.param == "memory":
        yield InMemoryUsageLedger()
        return
    from worker.usage import PostgresUsageLedger
    led = PostgresUsageLedger(PG_DSN, table=f"prism_usage_test_{os.getpid()}")
    with led._pool.connection() as conn:
        conn.execute(f"DELETE FROM {led.table}")
    yield led
    with led._pool.connection() as conn:
        conn.execute(f"DROP TABLE IF EXISTS {led.table}")
    led.close()


def test_count_is_zero_for_an_unknown_owner(ledger):
    assert ledger.count("nobody", since=0) == 0


def test_record_then_count_within_the_window(ledger):
    now = time.time()
    ledger.record("a", now=now - 10)
    ledger.record("a", now=now - 5)
    ledger.record("b", now=now - 5)
    assert ledger.count("a", since=now - 60) == 2
    assert ledger.count("b", since=now - 60) == 1


def test_count_respects_the_window_boundary(ledger):
    now = time.time()
    ledger.record("a", now=now - 100)
    ledger.record("a", now=now - 1)
    assert ledger.count("a", since=now - 50) == 1
    assert ledger.count("a", since=now - 200) == 2


def test_sweep_drops_old_rows_and_reports_how_many(ledger):
    now = time.time()
    for t in (now - 1000, now - 900, now - 1):
        ledger.record("a", now=t)
    assert ledger.sweep(older_than=now - 500) == 2
    assert ledger.count("a", since=0) == 1


def test_owners_are_isolated(ledger):
    now = time.time()
    for _ in range(3):
        ledger.record("a", now=now)
    assert ledger.count("b", since=0) == 0 and ledger.count("a", since=0) == 3


@pytest.mark.skipif(not PG_DSN, reason="PRISM_TEST_DATABASE_URL not set")
def test_postgres_ledger_can_share_the_job_store_pool():
    """The factory hands the ledger the job store's pool; nothing should be opened twice."""
    from worker.postgres_store import PostgresJobStore
    from worker.usage import PostgresUsageLedger
    store = PostgresJobStore(PG_DSN, table=f"prism_jobs_share_{os.getpid()}")
    led = PostgresUsageLedger(pool=store._pool, table=f"prism_usage_share_{os.getpid()}")
    try:
        led.record("a")
        assert led.count("a", since=0) == 1
        assert led._owns_pool is False
        led.close()                       # must NOT close the shared pool ...
        assert not store._pool.closed
        assert len(store) == 0            # ... which the store can still use
    finally:
        with store._pool.connection() as conn:
            conn.execute(f"DROP TABLE IF EXISTS {led.table}")
            conn.execute(f"DROP TABLE IF EXISTS {store.table}")
        store.close()
