"""
P.R.I.S.M. — Sentence-embedding cache (ADR-0023)
=================================================
Embedding is the dominant cost of a check: measured on a 12-thread CPU,
**6 000 source sentences take 77–93 s**, which is most of the wall time once
open-access full text is in play (ADR-0021). Downloads are not the bottleneck;
the forward pass is.

The same sentences are embedded again and again across checks:

* **Re-check after edits** — the product's core loop (edit → check again). The
  manuscript changes; the sources are byte-identical. Today that re-embeds
  everything; with this cache it is nearly free.
* **Popular sources** — the same OA paper is retrieved for many manuscripts.
* **Repeated boilerplate** — methods and definition sentences recur verbatim.

Design notes:

* Keyed by ``(model_key, sha1(text))`` — text, not source identity, because the
  relevance budget (ADR-0020) chooses a *different subset* of a source's sentences
  for each manuscript. A per-source key would miss on every new document.
* Stores read-only ``float32`` vectors. A 384-dim vector is ~1.5 KB, so the
  default 50 000 entries is roughly 75 MB — bounded, and sized in *entries* rather
  than bytes so the ceiling does not move when the model's dimensionality does.
* Thread-safe; several checks embed concurrently in the worker pool.
* Pure and optional: `embed_cached` falls back to a plain call if anything goes
  wrong, so a cache bug can never break a check.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MAX_ENTRIES = 50_000


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def lookups(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return (self.hits / self.lookups) if self.lookups else 0.0

    def as_dict(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "evictions": self.evictions,
                "hit_rate": round(self.hit_rate, 4)}


class EmbeddingCache:
    """Process-wide LRU of sentence embeddings, keyed by (model, text)."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self.max_entries = max_entries
        self._data: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()
        self._stats = CacheStats()

    @staticmethod
    def key(model_key: str, text: str) -> str:
        return f"{model_key}:{hashlib.sha1(text.encode('utf-8')).hexdigest()}"

    def get_many(self, model_key: str, texts: Sequence[str]) -> List[Optional[np.ndarray]]:
        out: List[Optional[np.ndarray]] = []
        with self._lock:
            for t in texts:
                v = self._data.get(self.key(model_key, t))
                if v is None:
                    self._stats.misses += 1
                else:
                    self._data.move_to_end(self.key(model_key, t))
                    self._stats.hits += 1
                out.append(v)
        return out

    def put_many(self, model_key: str, texts: Sequence[str], vectors: np.ndarray) -> None:
        if len(texts) != len(vectors):
            raise ValueError("texts and vectors must be the same length")
        with self._lock:
            for t, v in zip(texts, vectors):
                arr = np.asarray(v, dtype=np.float32)
                arr.setflags(write=False)          # shared by reference; never mutated in place
                self._data[self.key(model_key, t)] = arr
                self._data.move_to_end(self.key(model_key, t))
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)
                self._stats.evictions += 1

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(self._stats.hits, self._stats.misses, self._stats.evictions)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._stats = CacheStats()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


_CACHE: Optional[EmbeddingCache] = None
_CACHE_LOCK = threading.Lock()


def get_cache(max_entries: int = DEFAULT_MAX_ENTRIES) -> EmbeddingCache:
    """The process-wide cache. `max_entries` applies on first use; `configure_cache` resizes."""
    global _CACHE
    if _CACHE is None:
        with _CACHE_LOCK:
            if _CACHE is None:
                _CACHE = EmbeddingCache(max_entries=max_entries)
    return _CACHE


def configure_cache(max_entries: int) -> EmbeddingCache:
    """Set the process-wide cache size at startup (0 disables caching entirely)."""
    global _CACHE
    with _CACHE_LOCK:
        _CACHE = EmbeddingCache(max_entries=max(0, max_entries))
    return _CACHE


def embed_cached(
    embed_fn: Callable[[List[str]], np.ndarray],
    texts: Sequence[str],
    *,
    model_key: str,
    cache: Optional[EmbeddingCache] = None,
) -> np.ndarray:
    """Embed `texts`, computing only what is not already cached.

    Duplicates within one call are embedded once. Returns a (len(texts), dim) array in
    the original order. Any failure inside the cache path degrades to a plain
    `embed_fn(texts)` — the cache must never be able to break a check.
    """
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    if cache is None and get_cache().max_entries == 0:      # caching disabled by configuration
        return np.asarray(embed_fn(list(texts)), dtype=np.float32)
    # `is None`, never `or`: this class defines __len__, so an *empty* cache is falsy and
    # `cache or get_cache()` would silently discard an injected one and write to the global.
    if cache is None:
        cache = get_cache()
    try:
        cached = cache.get_many(model_key, texts)
        missing_order: List[str] = []
        seen: set[str] = set()
        for t, v in zip(texts, cached):
            if v is None and t not in seen:
                seen.add(t)
                missing_order.append(t)

        computed: dict[str, np.ndarray] = {}
        if missing_order:
            vectors = np.asarray(embed_fn(list(missing_order)), dtype=np.float32)
            if len(vectors) != len(missing_order):
                raise ValueError("embedder returned an unexpected number of vectors")
            cache.put_many(model_key, missing_order, vectors)
            computed = dict(zip(missing_order, vectors))

        rows = [v if v is not None else computed[t] for t, v in zip(texts, cached)]
        return np.asarray(rows, dtype=np.float32)
    except Exception:
        logger.exception("[embedding-cache] falling back to an uncached embed")
        return np.asarray(embed_fn(list(texts)), dtype=np.float32)
