"""
P.R.I.S.M. — Corpus-scale benchmark runner (ADR-0024)
======================================================
How far does taking the **max over N source sentences** push the operating point away
from the pairwise numbers we calibrate on?

    python -m eval.run_corpus mrpc                 # default sweep
    python -m eval.run_corpus qqp --queries 300
    python -m eval.run_corpus stsb --sizes 100,1000,6000

    # ADR-0025: the same sweep against a corpus assembled the way the product assembles
    # one — sources ordered by relevance to the manuscript, pooled from other datasets
    # so the ranking has something to select from.
    python -m eval.run_corpus qqp --distractors both --pool paws,mrpc,stsb --examples 15

Writes eval/results/corpus_<dataset>.json (`_retrieved` suffix for the retrieved mode).
Read the FPR column across a row: that is the same threshold behaving differently purely
because the corpus got bigger.
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


def _pool_pairs(names, exclude: str):
    """Distractor-only pairs from other registered datasets (never queries)."""
    pool, used = [], []
    for n in names:
        if not n or n == exclude:
            continue
        if n not in DATASETS:
            print(f"NOTE: unknown pool dataset {n!r}; skipped")
            continue
        try:
            pool.extend(load_dataset(n))
            used.append(n)
        except DatasetNotAvailable as exc:
            print(f"NOTE: pool dataset {n!r} not fetched; skipped ({exc.args[0].splitlines()[0]})")
    return pool, used


def run(name: str, *, sizes, thresholds, n_queries: int, model_key: str, seed: int,
        mode: str = "random", pool_names=(), pool_only: bool = False, drop_above: float = 0.0,
        n_examples: int = 0) -> dict:
    cases = load_dataset(name)
    want_pool = mode == "retrieved" or pool_only
    pool, pool_used = _pool_pairs(pool_names, exclude=name) if want_pool else ([], [])
    if pool_only and not pool:
        raise ValueError("--pool-only needs at least one fetched --pool dataset")
    report = measure(cases, embed=_embedder(model_key), corpus_sizes=sizes, thresholds=thresholds,
                     n_queries=n_queries, seed=seed, dataset=name, model_key=model_key,
                     distractor_mode=mode, pool_pairs=pool, pool_datasets=pool_used,
                     pool_only=pool_only, drop_above=drop_above, n_near_misses=n_examples)

    print("=" * 82)
    print(f"[{name}]  corpus-scale sweep   model={model_key}   "
          f"distractors={mode}{' (cross-dataset only)' if pool_only else ''}   "
          f"{report.results[0].n_negative_queries} negative / {report.results[0].n_positive_queries} positive queries")
    if drop_above:
        print(f"           dropped {report.dropped_near_duplicates} corpus sentences within "
              f"{drop_above:.2f} of a query (near-certain unlabelled paraphrases)")
    if want_pool:
        print(f"           pool = {report.pool_size} sentences"
              + (f" (+{', '.join(pool_used)})" if pool_used else "")
              + f"   selection at N={max(sizes)}: top {100.0 * min(max(sizes), report.pool_size) / max(report.pool_size, 1):.0f}%")
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

    if report.near_misses:
        print("\nHighest-scoring flags (all false positives BY CONSTRUCTION — read them; if any is a real\n"
              "paraphrase the pool is contaminated and the FPR above is overstated):")
        for m in report.near_misses:
            print(f"  {m.score:.3f}  Q: {m.query[:96]}")
            print(f"         C: {m.corpus_sentence[:96]}")

    artifact = report.as_dict()
    artifact["inflation"] = inflation_table(report)
    _RESULTS_DIR.mkdir(exist_ok=True)
    suffix = "" if mode == "random" and not pool_only else f"_{mode}"
    suffix += "_clean" if pool_only else ""
    suffix += f"_drop{int(round(drop_above * 100))}" if drop_above else ""
    out = _RESULTS_DIR / f"corpus_{name}{suffix}.json"
    out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return artifact


def _fpr_at(artifact: dict, n: int, t: float):
    for r in artifact["results"]:
        if r["corpus_size"] == n and abs(r["threshold"] - t) < 1e-9:
            return r
    return None


def _print_comparison(name: str, rnd: dict, ret: dict, thresholds) -> None:
    """The whole point of ADR-0025: how much worse is a corpus chosen *because it is relevant*."""
    sizes = [n for n in rnd["corpus_sizes"] if n in set(ret["corpus_sizes"])]
    print("\n" + "=" * 82)
    print(f"[{name}]  unrelated corpus  vs  retrieved corpus   (the product lives between them)")
    print("=" * 82)
    print("\nMean top score for a query with NO true match:")
    print(f"  {'corpus':>8}  {'random':>8}  {'retrieved':>10}  {'delta':>7}")
    by_n_rnd = {r["corpus_size"]: r for r in rnd["inflation"]}
    by_n_ret = {r["corpus_size"]: r for r in ret["inflation"]}
    for n in sizes:
        a, b = by_n_rnd.get(n), by_n_ret.get(n)
        if a and b:
            print(f"  {n:>8}  {a['mean_max_negative']:>8.3f}  {b['mean_max_negative']:>10.3f}  "
                  f"{b['mean_max_negative'] - a['mean_max_negative']:>+7.3f}")
    for t in (0.78, 0.90):
        if not any(abs(x - t) < 1e-9 for x in thresholds):
            continue
        print(f"\nFPR at threshold {t:.2f}:")
        print(f"  {'corpus':>8}  {'random':>8}  {'retrieved':>10}")
        for n in sizes:
            a, b = _fpr_at(rnd, n, t), _fpr_at(ret, n, t)
            if a and b:
                print(f"  {n:>8}  {a['fpr']:>8.3f}  {b['fpr']:>10.3f}")


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
    ap.add_argument("--distractors", default="random", choices=("random", "retrieved", "both"),
                    help="random = unrelated corpus (ADR-0024 floor); retrieved = corpus ordered by "
                         "relevance to the manuscript, as the product builds one (ADR-0025 ceiling)")
    ap.add_argument("--pool", default="", help="comma-separated datasets contributing DISTRACTORS ONLY, "
                                               "so the retrieved ranking has something to select from")
    ap.add_argument("--pool-only", action="store_true",
                    help="take the corpus ENTIRELY from --pool datasets, so no unlabelled paraphrase of a "
                         "query can be in it (contamination-free, but topically further away)")
    ap.add_argument("--drop-above", type=float, default=0.0,
                    help="drop corpus sentences within this similarity of ANY query before measuring — "
                         "bounds how much of a same-dataset FPR is unlabelled duplicates")
    ap.add_argument("--examples", type=int, default=0,
                    help="dump the N highest-scoring false positives for human inspection")
    args = ap.parse_args(argv)

    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]
    pool_names = [x.strip() for x in args.pool.split(",") if x.strip()]
    modes = ("random", "retrieved") if args.distractors == "both" else (args.distractors,)

    ran = 0
    for name in args.datasets:
        if name not in DATASETS:
            print(f"NOTE: unknown dataset {name!r}; known: {sorted(DATASETS)}")
            continue
        done = {}
        for mode in modes:
            try:
                done[mode] = run(name, sizes=sizes, thresholds=thresholds, n_queries=args.queries,
                                 model_key=args.model_key, seed=args.seed, mode=mode,
                                 pool_names=pool_names, pool_only=args.pool_only,
                                 drop_above=args.drop_above,
                                 n_examples=args.examples)
                ran += 1
            except DatasetNotAvailable as exc:
                print(f"SKIP [{name}]: {exc}\n")
            except ValueError as exc:
                print(f"SKIP [{name}]: {exc}\n")
        if len(done) == 2:
            _print_comparison(name, done["random"], done["retrieved"], thresholds)
    if not ran:
        print("Nothing ran. Fetch a dataset first:  python -m eval.fetch_datasets mrpc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
