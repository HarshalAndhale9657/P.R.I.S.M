# eval/data — benchmark datasets (public, fetched on demand)

The paraphrase pillar of the matcher is measured against **ready-made public
sentence-pair datasets** (ADR-0016). This directory holds them in one unified
schema. **No PAN** — the on-disk `research/datasets/pan/` is the PAN-2023
*style-change* task (wrong task; no doc→source pairs), and the owner excluded PAN.

## What's committed vs fetched
- `sample/pairs.jsonl` — **committed.** A tiny hand-made smoke set (10 pairs) so
  the harness runs end-to-end offline. **NOT a benchmark** — never quote its numbers.
- Everything else is **fetched on demand** (licences + size ⇒ not vendored):

```
pip install datasets
python -m eval.fetch_datasets paws            # hard paraphrase / high-overlap negatives
python -m eval.fetch_datasets mrpc stsb qqp   # more paraphrase / similarity sets
python -m eval.fetch_datasets pawsx --lang de # multilingual (translated pillar)
```

Then measure the current pipeline against them:

```
python -m eval.run_pairs paws mrpc --gate
```

## Unified schema (`<name>/pairs.jsonl`, one JSON object per line)
```json
{"a": "text A", "b": "text B", "label": 1, "stratum": "paraphrase", "id": "paws-42"}
```
- `label`: **1** = paraphrase/positive, **0** = negative.
- `stratum`: grouping for per-stratum FPR (the safety view):
  - `paraphrase` — positives
  - `high_overlap_negative` — non-paraphrase with high lexical overlap (the ESL /
    boilerplate trap; **PAWS is built for exactly this**)
  - `non_paraphrase` — ordinary negative
  - `graded` — binarized from a graded-similarity set (STS-B: sim ≥ 4/5 → 1, ≤ 3 → 0)

## Datasets & licences (their terms, not ours — we don't redistribute)
| name | source | homepage |
|------|--------|----------|
| paws | PAWS (Google Research), research use | https://github.com/google-research-datasets/paws |
| mrpc | MSR Paraphrase Corpus (GLUE) | https://gluebenchmark.com/tasks |
| stsb | STS Benchmark | https://ixa2.si.ehu.eus/stswiki/index.php/STSbenchmark |
| qqp  | Quora Question Pairs (GLUE) | https://gluebenchmark.com/tasks |
| pawsx | PAWS-X (multilingual) | https://github.com/google-research-datasets/paws/tree/master/pawsx |

Fetched files are git-ignored by default — treat them as a local cache.
