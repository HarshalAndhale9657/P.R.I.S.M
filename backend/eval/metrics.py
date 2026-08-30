"""
P.R.I.S.M. — Evaluation metrics (pure, stdlib-only, offline-testable)
====================================================================
Binary detection metrics from (score, label) pairs, where `label` is 1 for a true
paraphrase/positive and 0 for a negative, and a pair is *flagged* when
`score >= threshold`.

Reports the safety-critical view for a self-check tool: precision / recall / F1 /
specificity / **false-positive rate**, plus **FPR per stratum** (so a high-overlap
non-paraphrase stratum — our stand-in for the ESL / boilerplate trap — is watched
directly), a **threshold sweep**, and a Brier score (calibration proxy).

No numpy / sklearn dependency, so it is trivially unit-testable without the model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple


def _rate(num: int, den: int) -> float:
    return (num / den) if den else 0.0


@dataclass
class BinaryMetrics:
    threshold: float
    n: int
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    f1: float
    specificity: float
    fpr: float

    def as_dict(self) -> dict:
        return asdict(self)


def confusion(scores: Sequence[float], labels: Sequence[int], threshold: float) -> Tuple[int, int, int, int]:
    """Return (tp, fp, tn, fn) at the given threshold (flag when score >= threshold)."""
    if len(scores) != len(labels):
        raise ValueError("scores and labels must be the same length")
    tp = fp = tn = fn = 0
    for s, y in zip(scores, labels):
        flagged = s >= threshold
        if y:
            tp += flagged
            fn += not flagged
        else:
            fp += flagged
            tn += not flagged
    return tp, fp, tn, fn


def binary_metrics(scores: Sequence[float], labels: Sequence[int], threshold: float) -> BinaryMetrics:
    tp, fp, tn, fn = confusion(scores, labels, threshold)
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = _rate(2 * precision * recall, precision + recall)
    specificity = _rate(tn, tn + fp)
    fpr = _rate(fp, fp + tn)
    return BinaryMetrics(
        threshold=round(threshold, 4), n=len(scores),
        tp=tp, fp=fp, tn=tn, fn=fn,
        precision=round(precision, 4), recall=round(recall, 4), f1=round(f1, 4),
        specificity=round(specificity, 4), fpr=round(fpr, 4),
    )


def fpr_by_stratum(
    scores: Sequence[float], labels: Sequence[int], strata: Sequence[str], threshold: float
) -> Dict[str, dict]:
    """FPR within each negative stratum (positives are ignored — FPR is a negatives-only view)."""
    agg: Dict[str, List[int]] = {}  # stratum -> [flagged, total]
    for s, y, st in zip(scores, labels, strata):
        if y:  # only negatives contribute to a false-positive rate
            continue
        cell = agg.setdefault(st or "-", [0, 0])
        cell[1] += 1
        if s >= threshold:
            cell[0] += 1
    return {
        st: {"flagged": flagged, "total": total, "fpr": round(_rate(flagged, total), 4)}
        for st, (flagged, total) in sorted(agg.items())
    }


def sweep_thresholds(
    scores: Sequence[float], labels: Sequence[int], grid: Optional[Sequence[float]] = None
) -> List[BinaryMetrics]:
    if grid is None:
        grid = [i / 100 for i in range(0, 101)]  # 0.00 .. 1.00
    return [binary_metrics(scores, labels, t) for t in grid]


def best_threshold(
    scores: Sequence[float],
    labels: Sequence[int],
    *,
    objective: str = "f1",
    max_fpr: Optional[float] = None,
    grid: Optional[Sequence[float]] = None,
) -> BinaryMetrics:
    """Pick the threshold maximizing `objective` ("f1" or "recall"), optionally
    subject to fpr <= max_fpr. Falls back to the best-objective point if the FPR
    constraint excludes everything."""
    sweep = sweep_thresholds(scores, labels, grid)
    key = (lambda m: m.recall) if objective == "recall" else (lambda m: m.f1)
    eligible = [m for m in sweep if (max_fpr is None or m.fpr <= max_fpr)]
    pool = eligible or sweep
    # Prefer higher objective; tie-break on lower FPR then higher threshold (more conservative).
    return max(pool, key=lambda m: (key(m), -m.fpr, m.threshold))


def brier(scores: Sequence[float], labels: Sequence[int]) -> float:
    """Mean squared error between score (as P[positive]) and label — a calibration
    proxy. Only meaningful when scores are in [0, 1]."""
    if not scores:
        return 0.0
    return round(sum((s - y) ** 2 for s, y in zip(scores, labels)) / len(scores), 4)
