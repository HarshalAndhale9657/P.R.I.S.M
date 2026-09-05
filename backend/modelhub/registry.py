"""
P.R.I.S.M. — Model registry (the "models/ layer" of ADR-0015/0016)
==================================================================
One place to *name, version, lazily load and cache* every ML model the pipeline
uses, so swapping a model (W3: MiniLM -> bge/gte ONNX; W4: add a cross-encoder
reranker) is a registry edit, not a scattered import hunt.

NB: implemented as `modelhub/` rather than `models/` because `backend/models.py`
(legacy Pydantic models) already owns that name.

Today it registers one model — the sentence bi-encoder — and delegates loading to
the existing thread-safe singleton in `services.local_embeddings`, so there is a
single cached instance across the app. New entries (cross-encoder, AI detector)
slot into `_REGISTRY` with their own loader.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Dict, List, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    """Stable, reproducible description of one model."""
    key: str        # our stable handle, e.g. "bi-encoder"
    name: str       # underlying model id, e.g. "paraphrase-multilingual-MiniLM-L12-v2"
    kind: str       # "bi-encoder" | "cross-encoder" | "ai-detector"
    revision: str   # version/pin for reproducibility & cache-busting
    backend: str    # "sentence-transformers" | "onnx" | "torch"
    note: str = ""


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: List[str]): ...


# ── Registry ──────────────────────────────────────────────────────────────────
# Model *quality* is evaluated via sentence-transformers (torch); ONNX packaging
# of the winner is a W6 deployment step. bi-encoders are scored by cosine;
# cross-encoders score a pair directly (the W4 fix for high-overlap negatives).
_REGISTRY: Dict[str, ModelSpec] = {
    "bi-encoder": ModelSpec(
        key="bi-encoder", name="paraphrase-multilingual-MiniLM-L12-v2",
        kind="bi-encoder", revision="minilm-l12-v2", backend="sentence-transformers",
        note="Current default. Multilingual (enables translated matches). The W2 baseline.",
    ),
    # W3 candidates (stronger English bi-encoders; torch now, ONNX at W6).
    "bi-encoder-mpnet": ModelSpec(
        key="bi-encoder-mpnet", name="sentence-transformers/all-mpnet-base-v2",
        kind="bi-encoder", revision="mpnet-base-v2", backend="sentence-transformers",
        note="Strong English ST model — W3 candidate.",
    ),
    "bi-encoder-bge": ModelSpec(
        key="bi-encoder-bge", name="BAAI/bge-base-en-v1.5",
        kind="bi-encoder", revision="bge-base-en-v1.5", backend="sentence-transformers",
        note="BGE base (English) — W3 candidate. Used symmetrically (no instruction) for similarity.",
    ),
    # W4 candidate (cross-encoder reranker — the real fix for PAWS-style pairs).
    "cross-encoder-stsb": ModelSpec(
        key="cross-encoder-stsb", name="cross-encoder/stsb-roberta-base",
        kind="cross-encoder", revision="stsb-roberta-base", backend="sentence-transformers",
        note="Pretrained STS cross-encoder — scores a pair jointly; W4 candidate.",
    ),
    "cross-encoder-qqp": ModelSpec(
        key="cross-encoder-qqp", name="cross-encoder/quora-roberta-base",
        kind="cross-encoder", revision="quora-roberta-base", backend="sentence-transformers",
        note="Pretrained paraphrase (Quora) cross-encoder — W4 candidate.",
    ),
}

DEFAULT_BI_ENCODER = "bi-encoder"

_INSTANCES: Dict[str, Embedder] = {}
_CE_INSTANCES: Dict[str, object] = {}
_LOCK = threading.Lock()


class _STEmbedder:
    """Adapter: a sentence-transformers model exposing the Embedder protocol."""
    def __init__(self, name: str) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(name)

    def embed(self, texts: List[str]):
        return self._model.encode(texts, show_progress_bar=False, convert_to_numpy=True)


def list_models() -> List[ModelSpec]:
    return list(_REGISTRY.values())


def describe(key: str) -> ModelSpec:
    if key not in _REGISTRY:
        raise KeyError(f"Unknown model key {key!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[key]


def get_embedder(key: str = DEFAULT_BI_ENCODER) -> Embedder:
    """Return a cached bi-encoder for `key` (thread-safe, lazily loaded)."""
    inst = _INSTANCES.get(key)
    if inst is not None:
        return inst
    with _LOCK:
        inst = _INSTANCES.get(key)
        if inst is None:
            spec = describe(key)
            if spec.kind != "bi-encoder":
                raise ValueError(f"{key!r} is a {spec.kind}, not a bi-encoder (use get_cross_encoder).")
            logger.info("[modelhub] loading bi-encoder %r (%s)", key, spec.name)
            # The default key reuses the shared singleton; others load by name.
            if key == "bi-encoder":
                from services.local_embeddings import get_instance
                inst = get_instance()
            else:
                inst = _STEmbedder(spec.name)
            _INSTANCES[key] = inst
        return inst


def get_cross_encoder(key: str):
    """Return a cached sentence-transformers CrossEncoder for `key`."""
    ce = _CE_INSTANCES.get(key)
    if ce is not None:
        return ce
    with _LOCK:
        ce = _CE_INSTANCES.get(key)
        if ce is None:
            spec = describe(key)
            if spec.kind != "cross-encoder":
                raise ValueError(f"{key!r} is a {spec.kind}, not a cross-encoder.")
            from sentence_transformers import CrossEncoder
            logger.info("[modelhub] loading cross-encoder %r (%s)", key, spec.name)
            ce = CrossEncoder(spec.name)
            _CE_INSTANCES[key] = ce
        return ce
