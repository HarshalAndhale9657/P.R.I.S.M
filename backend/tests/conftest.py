"""Shared pytest fixtures for the PRISM backend test suite.

Tests are offline and deterministic: `/api/v1/check` is exercised WITHOUT
academic search (no network). Model-dependent (paraphrase/translated)
assertions skip gracefully when sentence-transformers isn't installed.

The app under test is built by the factory with explicit `Settings`, never from
process environment — so a developer's `.env` can't change test behaviour.
"""
import pathlib
import sys

# Make `import app` / `from services...` work regardless of pytest's rootdir.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


def _model_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


MODEL_AVAILABLE = _model_available()
requires_model = pytest.mark.skipif(
    not MODEL_AVAILABLE, reason="sentence-transformers not installed"
)

# ── Sample documents ──────────────────────────────────────────────────────────
# Paragraph 2 is a verbatim copy of reference paragraph 1 (always detectable,
# no model needed). Paragraph 3 paraphrases reference paragraph 2 (needs model).
PAPER_TEXT = (
    "In this paper we study machine learning methods for text analysis and their behaviour across settings.\n\n"
    "The transformer architecture relies entirely on self-attention mechanisms to draw global dependencies between input and output sequences.\n\n"
    "Clustering techniques based on density can infer how many groups exist in the data without needing a fixed number to be specified in advance.\n\n"
    "Our own contribution is a small user study conducted with twenty volunteers over two weeks."
)
REF_TEXT = (
    "The transformer architecture relies entirely on self-attention mechanisms to draw global dependencies between input and output sequences.\n\n"
    "Density-based clustering automatically determines the number of clusters present in a dataset without requiring a preset count parameter.\n\n"
    "Empirical evaluation on standard benchmarks shows consistent gains over recurrent baselines."
)


def make_settings(**overrides):
    """Test settings: no .env, no warm-up, generous rate limit, small queue."""
    from app.settings import Settings
    base = dict(env="test", warmup_models=False, rate_limit_submissions=1000,
                worker_threads=2, max_pending_jobs=8, log_level="WARNING")
    base.update(overrides)
    return Settings(_env_file=None, **base)


def make_client(**overrides):
    """A TestClient over a freshly built app (lifespan active)."""
    from fastapi.testclient import TestClient

    from app import create_app
    return TestClient(create_app(make_settings(**overrides)))


@pytest.fixture(scope="session")
def client():
    with make_client() as c:
        yield c


@pytest.fixture
def sample_paper() -> bytes:
    return PAPER_TEXT.encode("utf-8")


@pytest.fixture
def sample_ref() -> bytes:
    return REF_TEXT.encode("utf-8")
