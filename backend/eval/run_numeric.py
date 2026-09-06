"""
P.R.I.S.M. — Does numeric agreement separate boilerplate from paraphrase? (ADR-0025 finding 3)
==============================================================================================
ADR-0025 found the residual false positives are template text with different facts in
it. This runner asks the only question that decides whether that becomes a product
signal:

    Among pairs the matcher would already call **confident** (cosine >= the cutoff),
    does requiring the numbers to agree remove negatives faster than it removes
    positives?

    python -m eval.run_numeric mrpc stsb qqp paws
    python -m eval.run_numeric mrpc --cutoff 0.78

Writes eval/results/numeric_<dataset>.json. A signal that downgrades as many true
paraphrases as boilerplate is a wash and must not ship — "do not ship" is a result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.numeric_agreement import agreement, applicable  # noqa: E402
from eval.pairs import DATASETS, DatasetNotAvailable, load_dataset  # noqa: E402

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_GATES = (0.0, 0.25, 0.5, 0.75, 0.999)


def _cosines(pairs, model_key: str):
    import numpy as np

    from modelhub import get_embedder
    emb = get_embedder(model_key)
    a = np.asarray(emb.embed([p.a for p in pairs]), dtype=np.float32)
    b = np.asarray(emb.embed([p.b for p in pairs]), dtype=np.float32)
    num = np.sum(a * b, axis=1)
    den = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12
    return (num / den).tolist()


def _mean(xs):
    return round(sum(xs) / len(xs), 4) if xs else 0.0


def run(name: str, *, cutoff: float, gates, model_key: str) -> dict:
    cases = load_dataset(name)
    idx = applicable(cases)
    pairs = [cases[i] for i in idx]
    coverage = round(len(pairs) / len(cases), 4) if cases else 0.0

    print("=" * 82)
    print(f"[{name}]  numeric agreement   model={model_key}   cutoff={cutoff:.2f}")
    print(f"           {len(pairs)} of {len(cases)} pairs state a number on both sides "
          f"({100 * coverage:.1f}% coverage — the signal is silent on the rest)")
    print("=" * 82)
    if not pairs:
        print("No pair states a number on both sides; nothing to measure.\n")
        return {"dataset": name, "coverage": coverage, "n_applicable": 0}

    cos = _cosines(pairs, model_key)
    agree = [agreement(p.a, p.b) for p in pairs]

    pos = [i for i, p in enumerate(pairs) if p.label == 1]
    neg = [i for i, p in enumerate(pairs) if p.label == 0]
    print(f"\nMean numeric agreement:   positives {_mean([agree[i] for i in pos]):.3f}   "
          f"negatives {_mean([agree[i] for i in neg]):.3f}")
    print(f"Mean cosine:              positives {_mean([cos[i] for i in pos]):.3f}   "
          f"negatives {_mean([cos[i] for i in neg]):.3f}")

    # The decisive view: only pairs the matcher already calls confident are at stake.
    hot_pos = [i for i in pos if cos[i] >= cutoff]
    hot_neg = [i for i in neg if cos[i] >= cutoff]
    print(f"\nAt or above the {cutoff:.2f} cutoff: {len(hot_pos)} positives, {len(hot_neg)} negatives.")
    if not hot_neg:
        print("No negative reaches the cutoff here — this dataset cannot answer the question.")

    print("\nDowngrade rule: move to `review` when numeric agreement <= gate.")
    print(f"  {'gate':>6}  {'negatives caught':>17}  {'positives lost':>15}  {'ratio':>7}")
    rows = []
    for g in gates:
        caught = sum(1 for i in hot_neg if agree[i] is not None and agree[i] <= g)
        lost = sum(1 for i in hot_pos if agree[i] is not None and agree[i] <= g)
        c_rate = round(caught / len(hot_neg), 4) if hot_neg else 0.0
        l_rate = round(lost / len(hot_pos), 4) if hot_pos else 0.0
        ratio = round(c_rate / l_rate, 2) if l_rate else None
        rows.append({"gate": g, "negatives_caught": caught, "negatives_caught_rate": c_rate,
                     "positives_lost": lost, "positives_lost_rate": l_rate, "ratio": ratio})
        print(f"  {g:>6.3f}  {caught:>8} ({c_rate:>5.1%})  {lost:>7} ({l_rate:>5.1%})  "
              f"{'n/a' if ratio is None else f'{ratio:>6.2f}x'}")

    artifact = {
        "dataset": name, "model_key": model_key, "cutoff": cutoff,
        "n_pairs": len(cases), "n_applicable": len(pairs), "coverage": coverage,
        "mean_agreement_positive": _mean([agree[i] for i in pos]),
        "mean_agreement_negative": _mean([agree[i] for i in neg]),
        "n_above_cutoff_positive": len(hot_pos), "n_above_cutoff_negative": len(hot_neg),
        "gates": rows,
        "examples": [
            {"cosine": round(cos[i], 4), "agreement": agree[i], "label": pairs[i].label,
             "a": pairs[i].a[:160], "b": pairs[i].b[:160]}
            for i in sorted(hot_neg, key=lambda i: (agree[i] if agree[i] is not None else 1.0))[:8]
        ],
    }
    if artifact["examples"]:
        print("\nNegatives above the cutoff with the least numeric agreement "
              "(what the signal would catch):")
        for ex in artifact["examples"][:5]:
            print(f"  cos {ex['cosine']:.3f}  agree {ex['agreement']:.2f}")
            print(f"    A: {ex['a'][:96]}")
            print(f"    B: {ex['b'][:96]}")

    _RESULTS_DIR.mkdir(exist_ok=True)
    out = _RESULTS_DIR / f"numeric_{name}.json"
    out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return artifact


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Does numeric agreement separate boilerplate from paraphrase?")
    ap.add_argument("datasets", nargs="*", default=["mrpc"], help=f"one or more of {sorted(DATASETS)}")
    ap.add_argument("--cutoff", type=float, default=0.78, help="the confident cutoff under test")
    ap.add_argument("--gates", default=",".join(str(g) for g in DEFAULT_GATES))
    ap.add_argument("--model-key", default="bi-encoder")
    args = ap.parse_args(argv)

    gates = [float(x) for x in args.gates.split(",") if x.strip()]
    ran = 0
    for name in args.datasets:
        if name not in DATASETS:
            print(f"NOTE: unknown dataset {name!r}; known: {sorted(DATASETS)}")
            continue
        try:
            run(name, cutoff=args.cutoff, gates=gates, model_key=args.model_key)
            ran += 1
        except DatasetNotAvailable as exc:
            print(f"SKIP [{name}]: {exc}\n")
    if not ran:
        print("Nothing ran. Fetch a dataset first:  python -m eval.fetch_datasets mrpc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
