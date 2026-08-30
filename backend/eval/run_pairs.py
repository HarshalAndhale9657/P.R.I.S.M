"""
P.R.I.S.M. — Paraphrase benchmark runner (the honest baseline, ADR-0016)
========================================================================
Run the paraphrase scorer over one or more public sentence-pair datasets and
report precision / recall / F1 / FPR at the matcher's live threshold, a threshold
sweep (best-F1 and best-recall @ FPR<=cap), FPR per stratum, and Brier.

    python -m eval.run_pairs                 # all fetched datasets (falls back to 'sample')
    python -m eval.run_pairs paws mrpc       # specific sets
    python -m eval.run_pairs paws --gate     # non-zero exit if gates fail

Datasets are fetched separately (see eval/fetch_datasets.py); a missing set is
reported with its fetch command and skipped, so this never hard-fails CI before
the data exists. Results are written to eval/results/pairs_<name>.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python scripts/... ` style and `-m eval.run_pairs` both to import backend pkgs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval import metrics as M
from eval.pairs import DatasetNotAvailable, DATASETS, load_dataset
from eval.scorer import PARAPHRASE_THRESHOLD, score

_RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Provisional gates for the paraphrase pillar (tightened once real data lands).
MIN_RECALL = 0.60
MAX_FPR = 0.15
MAX_STRATUM_FPR = 0.34


def _run_one(name: str, *, threshold: float, max_fpr: float, gate: bool,
             scorer: str = "bi", model_key: str = None) -> dict:
    cases = load_dataset(name)
    scores = score(cases, scorer=scorer, model_key=model_key)
    labels = [c.label for c in cases]
    strata = [c.stratum for c in cases]
    tag = model_key or ("cross-encoder-stsb" if scorer == "cross" else None)

    at_thr = M.binary_metrics(scores, labels, threshold)
    best_f1 = M.best_threshold(scores, labels, objective="f1")
    best_recall = M.best_threshold(scores, labels, objective="recall", max_fpr=max_fpr)
    strat = M.fpr_by_stratum(scores, labels, strata, threshold)
    brier = M.brier(scores, labels)

    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    model_label = tag or "bi-encoder"
    print("=" * 78)
    print(f"[{name}]  {len(cases)} pairs  ({n_pos} positive / {n_neg} negative)   "
          f"{DATASETS[name].description}")
    print(f"scorer={scorer}  model={model_label}")
    print("=" * 78)
    print(f"At matcher threshold {threshold:.2f}:  "
          f"P={at_thr.precision:.3f}  R={at_thr.recall:.3f}  F1={at_thr.f1:.3f}  "
          f"FPR={at_thr.fpr:.3f}   (TP={at_thr.tp} FP={at_thr.fp} TN={at_thr.tn} FN={at_thr.fn})")
    print(f"Best-F1 threshold:        t={best_f1.threshold:.2f}  "
          f"P={best_f1.precision:.3f}  R={best_f1.recall:.3f}  F1={best_f1.f1:.3f}  FPR={best_f1.fpr:.3f}")
    print(f"Best-recall @ FPR<={max_fpr:.2f}:  t={best_recall.threshold:.2f}  "
          f"R={best_recall.recall:.3f}  FPR={best_recall.fpr:.3f}")
    print(f"Brier (calibration proxy, lower=better): {brier:.4f}")

    # Operating points: same scores, several candidate thresholds (no re-embedding).
    op_points = [M.binary_metrics(scores, labels, t) for t in (0.66, 0.70, 0.74, 0.78, 0.82, 0.86)]
    print("\nOperating points (threshold -> P/R/F1/FPR):")
    for m in op_points:
        print(f"  t={m.threshold:.2f}   P={m.precision:.3f}  R={m.recall:.3f}  "
              f"F1={m.f1:.3f}  FPR={m.fpr:.3f}")

    sep = M.separation(scores, labels)
    print(f"Separation: mean(pos)={sep['mean_positive']:.3f}  mean(neg)={sep['mean_negative']:.3f}  "
          f"gap={sep['mean_gap']:.3f}")
    print(f"  positive p5/25/50/75/95: {[sep['positive'][k] for k in ('p5','p25','p50','p75','p95')]}")
    print(f"  negative p5/25/50/75/95: {[sep['negative'][k] for k in ('p5','p25','p50','p75','p95')]}")

    if strat:
        print("\nFalse-positive rate by negative stratum (at matcher threshold):")
        for st, v in strat.items():
            print(f"  {st:<24} {v['flagged']}/{v['total']} flagged   FPR={v['fpr']:.2f}")

    worst_stratum = max((v["fpr"] for v in strat.values()), default=0.0)
    gates_pass = (at_thr.recall >= MIN_RECALL and at_thr.fpr <= MAX_FPR
                  and worst_stratum <= MAX_STRATUM_FPR)
    if gate:
        print(f"\nGates: recall>={MIN_RECALL} FPR<={MAX_FPR} per-stratum<={MAX_STRATUM_FPR}  ->  "
              f"{'PASS' if gates_pass else 'FAIL'}")

    artifact = {
        "dataset": name,
        "n": len(cases), "n_positive": n_pos, "n_negative": n_neg,
        "threshold": threshold,
        "scorer": scorer,
        "model_key": model_label,
        "at_threshold": at_thr.as_dict(),
        "best_f1": best_f1.as_dict(),
        "best_recall_at_fpr_cap": best_recall.as_dict(),
        "fpr_by_stratum": strat,
        "operating_points": [m.as_dict() for m in op_points],
        "separation": sep,
        "brier": brier,
        "gates_pass": gates_pass,
    }
    _RESULTS_DIR.mkdir(exist_ok=True)
    suffix = f"_{tag}" if tag else ""    # default bi-encoder keeps the baseline filename
    (_RESULTS_DIR / f"pairs_{name}{suffix}.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252 by default
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="PRISM paraphrase benchmark runner (public datasets).")
    ap.add_argument("datasets", nargs="*", help="dataset names (default: all fetched, else 'sample')")
    ap.add_argument("--threshold", type=float, default=PARAPHRASE_THRESHOLD,
                    help=f"flag threshold (default = matcher's {PARAPHRASE_THRESHOLD:.2f})")
    ap.add_argument("--max-fpr", type=float, default=MAX_FPR, help="FPR cap for best-recall sweep")
    ap.add_argument("--gate", action="store_true", help="exit non-zero if gates fail")
    ap.add_argument("--scorer", choices=["bi", "cross"], default="bi",
                    help="bi = bi-encoder cosine (W2/W3); cross = cross-encoder rerank (W4)")
    ap.add_argument("--model-key", default=None,
                    help="registry key override (e.g. bi-encoder-mpnet, cross-encoder-stsb)")
    args = ap.parse_args(argv)

    kw = dict(threshold=args.threshold, max_fpr=args.max_fpr, gate=args.gate,
              scorer=args.scorer, model_key=args.model_key)

    requested = args.datasets or list(DATASETS.keys())
    ran, any_fail = [], False
    for name in requested:
        if name not in DATASETS:
            print(f"NOTE: unknown dataset {name!r}; known: {sorted(DATASETS)}")
            continue
        try:
            art = _run_one(name, **kw)
            ran.append(art)
            any_fail = any_fail or (args.gate and not art["gates_pass"])
        except DatasetNotAvailable as exc:
            print(f"SKIP [{name}]: {exc}\n")

    if not ran:
        # Nothing fetched yet — fall back to the committed smoke sample so the
        # harness still demonstrably runs end-to-end offline.
        if "sample" not in requested:
            print("No requested datasets are available; running the committed 'sample' smoke set.\n")
            try:
                ran.append(_run_one("sample", **kw))
            except DatasetNotAvailable as exc:
                print(f"SKIP [sample]: {exc}")
        if not ran:
            print("\nNo datasets available. Fetch one:  python -m eval.fetch_datasets paws")
            return 0

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
