"""
P.R.I.S.M. — W5: selective cross-encoder fine-tune (the ONE sanctioned training step)
=====================================================================================
ADR-0016 permits exactly one fine-tune: the paraphrase **cross-encoder reranker**,
on free Colab/Kaggle GPU, shipped **only if it beats the pretrained model on our
real benchmark without raising FPR**. This script trains it AND enforces that gate
itself, so the decision is made by measurement rather than by hope.

Why we reached for this (measured, see docs/PROGRESS.md):
  * pretrained-first is exhausted — 4 models tried, no single winner:
      CE-stsb  : best on MRPC (F1 0.865, FPR 0.403) but PAWS FPR 0.99
      CE-qqp   : best on PAWS  (FPR 0.85, Brier 0.430) but MRPC regresses to 0.788
  * PAWS-style word-order/role swaps are the specific weakness; PAWS ships a
    49k-pair train split, so a fine-tune targets exactly that gap.

Deviation from ADR-0016 (deliberate, documented): ADR-0016 said "LoRA". The
cross-encoder is roberta-base (~125M params) — a FULL fine-tune fits fine on a
free T4 and generally beats LoRA at this scale. LoRA exists to make *large* models
trainable; here it would add a `peft` dependency for no benefit. Full FT it is.

TRAIN/TEST HYGIENE: we train ONLY on **train** splits and evaluate ONLY on the
**validation** splits that produced our published baselines. No leakage.

Usage (Colab/Kaggle — see training/README.md):
    python training/finetune_cross_encoder.py --limit 20000
    python training/finetune_cross_encoder.py --full --epochs 2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Make `eval.*` importable whether run from backend/ or elsewhere.
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from eval import metrics as M  # noqa: E402  (our real metric definitions — keep in lock-step)

# The operating threshold the product uses for a *confident* match (ADR-0017).
CONFIDENT_THRESHOLD = 0.78

# Published pretrained baselines to beat (docs/PROGRESS.md). A fine-tune only ships
# if it improves on the BEST pretrained result per dataset.
BASELINES = {
    "paws": {"model": "cross-encoder-qqp", "fpr_at_066": 0.852, "brier": 0.4301, "f1_best": 0.634},
    "mrpc": {"model": "cross-encoder-stsb", "fpr_at_066": 0.403, "brier": 0.1563, "f1_best": 0.865},
}


def log(msg: str) -> None:
    print(f"[w5] {msg}", flush=True)


# ── Data ─────────────────────────────────────────────────────────────────────
def load_pairs(name: str, split: str, limit: int = 0):
    """(a, b, label) triples from a public set. Mirrors eval/fetch_datasets.py."""
    from datasets import load_dataset

    if name == "paws":
        ds = load_dataset("google-research-datasets/paws", "labeled_final", split=split)
        cols = ("sentence1", "sentence2")
    elif name == "mrpc":
        ds = load_dataset("nyu-mll/glue", "mrpc", split=split)
        cols = ("sentence1", "sentence2")
    elif name == "qqp":
        ds = load_dataset("nyu-mll/glue", "qqp", split=split)
        cols = ("question1", "question2")
    elif name == "stsb":
        ds = load_dataset("nyu-mll/glue", "stsb", split=split)
        out = []
        for i, ex in enumerate(ds):
            if limit and i >= limit:
                break
            s = float(ex["label"])
            if s >= 4.0:
                out.append((ex["sentence1"], ex["sentence2"], 1))
            elif s <= 3.0:
                out.append((ex["sentence1"], ex["sentence2"], 0))
        return out
    else:
        raise SystemExit(f"unknown dataset {name!r}")

    out = []
    for i, ex in enumerate(ds):
        if limit and i >= limit:
            break
        out.append((ex[cols[0]], ex[cols[1]], int(ex["label"])))
    return out


# ── Evaluation (identical metric definitions to eval/run_pairs.py) ────────────
def evaluate(model, pairs, title: str) -> dict:
    scores = [max(0.0, min(1.0, float(s)))
              for s in model.predict([(a, b) for a, b, _ in pairs], show_progress_bar=False)]
    labels = [y for _, _, y in pairs]

    at_066 = M.binary_metrics(scores, labels, 0.66)
    at_conf = M.binary_metrics(scores, labels, CONFIDENT_THRESHOLD)
    best_f1 = M.best_threshold(scores, labels, objective="f1")
    best_r = M.best_threshold(scores, labels, objective="recall", max_fpr=0.15)
    sep = M.separation(scores, labels)
    brier = M.brier(scores, labels)

    log(f"--- {title} ---")
    log(f"  @0.66 : P={at_066.precision:.3f} R={at_066.recall:.3f} F1={at_066.f1:.3f} FPR={at_066.fpr:.3f}")
    log(f"  @{CONFIDENT_THRESHOLD:.2f} : P={at_conf.precision:.3f} R={at_conf.recall:.3f} "
        f"F1={at_conf.f1:.3f} FPR={at_conf.fpr:.3f}")
    log(f"  best-F1 t={best_f1.threshold:.2f} F1={best_f1.f1:.3f} FPR={best_f1.fpr:.3f}")
    log(f"  recall@FPR<=0.15: R={best_r.recall:.3f} (t={best_r.threshold:.2f})")
    log(f"  Brier={brier:.4f}  separation gap={sep['mean_gap']:.3f} "
        f"(pos {sep['mean_positive']:.3f} / neg {sep['mean_negative']:.3f})")
    return {
        "at_0.66": at_066.as_dict(), f"at_{CONFIDENT_THRESHOLD}": at_conf.as_dict(),
        "best_f1": best_f1.as_dict(), "best_recall_at_fpr_cap": best_r.as_dict(),
        "brier": brier, "separation": sep,
    }


def gate(before: dict, after: dict, dataset: str) -> tuple[bool, list[str]]:
    """ADR-0016: ship ONLY if it beats pretrained without raising FPR."""
    reasons = []
    b066, a066 = before["at_0.66"], after["at_0.66"]
    bf1, af1 = before["best_f1"], after["best_f1"]

    fpr_ok = a066["fpr"] <= b066["fpr"] + 1e-9
    f1_ok = af1["f1"] >= bf1["f1"] + 0.01          # a real gain, not noise
    brier_ok = after["brier"] <= before["brier"] + 1e-9

    reasons.append(f"FPR@0.66 {b066['fpr']:.3f} -> {a066['fpr']:.3f} "
                   f"({'OK' if fpr_ok else 'REGRESSED'})")
    reasons.append(f"best-F1 {bf1['f1']:.3f} -> {af1['f1']:.3f} "
                   f"({'OK (+>=0.01)' if f1_ok else 'insufficient gain'})")
    reasons.append(f"Brier {before['brier']:.4f} -> {after['brier']:.4f} "
                   f"({'OK' if brier_ok else 'REGRESSED'})")
    return (fpr_ok and f1_ok and brier_ok), reasons


# ── Main ─────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="W5 cross-encoder fine-tune + ship/no-ship gate.")
    ap.add_argument("--base-model", default="cross-encoder/stsb-roberta-base",
                    help="pretrained cross-encoder to start from (also the baseline to beat)")
    ap.add_argument("--train-sets", nargs="+", default=["paws", "mrpc"],
                    help="datasets to train on (train splits only)")
    ap.add_argument("--eval-sets", nargs="+", default=["paws", "mrpc"],
                    help="datasets to evaluate on (validation splits only)")
    ap.add_argument("--limit", type=int, default=20000, help="cap train pairs per set (0/--full = all)")
    ap.add_argument("--full", action="store_true", help="use the full train splits")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--out", default="models/prism-cross-encoder-v1")
    ap.add_argument("--export-onnx", action="store_true", help="also export ONNX for CPU inference")
    args = ap.parse_args(argv)

    limit = 0 if args.full else args.limit

    import torch
    from sentence_transformers import CrossEncoder, InputExample
    from torch.utils.data import DataLoader

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    log(f"device={dev}  base={args.base_model}")
    if dev == "cpu":
        log("WARNING: no GPU detected — training will be very slow. In Colab: Runtime > Change runtime type > T4 GPU.")

    # ---- Eval sets FIRST (validation splits only) so we fail fast on data problems.
    eval_data = {}
    for name in args.eval_sets:
        pairs = load_pairs(name, "validation", limit=3000)
        eval_data[name] = pairs
        n_pos = sum(y for _, _, y in pairs)
        log(f"eval[{name}]: {len(pairs)} pairs ({n_pos} pos / {len(pairs) - n_pos} neg)")

    # ---- Baseline BEFORE training (same model, same data, apples to apples).
    log("scoring pretrained baseline ...")
    base = CrossEncoder(args.base_model, device=dev)
    before = {name: evaluate(base, pairs, f"BEFORE {name}") for name, pairs in eval_data.items()}

    # ---- Train.
    train_samples = []
    for name in args.train_sets:
        rows = load_pairs(name, "train", limit=limit)
        log(f"train[{name}]: {len(rows)} pairs")
        train_samples += [InputExample(texts=[a, b], label=float(y)) for a, b, y in rows]
    log(f"total train pairs: {len(train_samples)}")

    model = CrossEncoder(args.base_model, num_labels=1, device=dev)
    loader = DataLoader(train_samples, shuffle=True, batch_size=args.batch_size)
    warmup = max(1, int(len(loader) * args.epochs * 0.1))
    t0 = time.time()
    log(f"training: epochs={args.epochs} bs={args.batch_size} lr={args.lr} warmup={warmup}")
    model.fit(train_dataloader=loader, epochs=args.epochs, warmup_steps=warmup,
              optimizer_params={"lr": args.lr}, output_path=args.out, show_progress_bar=True)
    log(f"trained in {time.time() - t0:.0f}s -> {args.out}")

    # ---- Evaluate AFTER + enforce the gate.
    tuned = CrossEncoder(args.out, device=dev)
    after = {name: evaluate(tuned, pairs, f"AFTER {name}") for name, pairs in eval_data.items()}

    log("=" * 70)
    log("SHIP/NO-SHIP GATE (ADR-0016: beat pretrained, do not raise FPR)")
    log("=" * 70)
    verdicts = {}
    for name in eval_data:
        ok, reasons = gate(before[name], after[name], name)
        verdicts[name] = ok
        log(f"[{name}] {'PASS' if ok else 'FAIL'}")
        for r in reasons:
            log(f"    {r}")

    ship = all(verdicts.values())
    log("=" * 70)
    log(f"VERDICT: {'SHIP IT' if ship else 'DO NOT SHIP — keep the pretrained cross-encoder'}")
    if not ship:
        log("Per ADR-0016 this is a legitimate outcome, not a failure: the pretrained")
        log("model stays, and W5 is banked as schedule buffer. Do NOT ship a regression.")
    log("=" * 70)

    report = {
        "base_model": args.base_model, "train_sets": args.train_sets,
        "eval_sets": args.eval_sets, "limit": limit, "epochs": args.epochs,
        "batch_size": args.batch_size, "lr": args.lr,
        "before": before, "after": after,
        "verdicts": verdicts, "ship": ship,
        "published_baselines": BASELINES,
    }
    out = Path(args.out) / "w5_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"report -> {out}")
    log("Copy this JSON back into the repo (docs/PROGRESS.md) — it is the evidence for the decision.")

    if ship and args.export_onnx:
        try:
            from transformers.onnx import export  # noqa: F401
            log("ONNX export: use `optimum-cli export onnx --model "
                f"{args.out} {args.out}-onnx` (install `optimum[exporters]`).")
        except Exception:
            log("ONNX export: install `optimum[exporters]`, then "
                f"`optimum-cli export onnx --model {args.out} {args.out}-onnx`")

    return 0 if ship else 2   # 2 = trained fine, but did not earn its place


if __name__ == "__main__":
    sys.exit(main())
