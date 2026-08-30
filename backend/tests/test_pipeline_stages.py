"""Unit tests for the pluggable pipeline (ADR-0015/0016). Pure/offline — the
matcher and search fn are faked, so no model or network is needed."""
import pytest

from pipeline import CheckContext, Document, SourceDoc, default_check_stages, run_pipeline
from pipeline.base import PipelineError
from pipeline.stages import LocalizeStage, MatchStage, RetrieveStage


class FakeMatcher:
    def __init__(self):
        self.called_with = None

    def check(self, doc_text, sources):
        self.called_with = (doc_text, list(sources))
        return {
            "overall": {"similarity_pct": 12.5},
            "per_source": [{"id": "s0"}],
            "matches": [{"doc_start": 5, "doc_end": 9}, {"doc_start": 15, "doc_end": 18}],
            "warnings": ["matcher-warning"],
            "paraphrase_enabled": True,
        }


def _ctx(text="the document text here", sources=None, paragraphs=None):
    return CheckContext(
        document=Document(name="p.txt", text=text, paragraphs=paragraphs or []),
        sources=list(sources or []),
    )


# ── MatchStage ────────────────────────────────────────────────────────────────

def test_match_stage_populates_artifacts():
    fake = FakeMatcher()
    ctx = _ctx(sources=[SourceDoc("s0", "Src", "some source text")])
    ctx = MatchStage(fake).run(ctx)
    assert fake.called_with[0] == "the document text here"
    assert ctx.artifacts["overall"]["similarity_pct"] == 12.5
    assert ctx.artifacts["per_source"] == [{"id": "s0"}]
    assert len(ctx.artifacts["matches"]) == 2
    assert ctx.artifacts["paraphrase_enabled"] is True
    assert "matcher-warning" in ctx.warnings


# ── RetrieveStage ─────────────────────────────────────────────────────────────

def test_retrieve_off_is_noop():
    ctx = _ctx(sources=[SourceDoc("s0", "Src", "x")])
    called = []
    stage = RetrieveStage(lambda t: (called.append(t) or ([], [])), use_academic=False)
    ctx = stage.run(ctx)
    assert called == []                      # search never invoked
    assert ctx.artifacts["academic_used"] is False
    assert len(ctx.sources) == 1


def test_retrieve_on_extends_sources():
    ctx = _ctx()
    def search(_text):
        return [SourceDoc("a0", "OpenAlex hit", "abstract text", origin="openalex")], ["acad-warning"]
    ctx = RetrieveStage(search, use_academic=True).run(ctx)
    assert ctx.artifacts["academic_used"] is True
    assert ctx.sources[0].origin == "openalex"
    assert "acad-warning" in ctx.warnings


def test_retrieve_degrades_on_error():
    ctx = _ctx()
    def boom(_text):
        raise RuntimeError("network down")
    ctx = RetrieveStage(boom, use_academic=True).run(ctx)
    assert ctx.artifacts["academic_used"] is False
    assert any("academic" in w.lower() for w in ctx.warnings)
    assert ctx.sources == []                 # never raised


# ── LocalizeStage ─────────────────────────────────────────────────────────────

def test_localize_maps_paragraphs():
    paragraphs = [
        {"index": 0, "page": 1, "start": 0, "end": 10, "text": "first para"},
        {"index": 1, "page": 2, "start": 11, "end": 20, "text": "second one"},
    ]
    ctx = _ctx(paragraphs=paragraphs)
    ctx.artifacts["matches"] = [
        {"doc_start": 5, "doc_end": 9},       # -> paragraph 0 / page 1
        {"doc_start": 15, "doc_end": 18},     # -> paragraph 1 / page 2
        {"doc_start": 999, "doc_end": 1000},  # past the last para start -> maps to last paragraph
    ]
    ctx = LocalizeStage().run(ctx)
    m0, m1, m2 = ctx.artifacts["matches"]
    assert (m0["paragraph_index"], m0["page"]) == (0, 1)
    assert (m1["paragraph_index"], m1["page"]) == (1, 2)
    assert (m2["paragraph_index"], m2["page"]) == (1, 2)  # nearest preceding paragraph


def test_localize_no_paragraphs_is_null():
    ctx = _ctx(paragraphs=[])
    ctx.artifacts["matches"] = [{"doc_start": 5, "doc_end": 9}]
    ctx = LocalizeStage().run(ctx)
    m = ctx.artifacts["matches"][0]
    assert m["paragraph_index"] is None and m["page"] is None


# ── Orchestrator ──────────────────────────────────────────────────────────────

def test_run_pipeline_threads_context_and_reraises():
    fake = FakeMatcher()
    ctx = _ctx(
        sources=[SourceDoc("s0", "Src", "text")],
        paragraphs=[{"index": 0, "page": 1, "start": 0, "end": 50, "text": "t"}],
    )
    stages = default_check_stages(fake, lambda t: ([], []), use_academic=False)
    assert [s.name for s in stages] == ["retrieve", "match", "rerank", "localize"]
    # rerank is opt-in: off unless explicitly enabled (or PRISM_RERANK=1)
    assert next(s for s in stages if s.name == "rerank").enabled is False
    out = run_pipeline(ctx, stages)
    assert out.artifacts["matches"][0]["paragraph_index"] == 0

    class Boom:
        name = "boom"
        def run(self, ctx):
            raise RuntimeError("stage failure")

    with pytest.raises(RuntimeError):
        run_pipeline(ctx, [Boom()])


def test_pipeline_error_is_user_safe_subclass():
    assert issubclass(PipelineError, Exception)


# ── RerankStage (W4 cross-encoder) ────────────────────────────────────────────

from pipeline.stages import RerankStage  # noqa: E402


class FakeCE:
    """Stand-in cross-encoder: returns a preset score per pair."""
    def __init__(self, scores):
        self.scores = scores
        self.seen = None

    def predict(self, pairs, show_progress_bar=False):
        self.seen = list(pairs)
        return self.scores[:len(pairs)]


def _rerank_ctx(matches, text="The document text used for token accounting here."):
    ctx = _ctx(text=text)
    ctx.artifacts["matches"] = matches
    ctx.artifacts["overall"] = {"confident_pct": 0.0, "review_pct": 0.0, "review_count": 0}
    return ctx


def _m(sim, mtype="paraphrase", start=0, end=10, conf="review"):
    return {"match_type": mtype, "similarity": sim, "confidence": conf,
            "doc_start": start, "doc_end": end,
            "doc_excerpt": "doc text", "source_excerpt": "src text"}


def test_rerank_disabled_is_noop(monkeypatch):
    ctx = _rerank_ctx([_m(0.70)])
    out = RerankStage(enabled=False).run(ctx)
    assert "rerank_score" not in out.artifacts["matches"][0]


def test_rerank_promotes_and_demotes_by_cross_encoder(monkeypatch):
    import modelhub
    # 0.90 -> confident ; 0.40 -> stays review
    fake = FakeCE([0.90, 0.40])
    monkeypatch.setattr(modelhub, "get_cross_encoder", lambda k: fake)
    ctx = _rerank_ctx([_m(0.80, start=0, end=8), _m(0.70, start=9, end=17)])
    out = RerankStage(enabled=True, confident_threshold=0.78).run(ctx)
    a, b = out.artifacts["matches"]
    assert a["rerank_score"] == 0.9 and a["confidence"] == "confident"
    assert b["rerank_score"] == 0.4 and b["confidence"] == "review"
    # the displayed bi-encoder similarity is preserved
    assert a["similarity"] == 0.80 and b["similarity"] == 0.70
    assert out.artifacts["reranked_count"] == 2


def test_rerank_skips_verbatim_and_out_of_band(monkeypatch):
    import modelhub
    fake = FakeCE([0.99])
    monkeypatch.setattr(modelhub, "get_cross_encoder", lambda k: fake)
    ms = [
        _m(1.0, mtype="verbatim", conf="confident"),  # exact overlap -> never reranked
        _m(0.35),                                     # below lo
        _m(0.97),                                     # above hi
        _m(0.75, start=20, end=28),                   # borderline -> reranked
    ]
    ctx = _rerank_ctx(ms)
    out = RerankStage(enabled=True, lo=0.60, hi=0.92).run(ctx)
    assert out.artifacts["reranked_count"] == 1
    assert len(fake.seen) == 1
    assert [m.get("reranked") for m in ms] == [None, None, None, True]


def test_rerank_respects_max_pairs(monkeypatch):
    import modelhub
    fake = FakeCE([0.9] * 10)
    monkeypatch.setattr(modelhub, "get_cross_encoder", lambda k: fake)
    ms = [_m(0.70 + i * 0.001, start=i * 3, end=i * 3 + 2) for i in range(10)]
    out = RerankStage(enabled=True, max_pairs=3).run(_rerank_ctx(ms))
    assert out.artifacts["reranked_count"] == 3


def test_rerank_fails_soft_when_model_unavailable(monkeypatch):
    import modelhub
    def boom(_k):
        raise RuntimeError("model download failed")
    monkeypatch.setattr(modelhub, "get_cross_encoder", boom)
    ctx = _rerank_ctx([_m(0.70)])
    out = RerankStage(enabled=True).run(ctx)
    assert "rerank_score" not in out.artifacts["matches"][0]     # untouched
    assert any("rerank" in w.lower() for w in out.warnings)      # but surfaced


def test_rerank_recomputes_confidence_aggregates(monkeypatch):
    import modelhub
    monkeypatch.setattr(modelhub, "get_cross_encoder", lambda k: FakeCE([0.95]))
    text = "alpha beta gamma delta epsilon zeta eta theta"
    ctx = _rerank_ctx([_m(0.70, start=0, end=len(text))], text=text)
    out = RerankStage(enabled=True).run(ctx)
    ov = out.artifacts["overall"]
    assert ov["confident_pct"] > 0 and ov["review_pct"] == 0.0 and ov["review_count"] == 0
