# W5 — cross-encoder fine-tune (the one sanctioned training step)

ADR-0016 permits **exactly one** fine-tune: the paraphrase **cross-encoder reranker**, on a free
Colab/Kaggle GPU, shipped **only if it beats the pretrained model on our real benchmark without
raising FPR**. [`finetune_cross_encoder.py`](finetune_cross_encoder.py) trains it *and enforces that
gate itself* — it exits non-zero and tells you not to ship if the tune doesn't earn its place.

## Why we're here (measured — see `docs/PROGRESS.md`)
Pretrained-first is exhausted: four models, no single winner.

| model | PAWS FPR@0.66 | PAWS Brier | MRPC F1 | MRPC FPR@0.66 |
|---|---|---|---|---|
| MiniLM (bi-encoder) | 1.00 | 0.538 | 0.84 | 0.64 |
| all-mpnet-base-v2 | 0.99 | 0.516 | 0.84 | 0.64 |
| **CE-stsb** | 0.99 | 0.519 | **0.865** | **0.40** |
| **CE-qqp** | **0.85** | **0.430** | 0.788 | 0.52 |

The specific weakness is PAWS-style **word-order / semantic-role swaps** — and PAWS ships a
**49k-pair train split**, so a fine-tune targets exactly that gap.

## Run it on Colab (free T4, ~20–40 min)
**Runtime → Change runtime type → T4 GPU**, then three cells:

```python
!git clone --depth 1 https://github.com/HarshalAndhale9657/P.R.I.S.M
%cd P.R.I.S.M/backend
```
```python
# Pinned: sentence-transformers changed the CrossEncoder training API in v4+;
# this script uses the classic .fit() path.
!pip install -q "sentence-transformers>=3.0,<4.0" "datasets>=2.19" accelerate
```
```python
!python training/finetune_cross_encoder.py --limit 20000 --epochs 1
```

Kaggle is the same (enable GPU in Settings → Accelerator).

Useful flags: `--full` (all 49k PAWS pairs, slower/stronger) · `--epochs 2` · `--base-model
cross-encoder/quora-roberta-base` (start from the PAWS-stronger model instead) · `--batch-size 32`
(if VRAM allows) · `--export-onnx`.

## What it does
1. Loads **validation** splits first (fails fast on data problems).
2. Scores the **pretrained** model on them → the baseline, computed *here*, apples-to-apples.
3. Trains on **train** splits only — **no leakage**, since our published numbers are validation-split.
4. Re-scores and applies the **ship/no-ship gate**.
5. Writes `w5_report.json` — the evidence for the decision.

Metrics come from the repo's own `eval/metrics.py`, so the numbers are directly comparable to
`python -m eval.run_pairs` (same definitions, same stratification — no reimplementation drift).

## The gate (all three must hold, per dataset)
| check | rule |
|---|---|
| FPR@0.66 | must **not** increase |
| best-F1 | must improve by **≥ 0.01** (a real gain, not noise) |
| Brier | must **not** worsen |

Exit codes: `0` = ship · `2` = trained fine but didn't earn its place · `1` = error.

> **"Do not ship" is a legitimate, expected outcome — not a failed experiment.** ADR-0016 explicitly
> allows keeping the pretrained model and banking W5 as schedule buffer. Shipping a regression to
> justify the effort is the one thing we must not do.

## After the run
1. Download `models/prism-cross-encoder-v1/w5_report.json`.
2. Paste the before/after numbers into `docs/PROGRESS.md` (they are the record).
3. **If SHIP:** export ONNX (`optimum-cli export onnx --model <out> <out>-onnx`), publish the
   weights somewhere fetchable, register it in `backend/modelhub/registry.py` as a `cross-encoder`
   entry, and wire `RerankStage`. **CPU inference only in production** (ADR-0016).
4. **If NO-SHIP:** record the negative result in `docs/PROGRESS.md` — it is genuinely useful
   evidence that pretrained is good enough here — and keep `cross-encoder-stsb`.

## Deviation from ADR-0016, stated plainly
ADR-0016 said "LoRA". This does a **full fine-tune** instead: the cross-encoder is `roberta-base`
(~125M params), which trains comfortably on a free T4 and generally beats LoRA at this scale. LoRA
exists to make *large* models trainable; here it would add a `peft` dependency for no benefit.
If we later move to a much larger reranker, revisit this.
