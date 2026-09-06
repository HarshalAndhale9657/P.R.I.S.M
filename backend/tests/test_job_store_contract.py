"""The ``JobStore`` contract, run against every implementation (ADR-0029).

The in-memory store always runs. The Postgres store runs when
``PRISM_TEST_DATABASE_URL`` points at a database — CI provides one as a service
container — and is *skipped, visibly*, otherwise. A skipped Postgres run is not a
green Postgres run; CI is where that claim is made.
"""
import os
import time

import pytest

from worker.store import InMemoryJobStore, JobRecord

PG_DSN = os.environ.get("PRISM_TEST_DATABASE_URL")


def _postgres(**kw):
    from worker.postgres_store import PostgresJobStore
    store = PostgresJobStore(PG_DSN, table=f"prism_jobs_test_{os.getpid()}", **kw)
    # Every test starts from an empty table; the pool is closed by the fixture.
    with store._pool.connection() as conn:
        conn.execute(f"DELETE FROM {store.table}")
    return store


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.skipif(
    not PG_DSN, reason="PRISM_TEST_DATABASE_URL not set - Postgres contract verified in CI"))])
def make_store(request):
    """Factory fixture: ``make_store(ttl_seconds=..., max_jobs=...)`` for the current backend."""
    created = []

    def factory(**kw):
        kw.setdefault("ttl_seconds", 1800)
        kw.setdefault("max_jobs", 200)
        store = InMemoryJobStore(**kw) if request.param == "memory" else _postgres(**kw)
        created.append(store)
        return store

    yield factory
    for store in created:
        close = getattr(store, "close", None)
        if close:
            if getattr(store, "kind", "") == "postgres":
                with store._pool.connection() as conn:
                    conn.execute(f"DROP TABLE IF EXISTS {store.table}")
            close()


# ── The contract ──────────────────────────────────────────────────────────────

def test_create_returns_a_queued_record_that_get_reads_back(make_store):
    store = make_store()
    rec = store.create()
    assert isinstance(rec, JobRecord) and rec.status == "queued" and len(rec.id) == 32
    got = store.get(rec.id)
    assert got is not None
    assert (got.id, got.status, got.result, got.error) == (rec.id, "queued", None, None)
    assert got.created == pytest.approx(rec.created, abs=1e-3)


def test_get_returns_a_snapshot_not_shared_state(make_store):
    """Mutating what ``get`` returned must not change what the store holds."""
    store = make_store()
    rec = store.create()
    snap = store.get(rec.id)
    snap.status = "tampered"
    assert store.get(rec.id).status == "queued"


def test_unknown_job_is_none(make_store):
    assert make_store().get("does-not-exist") is None


def test_update_changes_status_result_and_error_and_bumps_updated(make_store):
    store = make_store()
    rec = store.create()
    before = store.get(rec.id).updated
    time.sleep(0.01)
    store.update(rec.id, status="done", result={"matches": [{"similarity": 0.91, "text": "ünïcode ✓"}],
                                              "nested": {"list": [1, 2.5, None, True]}})
    got = store.get(rec.id)
    assert got.status == "done"
    assert got.result["matches"][0]["text"] == "ünïcode ✓"
    assert got.result["nested"]["list"] == [1, 2.5, None, True]
    assert got.updated > before

    store.update(rec.id, status="error", error="Server busy.")
    got = store.get(rec.id)
    assert (got.status, got.error) == ("error", "Server busy.")
    assert got.result is not None, "an error update must not wipe an earlier result"


def test_update_of_an_unknown_job_is_a_silent_no_op(make_store):
    store = make_store()
    store.update("nope", status="done")     # must not raise
    assert len(store) == 0


def test_expired_jobs_are_invisible_and_swept(make_store):
    store = make_store(ttl_seconds=0)
    rec = store.create()
    time.sleep(0.02)
    assert store.get(rec.id) is None, "a job past its TTL must read as gone"
    assert len(store) == 0, "reading an expired job purges it"


def test_sweep_reports_how_many_it_removed_and_accepts_an_injected_clock(make_store):
    store = make_store(ttl_seconds=100)
    a, b = store.create(), store.create()
    assert store.sweep(now=time.time() + 50) == 0
    assert store.sweep(now=time.time() + 1000) == 2
    assert store.get(a.id) is None and store.get(b.id) is None


def test_the_store_is_bounded_by_count_oldest_first(make_store):
    store = make_store(max_jobs=3)
    ids = []
    for _ in range(5):
        ids.append(store.create().id)
        time.sleep(0.002)               # distinct `created` so "oldest" is well defined
    assert len(store) == 3
    assert store.get(ids[0]) is None and store.get(ids[1]) is None
    assert all(store.get(i) is not None for i in ids[2:])


def test_len_counts_live_jobs(make_store):
    store = make_store()
    assert len(store) == 0
    store.create()
    store.create()
    assert len(store) == 2


# ── Postgres-only guarantees ──────────────────────────────────────────────────

@pytest.mark.skipif(not PG_DSN, reason="PRISM_TEST_DATABASE_URL not set")
def test_postgres_rejects_unknown_update_fields():
    """``**fields`` are column names in SQL; anything outside the whitelist must raise, not interpolate."""
    store = _postgres()
    try:
        rec = store.create()
        with pytest.raises(ValueError):
            store.update(rec.id, status="done", owner="x; DROP TABLE prism_jobs")
        assert store.get(rec.id).status == "queued"
    finally:
        with store._pool.connection() as conn:
            conn.execute(f"DROP TABLE IF EXISTS {store.table}")
        store.close()


@pytest.mark.skipif(not PG_DSN, reason="PRISM_TEST_DATABASE_URL not set")
def test_postgres_state_survives_a_new_store_instance():
    """The point of durability: a second process sees what the first wrote."""
    first = _postgres()
    rec = first.create()
    first.update(rec.id, status="done", result={"ok": True})
    table = first.table
    first.close()
    from worker.postgres_store import PostgresJobStore
    second = PostgresJobStore(PG_DSN, table=table)
    try:
        got = second.get(rec.id)
        assert got is not None and got.status == "done" and got.result == {"ok": True}
    finally:
        with second._pool.connection() as conn:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        second.close()


def test_unsafe_table_names_are_refused():
    from worker.postgres_store import _validate_table
    for bad in ("jobs; drop", "pg_catalog", "a-b", ""):
        with pytest.raises(ValueError):
            _validate_table(bad)
    assert _validate_table("prism_jobs") == "prism_jobs"


# ── Ownership (ADR-0030) ──────────────────────────────────────────────────────

def test_owner_round_trips_and_defaults_to_anonymous(make_store):
    store = make_store()
    anon = store.create()
    mine = store.create(owner="user-a")
    assert store.get(anon.id).owner is None
    assert store.get(mine.id).owner == "user-a"
    store.update(mine.id, status="done", result={"ok": True})
    assert store.get(mine.id).owner == "user-a", "updates must not disturb ownership"
