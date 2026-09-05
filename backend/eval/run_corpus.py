"""
P.R.I.S.M. — Corpus-scale benchmark runner (ADR-0024)
======================================================
How far does taking the **max over N source sentences** push the operating point away
from the pairwise numbers we calibrate on?

    python -m eval.run_corpus mrpc                 # default sweep
    python -m eval.run_corpus qqp --queries 300
    python -m eval.run_corpus stsb --sizes 100,1000,6000

Writes eval/results/corpus_<dataset>.json. Read the FPR column across a row: that is
the same threshold behaving differently purely because the corpus got bigger.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.corpus_scale import inflation_table, measure  # noqa: E402
from eval.pairs import DATASETS, DatasetNotAvailable, load_dataset  # noqa: E402

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_SIZES = (100, 500, 1000, 3000, 6000)
DEFAULT_THRESHOLDS = (0.66, 0.70, 0.74, 0.78, 0.82, 0.86, 0.90)


def _embedder(model_key: str):
    from modelhub import get_embedder
    emb = get_embedder(model_key)
    return emb.embed


def run(name: str, *, sizes, thresholds, n_queries: int, model_key: str, seed: int) -> dict:
    cases = load_dataset(name)
    report = measure(cases, embed=_embedder(model_key), corpus_sizes=sizes, thresholds=thresholds,
                     n_queries=n_queries, seed=seed, dataset=name, model_key=model_key)

    print("=" * 82)
    print(f"[{name}]  corpus-scale sweep   model={model_key}   "
          f"{report.results[0].n_negative_queries} negative / {report.results[0].n_positive_queries} positive queries")
    print("=" * 82)

    print("\nTop-score drift for a query with NO true match in the corpus:")
    print(f"  {'corpus':>8}  {'mean max':>9}  {'p95 max':>8}  {'drift':>7}")
    for row in inflation_table(report):
        print(f"  {row['corpus_size']:>8}  {row['mean_max_negative']:>9.3f}  "
              f"{row['p95_max_negative']:>8.3f}  {row['drift_vs_smallest']:>+7.3f}")

    print("\nFalse-positive rate by threshold x corpus size (flag rate on queries with no true match):")
    header = "  thresh " + "".join(f"{n:>9}" for n in report.corpus_sizes)
    print(header)
    for t in report.thresholds:
        row = f"  {t:>6.2f} "
        for n in report.corpus_sizes:
            r = report.at(n, t)
            row += f"{r.fpr:>9.3f}" if r else f"{'-':>9}"
        print(row)

    print("\nRecall by threshold x corpus size (query's true paraphrase IS in the corpus):")
    print(header)
    for t in report.thresholds:
        row = f"  {t:>6.2f} "
        for n in report.corpus_sizes:
            r = report.at(n, t)
            row += f"{r.recall:>9.3f}" if r else f"{'-':>9}"
        print(row)

    print("\nLowest threshold holding FPR at or under a budget, per corpus size:")
    for budget in (0.05, 0.10, 0.15):
        cells = []
        for n in report.corpus_sizes:
            t = report.threshold_for_fpr(n, budget)
            r = report.at(n, t) if t is not None else None
            cells.append(f"N={n}: {'none' if t is None else f'{t:.2f} (R={r.recall:.2f})'}")
        print(f"  FPR<={budget:.2f}   " + "   ".join(cells))

    artifact = report.as_dict()
    artifact["inflation"] = inflation_table(report)
    _RESULTS_DIR.mkdir(exist_ok=True)
    out = _RESULTS_DIR / f"corpus_{name}.json"
    out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return artifact


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Corpus-scale sweep: how max-over-N moves the operating point.")
    ap.add_argument("datasets", nargs="*", default=["mrpc"], help=f"one or more of {sorted(DATASETS)}")
    ap.add_argument("--sizes", default=",".join(str(n) for n in DEFAULT_SIZES))
    ap.add_argument("--thresholds", default=",".join(str(t) for t in DEFAULT_THRESHOLDS))
    ap.add_argument("--queries", type=int, default=200, help="probe sentences per class")
    ap.add_argument("--model-key", default="bi-encoder")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]

    ran = 0
    for name in args.datasets:
        if name not in DATASETS:
            print(f"NOTE: unknown dataset {name!r}; known: {sorted(DATASETS)}")
            continue
        try:
            run(name, sizes=sizes, thresholds=thresholds, n_queries=args.queries,
                model_key=args.model_key, seed=args.seed)
            ran += 1
        except DatasetNotAvailable as exc:
            print(f"SKIP [{name}]: {exc}\n")
        except ValueError as exc:
            print(f"SKIP [{name}]: {exc}\n")
    if not ran:
        print("Nothing ran. Fetch a dataset first:  python -m eval.fetch_datasets mrpc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
