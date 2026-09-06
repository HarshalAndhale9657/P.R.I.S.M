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

## Known contamination — read this before quoting a corpus-probe number (ADR-0025)

These sets label **pairs**, not corpora. Two things follow, and both were measured, not guessed:

- **QQP contains unlabelled duplicates across different pairs.** A probe that excludes a query's
  *labelled* partner from the corpus still leaves near-identical questions in it
  ("What is the funniest joke you ever heard?" / "What is funniest joke you've ever heard?" — 0.99).
  Anything that ranks the corpus by similarity promotes those straight to the top, so they are
  counted as false positives when they are real matches.
- **STS-B and MRPC share source sentences.** Using one as a distractor pool for the other puts exact
  duplicates in the corpus (a "Lord Falconer …" sentence matched at 0.998 across the two).

So a corpus-scale FPR from a single dataset is an **upper bound**, not a measurement.
`eval/run_corpus.py` has three defences — `--pool-only` (corpus entirely from other datasets),
`--drop-above` (remove corpus sentences within X of any query, and report how many), and
`--examples` (dump the top-scoring flags so a human can *see* whether they are real paraphrases).
Use at least one of them before quoting a number.

Fetched files are git-ignored by default — treat them as a local cache.
