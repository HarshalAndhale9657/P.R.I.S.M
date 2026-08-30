"""Unit tests for the W5 fine-tune ship/no-ship gate (pure — no GPU, no model, no network).

The gate decides whether a fine-tuned cross-encoder earns its place (ADR-0016).
Getting it wrong in the permissive direction would ship a regression, so it is
worth testing independently of the training run.
"""
import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "training" / "finetune_cross_encoder.py"


def _load():
    spec = importlib.util.spec_from_file_location("w5", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


w5 = _load()


def _res(fpr, f1, brier):
    """Minimal shape the gate reads."""
    return {"at_0.66": {"fpr": fpr}, "best_f1": {"f1": f1}, "brier": brier}


def test_script_imports_and_exposes_gate():
    assert callable(w5.gate)
    assert w5.CONFIDENT_THRESHOLD == 0.78


def test_clear_improvement_passes():
    before = _res(0.40, 0.860, 0.156)
    after = _res(0.30, 0.900, 0.140)          # FPR down, F1 +0.04, Brier down
    ok, reasons = w5.gate(before, after, "mrpc")
    assert ok is True
    assert any("OK" in r for r in reasons)


def test_raised_fpr_fails_even_if_f1_improves():
    before = _res(0.40, 0.860, 0.156)
    after = _res(0.45, 0.920, 0.140)          # F1 way up but FPR REGRESSED
    ok, reasons = w5.gate(before, after, "mrpc")
    assert ok is False
    assert any("REGRESSED" in r for r in reasons)


def test_marginal_f1_gain_is_rejected_as_noise():
    before = _res(0.40, 0.860, 0.156)
    after = _res(0.40, 0.865, 0.156)          # +0.005 < the +0.01 required
    ok, _ = w5.gate(before, after, "mrpc")
    assert ok is False


def test_worsened_calibration_fails():
    before = _res(0.40, 0.860, 0.156)
    after = _res(0.35, 0.900, 0.200)          # Brier REGRESSED
    ok, _ = w5.gate(before, after, "mrpc")
    assert ok is False


def test_identical_results_do_not_ship():
    same = _res(0.40, 0.860, 0.156)
    ok, _ = w5.gate(same, dict(same), "paws")
    assert ok is False, "no change must never justify shipping"


def test_exactly_threshold_gain_passes():
    before = _res(0.40, 0.860, 0.156)
    after = _res(0.40, 0.870, 0.156)          # exactly +0.01, FPR/Brier flat
    ok, _ = w5.gate(before, after, "mrpc")
    assert ok is True


def test_published_baselines_recorded():
    """The script must carry the real measured baselines it has to beat."""
    assert w5.BASELINES["mrpc"]["model"] == "cross-encoder-stsb"
    assert w5.BASELINES["paws"]["model"] == "cross-encoder-qqp"
    assert 0.0 < w5.BASELINES["paws"]["fpr_at_066"] <= 1.0
