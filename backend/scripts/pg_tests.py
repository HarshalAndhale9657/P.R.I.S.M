"""
Run the test suite against a real, embedded PostgreSQL (ADR-0031 follow-up to ADR-0029).

    python scripts/pg_tests.py                 # whole suite, no Postgres skips
    python scripts/pg_tests.py tests/test_job_store_contract.py -k owner

CI runs the Postgres halves of the contract suites against a `postgres:16` service
container and fails if they were skipped. Locally they skip unless
`PRISM_TEST_DATABASE_URL` is set — this script sets it for you by starting a
self-contained server from the `pgserver` wheel (a dev dependency; no Docker, no
system install), running pytest with the DSN in the environment, and tearing the
server down. The data directory lives under the OS temp dir and is discarded.

Why this exists: a "verified in CI" claim is only checkable if a developer can
reproduce it at their desk. The first time this was needed, a teardown bug in one
Postgres-only test cost a red CI run that could not be reproduced without it.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    try:
        import pgserver
    except ImportError:
        print("pgserver is not installed:  pip install -r requirements-dev.txt", file=sys.stderr)
        return 2
    data_dir = pathlib.Path(tempfile.gettempdir()) / "prism-pg-tests"
    server = pgserver.get_server(str(data_dir))
    try:
        dsn = server.get_uri()
        print(f"[pg_tests] embedded postgres at {dsn.rsplit('@', 1)[-1]}")
        env = dict(os.environ, PRISM_TEST_DATABASE_URL=dsn)
        args = argv or ["tests"]
        return subprocess.run([sys.executable, "-m", "pytest", *args, "-rs"], env=env, cwd=HERE).returncode
    finally:
        server.cleanup()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
