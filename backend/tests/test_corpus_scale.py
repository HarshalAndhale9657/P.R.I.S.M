"""Unit tests for the corpus-scale probe (ADR-0024). Deterministic stub embedder — no model."""
import numpy as np
import pytest

from eval.corpus_scale import build_probe_with_truth, inflation_table, measure
from eval.pairs import PairCase


def _pairs(n=60):
    """Pairs where `a`/`b` of a positive are near-identical and everything else differs."""
    out = []
    for i in range(n):
        label = 1 if i % 2 == 0 else 0
        out.append(PairCase(a=f"query sentence number {i} about topic {i}",
                            b=(f"query sentence number {i} about topic {i} restated" if label
                               else f"unrelated statement {i} concerning matter {i}"),
                            label=label, id=f"p{i}"))
    return out


def _stub_embed(texts):
    """3-d vectors: near-duplicate strings land near each other, others do not."""
    rows = []
    for t in texts:
        toks = t.split()
        rows.append([len(toks), sum(ord(c) for c in t) % 1000 / 1000.0, len(set(toks)) / 10.0])
    v = np.asarray(rows, dtype=np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


# ── Probe construction ────────────────────────────────────────────────────────

def test_probe_never_puts_a_negative_querys_partner_in_the_corpus():
    pairs = _pairs()
    neg_q, pos_q, pos_truth, distractors = build_probe_with_truth(pairs, n_queries=10, max_corpus=200, seed=1)
    partners = {p.b for p in pairs if p.a in set(neg_q)}
    assert partners.isdisjoint(set(distractors)), "a negative query's own partner leaked into the corpus"
    assert set(neg_q).isdisjoint(set(distractors))


def test_probe_positives_carry_their_truth_and_are_disjoint_from_negatives():
    neg_q, pos_q, pos_truth, distractors = build_probe_with_truth(_pairs(), n_queries=8, max_corpus=100, seed=2)
    assert len(pos_q) == len(pos_truth) and pos_q
    assert set(pos_q).isdisjoint(set(neg_q))
    assert set(pos_truth).isdisjoint(set(distractors))


def test_probe_is_deterministic_for_a_seed():
    a = build_probe_with_truth(_pairs(), n_queries=6, max_corpus=50, seed=3)
    b = build_probe_with_truth(_pairs(), n_queries=6, max_corpus=50, seed=3)
    c = build_probe_with_truth(_pairs(), n_queries=6, max_corpus=50, seed=4)
    assert a == b and a != c


# ── Measurement ───────────────────────────────────────────────────────────────

def test_measure_reports_every_size_threshold_combination():
    r = measure(_pairs(120), embed=_stub_embed, corpus_sizes=(10, 40), thresholds=(0.5, 0.9),
                n_queries=10, dataset="stub")
    assert {x.corpus_size for x in r.results} == {10, 40}
    assert {x.threshold for x in r.results} == {0.5, 0.9}
    assert len(r.results) == 4
    for x in r.results:
        assert 0.0 <= x.fpr <= 1.0 and 0.0 <= x.recall <= 1.0
        assert x.false_positives <= x.n_negative_queries


def test_false_positive_rate_never_falls_as_the_corpus_grows():
    """The core claim: more sentences = more chances to score high, never fewer."""
    r = measure(_pairs(200), embed=_stub_embed, corpus_sizes=(10, 50, 150),
                thresholds=(0.6, 0.8), n_queries=20, dataset="stub")
    for t in (0.6, 0.8):
        fprs = [r.at(n, t).fpr for n in r.corpus_sizes]
        assert fprs == sorted(fprs), f"FPR fell as the corpus grew at t={t}: {fprs}"


def test_raising_the_threshold_never_raises_the_false_positive_rate():
    r = measure(_pairs(200), embed=_stub_embed, corpus_sizes=(50,),
                thresholds=(0.5, 0.7, 0.9), n_queries=20, dataset="stub")
    fprs = [r.at(50, t).fpr for t in (0.5, 0.7, 0.9)]
    assert fprs == sorted(fprs, reverse=True)


def test_inflation_table_is_monotonic_and_anchored_at_the_smallest_corpus():
    r = measure(_pairs(200), embed=_stub_embed, corpus_sizes=(10, 50, 150),
                thresholds=(0.7,), n_queries=20, dataset="stub")
    rows = inflation_table(r)
    assert [x["corpus_size"] for x in rows] == [10, 50, 150]
    assert rows[0]["drift_vs_smallest"] == 0.0
    means = [x["mean_max_negative"] for x in rows]
    assert means == sorted(means), "the top score for a no-match query must not fall as N grows"


def test_threshold_for_fpr_picks_the_lowest_threshold_within_budget():
    r = measure(_pairs(200), embed=_stub_embed, corpus_sizes=(50,),
                thresholds=(0.5, 0.7, 0.9), n_queries=20, dataset="stub")
    t = r.threshold_for_fpr(50, 1.0)
    assert t == 0.5                                   # everything is within a 100% budget
    assert r.threshold_for_fpr(50, -1.0) is None      # impossible budget -> no answer


def test_report_round_trips_to_a_json_safe_dict():
    import json
    r = measure(_pairs(80), embed=_stub_embed, corpus_sizes=(20,), thresholds=(0.7,),
                n_queries=8, dataset="stub")
    d = r.as_dict()
    assert json.loads(json.dumps(d))["dataset"] == "stub"
    assert d["results"][0]["corpus_size"] == 20


def test_measure_rejects_data_too_small_to_probe():
    with pytest.raises(ValueError):
        measure([], embed=_stub_embed, corpus_sizes=(10,), thresholds=(0.7,), n_queries=5)
