"""
P.R.I.S.M. — Paraphrase scorers for the eval harness
====================================================
The *seam* the detection-lift work (W3 better bi-encoder, W4 cross-encoder rerank,
W5 selective fine-tune) will swap out. Today: cosine over the registered
bi-encoder — the SAME signal the matcher's paraphrase path uses — so a score here
predicts matcher behaviour on the paraphrase pillar.

Kept import-light: numpy is imported lazily inside the function, so `eval.metrics`
and the pair loaders stay usable (and unit-testable) without the model installed.
"""
from __future__ import annotations

from typing import List, Sequence

# Keep in lock-step with the matcher's live paraphrase cutoff.
from services.plagiarism_matcher import PlagiarismMatcher

from .pairs import PairCase

PARAPHRASE_THRESHOLD: float = PlagiarismMatcher().paraphrase_threshold  # 0.66 today


def score_pairs(pairs: Sequence[PairCase], *, model_key: str = "bi-encoder") -> List[float]:
    """Bi-encoder: row-wise cosine similarity (clamped to [0,1]) for each (a, b) pair."""
    if not pairs:
        return []
    import numpy as np

    from modelhub import get_embedder

    embedder = get_embedder(model_key)
    a_emb = np.asarray(embedder.embed([p.a for p in pairs]), dtype=float)
    b_emb = np.asarray(embedder.embed([p.b for p in pairs]), dtype=float)

    a_norm = a_emb / (np.linalg.norm(a_emb, axis=1, keepdims=True) + 1e-12)
    b_norm = b_emb / (np.linalg.norm(b_emb, axis=1, keepdims=True) + 1e-12)
    sims = np.sum(a_norm * b_norm, axis=1)
    return [max(0.0, min(1.0, float(s))) for s in sims]


def score_pairs_cross_encoder(pairs: Sequence[PairCase], *, model_key: str = "cross-encoder-stsb") -> List[float]:
    """Cross-encoder: score each (a, b) pair jointly (W4 — the fix for high-overlap
    negatives the bi-encoder can't separate). Output clamped to [0,1]."""
    if not pairs:
        return []
    from modelhub import get_cross_encoder

    ce = get_cross_encoder(model_key)
    raw = ce.predict([(p.a, p.b) for p in pairs], show_progress_bar=False)
    return [max(0.0, min(1.0, float(s))) for s in raw]


def score(pairs, *, scorer: str = "bi", model_key: str = None) -> List[float]:
    """Dispatch to the chosen scorer. scorer in {"bi", "cross"}."""
    if scorer == "cross":
        return score_pairs_cross_encoder(pairs, model_key=model_key or "cross-encoder-stsb")
    return score_pairs(pairs, model_key=model_key or "bi-encoder")
