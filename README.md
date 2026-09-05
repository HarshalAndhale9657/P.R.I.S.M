# P.R.I.S.M. — Originality Checker

**Find what is copied, where it is, and which source it came from — honestly.**

PRISM is a source-attribution originality checker for authors. Upload a manuscript and the references it
draws on (or search open-access abstracts), and get every verbatim, paraphrased or translated passage
localized to the character, attributed to its source, and labelled with an explicit confidence band.
It is a **self-check aid, not a verdict**, and it never claims more than it has measured.

> **Status (2026-09-06):** the checker is functional and honestly benchmarked; it is **not yet a public service**.
> No accounts, no persistence, no paid tier — those are weeks 7–12 of [`docs/LAUNCH_PLAN.md`](docs/LAUNCH_PLAN.md).
> Longer-term direction: an honest *publication-readiness coach* (ADR-0014) that triages each flag and coaches
> the legitimate fix. **It will never include detection-evasion** (no auto-rewrite-to-lower-similarity, no "AI humanizer").

---

## What it does

| Detects | How | Evidence shown |
|---|---|---|
| **Verbatim** copying | k-gram anchoring + greedy extension (case/punctuation-insensitive) | exact spans on both sides |
| **Paraphrase** | sentence-embedding cosine (`paraphrase-multilingual-MiniLM-L12-v2`), optional cross-encoder rerank | side-by-side sentences, similarity, confidence band |
| **Translated** reuse | the paraphrase path, re-labelled when the language pair differs | language pair (e.g. FR→EN) |

Every semantic match carries `confidence: confident | review`. A `review` match is similar wording that
independently written text on the same topic can also reach — it is shown as **"Needs review"**, never as
a confirmed copy ([ADR-0017](docs/DECISIONS.md)). Academic sources come from OpenAlex, arXiv and (with a key)
Semantic Scholar; where a candidate has an open-access PDF, PRISM fetches it and matches against the **full
text**, otherwise against the abstract — and every source is labelled *full text* or *abstract only*. Reports
state their coverage plainly: **not** the full web or subscription databases.

## How well does it work? (measured, on public data)

The paraphrase scorer is benchmarked on public sentence-pair datasets, never on our own examples. At the
confident cutoff (0.78), bi-encoder baseline, validation splits:

| dataset | n | recall | false-positive rate | note |
|---|---|---|---|---|
| STS-B | 1,221 | 0.90 | **0.10** | graded similarity, binarised |
| QQP | 3,000 | 0.86 | **0.26** | duplicate questions |
| MRPC | 408 | 0.79 | **0.44** | news paraphrase; hard same-topic negatives |
| PAWS | 2,000 | 1.00 | 0.997 | adversarial word-order swaps — *unsolvable for bi-encoders*; reported, not gated |

These numbers are **regression gates in CI** (`backend/eval/gates.json`), not marketing. They say the same
thing the UI says: high-overlap, same-topic text is exactly where a similarity score is least trustworthy,
which is why borderline matches are labelled for review instead of asserted. A pretrained cross-encoder
reranker (opt-in, `PRISM_RERANK=1`) cuts MRPC's FPR to 0.40 at the reporting floor; see
[`docs/PROGRESS.md`](docs/PROGRESS.md) for the full measurement history including the negative results.

## Architecture

```
frontend/ (vanilla JS, no build)  ──►  POST /api/v1/check  (202 + job_id)  ──►  GET /api/v1/check/{id}
                                              │
                                       app/  (FastAPI: settings · schemas · rate limit · request-id · health)
                                              │
                                     worker/ (bounded executor · TTL job store · result cache · runner)
                                              │
        pipeline/  parse ─► retrieve ─► match ─► rerank (opt-in) ─► localize ─► [triage ─► coach ─► report]
                     │          │          │          │
   services/document_parser  academic_corpus + fulltext  plagiarism_matcher   modelhub/ (model registry)
                                                                     eval/    (public-dataset harness + gates)
```

- **Bounded by arithmetic, not hope:** worst-case upload memory = `max_pending_jobs × max_request_bytes`;
  the API answers `503 Retry-After` when the queue is full and `429` when one client submits too often.
- **Ephemeral by default:** manuscripts live in process memory for `PRISM_JOB_TTL_SECONDS` (30 min) and are gone.
- **Observable:** `X-Request-ID` in/out, `request_id`/`job_id` on every log line, per-stage `timings_ms`
  in every result, `/health` + `/health/ready`, optional Sentry.
- **Pluggable:** every stage is injectable; the eval harness runs the same code the API runs.

## Run it locally

```bash
cd backend
python -m venv venv && venv/Scripts/pip install -r requirements-dev.txt     # Windows; use venv/bin on Unix
venv/Scripts/uvicorn main:app --host 127.0.0.1 --port 8000                  # http://127.0.0.1:8000/docs
cd ../frontend && python _serve.py 3000                                     # http://127.0.0.1:3000
```
First check downloads the ~470 MB embedding model once. Configuration: [`backend/.env.example`](backend/.env.example).

**Tests:** `cd backend && venv/Scripts/pytest` (102 offline tests) · `ruff check .` · browser E2E in [`e2e/`](e2e/)
· real benchmark `python -m eval.fetch_datasets stsb mrpc && python -m eval.run_pairs stsb mrpc --gate`.

**Deploy:** one VPS, Docker Compose + Caddy — [`deploy/README.md`](deploy/README.md).

## Project map

| | |
|---|---|
| [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) | what PRISM is, what's built, guardrails |
| [`docs/LAUNCH_PLAN.md`](docs/LAUNCH_PLAN.md) | the 12-week plan to a paid launch (authoritative) |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | ADRs — every real decision and why (20 so far) |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | session log with every measurement, including the ones that went badly |
| [`ROADMAP.md`](ROADMAP.md) · [`TODO.md`](TODO.md) | what's next |
| [`CLAUDE.md`](CLAUDE.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) | how to work on it |
| [`SECURITY.md`](SECURITY.md) | security posture and reporting |
| [`research/`](research/) | the pre-pivot stylometric engine's research record (historical) |

## Principles (non-negotiable)

1. **Self-check, non-accusatory.** No "guilty" verdicts; an author's originality report.
2. **Calibrated and willing to say "inconclusive".** A review band beats a false clean or a false accusation.
3. **No number without a measurement — on public data.** Our own examples are a smoke test, never a claim.
4. **No detection-evasion, ever.** Coaching shows the source and helps the author fix it honestly.

## History

PRISM began (April 2026, DevClash hackathon) as a stylometric *authorship* detector. Honest evaluation found
that engine near-noise (F1 ≈ 0.40, [`research/HONEST_AUDIT.md`](research/HONEST_AUDIT.md)), and the project
pivoted to source-attribution plagiarism in August 2026 (ADR-0001). The legacy engine was removed in September
2026 (ADR-0018); it remains in git history.

## License

Not yet chosen — all rights reserved by the contributors until a licence is added. See `TODO.md`.
