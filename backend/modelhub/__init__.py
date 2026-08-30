"""P.R.I.S.M. modelhub — the model registry / cache / version layer (ADR-0015/0016)."""
from .registry import (
    DEFAULT_BI_ENCODER,
    Embedder,
    ModelSpec,
    describe,
    get_cross_encoder,
    get_embedder,
    list_models,
)

__all__ = [
    "DEFAULT_BI_ENCODER",
    "Embedder",
    "ModelSpec",
    "describe",
    "get_cross_encoder",
    "get_embedder",
    "list_models",
]
