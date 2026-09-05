"""Unit tests for the eval harness metrics + pair loader (pure/offline, no model)."""
import pytest

from eval import metrics as M
from eval.pairs import DATASETS, DatasetNotAvailable, load_dataset

# ── metrics ───────────────────────────────────────────────────────────────────

def test_confusion_and_binary_metrics_perfect():
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [1, 1, 0, 0]
    tp, fp, tn, fn = M.confusion(scores, labels, 0.5)
    assert (tp, fp, tn, fn) == (2, 0, 2, 0)
    m = M.binary_metrics(scores, labels, 0.5)
    assert m.precision == 1.0 and m.recall == 1.0 and m.f1 == 1.0 and m.fpr == 0.0


def test_binary_metrics_partial_recall():
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [1, 1, 0, 0]
    m = M.binary_metrics(scores, labels, 0.85)  # only 0.9 flagged
    assert m.tp == 1 and m.fn == 1 and m.fp == 0
    assert m.recall == 0.5 and m.precision == 1.0 and m.fpr == 0.0


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        M.confusion([0.1, 0.2], [1], 0.5)


def test_fpr_by_stratum_ignores_positives():
    scores = [0.9, 0.7, 0.6, 0.1, 0.95]
    labels = [0,   0,   0,   0,   1]     # last is a positive -> ignored in FPR
    strata = ["hi", "hi", "lo", "lo", "paraphrase"]
    out = M.fpr_by_stratum(scores, labels, strata, threshold=0.65)
    assert out["hi"] == {"flagged": 2, "total": 2, "fpr": 1.0}   # 0.9, 0.7 flagged
    assert out["lo"] == {"flagged": 0, "total": 2, "fpr": 0.0}   # 0.6, 0.1 not flagged
    assert "paraphrase" not in out                                # positives excluded


def test_best_threshold_f1_and_fpr_cap():
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [1, 1, 0, 0]
    best = M.best_threshold(scores, labels, objective="f1")
    assert best.f1 == 1.0
    # A cap that forces a conservative choice still returns a valid point.
    capped = M.best_threshold(scores, labels, objective="recall", max_fpr=0.0)
    assert capped.fpr <= 0.0 and capped.recall == 1.0


def test_percentiles_and_separation():
    assert M.percentiles([]) == {"p5": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0}
    p = M.percentiles([0.0, 0.25, 0.5, 0.75, 1.0])
    assert p["p50"] == 0.5 and p["p5"] <= p["p50"] <= p["p95"]

    # Well-separated: positives high, negatives low -> large positive gap.
    sep = M.separation([0.9, 0.95, 0.1, 0.05], [1, 1, 0, 0])
    assert sep["mean_positive"] > sep["mean_negative"]
    assert sep["mean_gap"] > 0.5

    # Saturated/overlapping: both classes crushed together -> ~zero gap.
    flat = M.separation([0.8, 0.82, 0.81, 0.79], [1, 1, 0, 0])
    assert abs(flat["mean_gap"]) < 0.05


def test_brier():
    assert M.brier([1.0, 0.0], [1, 0]) == 0.0
    assert M.brier([0.5, 0.5], [1, 0]) == 0.25
    assert M.brier([], []) == 0.0


# ── pair loader ───────────────────────────────────────────────────────────────

def test_sample_dataset_loads():
    cases = load_dataset("sample")
    assert len(cases) == 10
    assert sum(c.label for c in cases) == 5           # 5 positive / 5 negative
    assert {c.stratum for c in cases} >= {"paraphrase", "high_overlap_negative", "unrelated"}
    assert all(c.a and c.b and c.dataset == "sample" for c in cases)


def test_unfetched_dataset_raises_with_hint(tmp_path, monkeypatch):
    # Point DATA_DIR at an empty temp dir so the result is deterministic regardless
    # of which datasets happen to be fetched locally (e.g. PAWS from a W2 run).
    import eval.pairs as pairs_mod
    monkeypatch.setattr(pairs_mod, "DATA_DIR", tmp_path)
    assert "paws" in DATASETS
    with pytest.raises(DatasetNotAvailable) as exc:
        load_dataset("paws")
    assert "fetch_datasets" in str(exc.value)


def test_unknown_dataset_raises_keyerror():
    with pytest.raises(KeyError):
        load_dataset("nope-not-real")
