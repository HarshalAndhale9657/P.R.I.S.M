"""
P.R.I.S.M. — Public dataset fetcher (ADR-0016: ready-made public sets only, NO PAN)
===================================================================================
Explicitly downloads a sanctioned public sentence-pair dataset via HuggingFace
`datasets` and writes it in our unified JSONL schema to eval/data/<name>/pairs.jsonl.
Nothing is fetched implicitly — you run this on purpose, per dataset.

    python -m eval.fetch_datasets paws
    python -m eval.fetch_datasets mrpc stsb --split validation --limit 2000
    python -m eval.fetch_datasets pawsx --lang de

Requires `pip install datasets`. Licences/terms are the datasets' own — see
eval/data/README.md. These sets are for evaluation of OUR pipeline; we do not
redistribute them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.pairs import DATA_DIR, DATASETS


def _write(name: str, rows) -> Path:
    out = DATA_DIR / DATASETS[name].relpath
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    print(f"[fetch] wrote {n} pairs -> {out}")
    return out


def _pos_neg_stratum(label: int, neg_stratum: str) -> str:
    return "paraphrase" if label == 1 else neg_stratum


def _load_split(path: str, config: str, split: str):
    """load_dataset that works across `datasets` versions (newer ones require
    trust_remote_code for script datasets; older ones reject the kwarg)."""
    from datasets import load_dataset
    try:
        return load_dataset(path, config, split=split, trust_remote_code=True)
    except TypeError:
        return load_dataset(path, config, split=split)


def _adapt(name: str, split: str, limit: int, lang: str):
    """Yield unified dicts for the given dataset via HF `datasets`. Uses the
    parquet-native Hub ids so no dataset script needs to run."""
    if name == "paws":
        ds = _load_split("google-research-datasets/paws", "labeled_final", split)
        for i, ex in enumerate(ds):
            if limit and i >= limit:
                break
            yield {"a": ex["sentence1"], "b": ex["sentence2"], "label": int(ex["label"]),
                   "stratum": _pos_neg_stratum(int(ex["label"]), "high_overlap_negative"),
                   "id": f"paws-{split}-{i}"}

    elif name == "mrpc":
        ds = _load_split("nyu-mll/glue", "mrpc", split)
        for i, ex in enumerate(ds):
            if limit and i >= limit:
                break
            yield {"a": ex["sentence1"], "b": ex["sentence2"], "label": int(ex["label"]),
                   "stratum": _pos_neg_stratum(int(ex["label"]), "non_paraphrase"),
                   "id": f"mrpc-{split}-{i}"}

    elif name == "stsb":
        ds = _load_split("nyu-mll/glue", "stsb", split)
        for i, ex in enumerate(ds):
            if limit and i >= limit:
                break
            score = float(ex["label"])          # 0..5
            if score >= 4.0:
                label = 1
            elif score <= 3.0:
                label = 0
            else:
                continue                        # drop the ambiguous 3-4 band
            yield {"a": ex["sentence1"], "b": ex["sentence2"], "label": label,
                   "stratum": "graded", "id": f"stsb-{split}-{i}"}

    elif name == "qqp":
        ds = _load_split("nyu-mll/glue", "qqp", split)
        for i, ex in enumerate(ds):
            if limit and i >= limit:
                break
            yield {"a": ex["question1"], "b": ex["question2"], "label": int(ex["label"]),
                   "stratum": _pos_neg_stratum(int(ex["label"]), "non_paraphrase"),
                   "id": f"qqp-{split}-{i}"}

    elif name == "pawsx":
        ds = _load_split("google-research-datasets/paws-x", lang, split)
        for i, ex in enumerate(ds):
            if limit and i >= limit:
                break
            yield {"a": ex["sentence1"], "b": ex["sentence2"], "label": int(ex["label"]),
                   "stratum": _pos_neg_stratum(int(ex["label"]), "high_overlap_negative"),
                   "id": f"pawsx-{lang}-{split}-{i}"}

    else:
        raise SystemExit(f"No fetch adapter for {name!r}. Known: {sorted(DATASETS)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch public paraphrase datasets (no PAN).")
    ap.add_argument("datasets", nargs="+", help=f"one or more of: {sorted(k for k in DATASETS if k != 'sample')}")
    ap.add_argument("--split", default="validation", help="dataset split (default: validation)")
    ap.add_argument("--limit", type=int, default=0, help="max pairs (0 = all)")
    ap.add_argument("--lang", default="en", help="language for pawsx (default: en)")
    args = ap.parse_args(argv)

    try:
        import datasets  # noqa: F401
    except ImportError:
        print("This needs HuggingFace `datasets`.  Install it:  pip install datasets", file=sys.stderr)
        return 2

    for name in args.datasets:
        if name not in DATASETS or name == "sample":
            print(f"NOTE: cannot fetch {name!r} (known: {sorted(k for k in DATASETS if k != 'sample')})")
            continue
        print(f"[fetch] {name}  split={args.split}  limit={args.limit or 'all'}")
        _write(name, _adapt(name, args.split, args.limit, args.lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
