"""Unit tests for the sentence-embedding cache (ADR-0023). No model — the embedder is a stub."""
import numpy as np
import pytest

from services.embedding_cache import EmbeddingCache, embed_cached


class StubEmbedder:
    """Deterministic 'embeddings' plus a record of exactly what it was asked to embed."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return np.array([[float(len(t)), float(sum(map(ord, t)) % 97), 1.0] for t in texts], dtype=np.float32)

    @property
    def embedded(self) -> list[str]:
        return [t for call in self.calls for t in call]


def _cache(**kw):
    return EmbeddingCache(**kw)


# ── Correctness ───────────────────────────────────────────────────────────────

def test_returns_same_vectors_as_an_uncached_call():
    e, c = StubEmbedder(), _cache()
    texts = ["alpha", "beta", "gamma"]
    expected = e.embed(texts)
    e.calls.clear()
    got = embed_cached(e.embed, texts, model_key="m", cache=c)
    assert np.array_equal(got, expected)
    assert got.dtype == np.float32 and got.shape == (3, 3)


def test_second_call_embeds_nothing():
    e, c = StubEmbedder(), _cache()
    texts = ["one", "two", "three"]
    first = embed_cached(e.embed, texts, model_key="m", cache=c)
    e.calls.clear()
    second = embed_cached(e.embed, texts, model_key="m", cache=c)
    assert e.calls == []                       # a full cache hit costs no forward pass
    assert np.array_equal(first, second)
    assert c.stats().hits == 3 and c.stats().misses == 3


def test_partial_overlap_embeds_only_the_new_sentences():
    e, c = StubEmbedder(), _cache()
    embed_cached(e.embed, ["a", "b"], model_key="m", cache=c)
    e.calls.clear()
    out = embed_cached(e.embed, ["b", "c", "a", "d"], model_key="m", cache=c)
    assert e.embedded == ["c", "d"]            # only the misses
    assert out.shape == (4, 3)
    assert np.array_equal(out[0], out[0]) and np.array_equal(out[2], embed_cached(e.embed, ["a"], model_key="m", cache=c)[0])


def test_duplicates_within_one_call_are_embedded_once():
    e, c = StubEmbedder(), _cache()
    out = embed_cached(e.embed, ["x", "y", "x", "x"], model_key="m", cache=c)
    assert e.embedded == ["x", "y"]
    assert np.array_equal(out[0], out[2]) and np.array_equal(out[0], out[3])
    assert out.shape == (4, 3)


def test_order_is_preserved_with_a_mix_of_hits_and_misses():
    e, c = StubEmbedder(), _cache()
    embed_cached(e.embed, ["mid"], model_key="m", cache=c)
    texts = ["first", "mid", "last"]
    out = embed_cached(e.embed, texts, model_key="m", cache=c)
    direct = StubEmbedder().embed(texts)
    assert np.array_equal(out, direct)


def test_model_key_namespaces_entries():
    e, c = StubEmbedder(), _cache()
    embed_cached(e.embed, ["shared"], model_key="model-a", cache=c)
    e.calls.clear()
    embed_cached(e.embed, ["shared"], model_key="model-b", cache=c)
    assert e.embedded == ["shared"]            # a different model must not reuse vectors


def test_empty_input_short_circuits():
    e, c = StubEmbedder(), _cache()
    out = embed_cached(e.embed, [], model_key="m", cache=c)
    assert out.shape[0] == 0 and e.calls == []


# ── Bounds and safety ─────────────────────────────────────────────────────────

def test_lru_eviction_keeps_the_cache_bounded():
    e, c = StubEmbedder(), _cache(max_entries=2)
    embed_cached(e.embed, ["a", "b"], model_key="m", cache=c)
    embed_cached(e.embed, ["a"], model_key="m", cache=c)        # touch a -> b is the LRU
    embed_cached(e.embed, ["c"], model_key="m", cache=c)        # evicts b
    assert len(c) == 2 and c.stats().evictions == 1
    e.calls.clear()
    embed_cached(e.embed, ["a", "b"], model_key="m", cache=c)
    assert e.embedded == ["b"]                                   # a survived, b was evicted


def test_cached_vectors_are_read_only():
    e, c = StubEmbedder(), _cache()
    embed_cached(e.embed, ["frozen"], model_key="m", cache=c)
    stored = c.get_many("m", ["frozen"])[0]
    with pytest.raises(ValueError):
        stored[0] = 999.0


def test_a_broken_cache_never_breaks_a_check(monkeypatch):
    e, c = StubEmbedder(), _cache()

    def boom(*a, **k):
        raise RuntimeError("cache exploded")

    monkeypatch.setattr(c, "get_many", boom)
    out = embed_cached(e.embed, ["a", "b"], model_key="m", cache=c)
    assert out.shape == (2, 3)                 # degraded to a plain embed
    assert e.embedded == ["a", "b"]


def test_embedder_returning_wrong_count_falls_back():
    c = _cache()
    calls = []

    def bad(texts):
        calls.append(list(texts))
        n = len(texts) if len(calls) > 1 else len(texts) - 1     # short result the first time
        return np.ones((max(n, 0), 3), dtype=np.float32)

    out = embed_cached(bad, ["a", "b"], model_key="m", cache=c)
    assert out.shape == (2, 3) and len(calls) == 2               # retried uncached


def test_stats_report_hit_rate():
    e, c = StubEmbedder(), _cache()
    embed_cached(e.embed, ["a", "b"], model_key="m", cache=c)
    embed_cached(e.embed, ["a", "b"], model_key="m", cache=c)
    s = c.stats()
    assert s.hits == 2 and s.misses == 2 and s.hit_rate == 0.5
    assert s.as_dict()["hit_rate"] == 0.5


def test_clear_resets_entries_and_stats():
    e, c = StubEmbedder(), _cache()
    embed_cached(e.embed, ["a"], model_key="m", cache=c)
    c.clear()
    assert len(c) == 0 and c.stats().lookups == 0


# ── Configuration ─────────────────────────────────────────────────────────────

def test_configure_cache_replaces_the_global_and_zero_disables(monkeypatch):
    import services.embedding_cache as ec

    ec.configure_cache(5)
    assert ec.get_cache().max_entries == 5

    ec.configure_cache(0)                       # disabled
    e = StubEmbedder()
    embed_cached(e.embed, ["a"], model_key="m")  # no explicit cache -> uses the global
    embed_cached(e.embed, ["a"], model_key="m")
    assert e.embedded == ["a", "a"]              # nothing cached, so it embeds twice
    assert len(ec.get_cache()) == 0
    ec.configure_cache(ec.DEFAULT_MAX_ENTRIES)   # restore for other tests
