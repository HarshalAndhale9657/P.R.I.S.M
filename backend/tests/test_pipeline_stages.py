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
    assert [s.name for s in stages] == ["retrieve", "match", "localize"]
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
