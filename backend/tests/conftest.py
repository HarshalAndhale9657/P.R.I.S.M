"""Shared pytest fixtures for the PRISM backend test suite.

Tests are offline and deterministic: `/api/check` is exercised WITHOUT academic
search (no network). Model-dependent (paraphrase/translated) assertions skip
gracefully when sentence-transformers isn't installed.
"""
import sys
import pathlib

# Make `import main` / `from services...` work regardless of pytest's rootdir.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest


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


@pytest.fixture(scope="session")
def client():
    """A FastAPI TestClient over the real app (built once for the session)."""
    import main
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def sample_paper() -> bytes:
    return PAPER_TEXT.encode("utf-8")


@pytest.fixture
def sample_ref() -> bytes:
    return REF_TEXT.encode("utf-8")
