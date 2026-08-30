# CLAUDE.md — operating manual for AI assistants on P.R.I.S.M.

Read this first, then [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) (spec) and [`docs/DECISIONS.md`](docs/DECISIONS.md) (why).
Keep [`CHANGELOG.md`](CHANGELOG.md), [`docs/PROGRESS.md`](docs/PROGRESS.md) and [`TODO.md`](TODO.md) updated as you work.

## What this is
An **originality checker** for a writer to self-check a paper: find **plagiarism**, **where** it is, and
**which source** it came from. Detection: verbatim + paraphrase + translated (shipped); AI-generated (deferred).
Corpora: user-uploaded references + OpenAlex + arXiv (shipped, concurrent/deduped; Crossref dropped — no abstracts).

> ✅ **Shipped & live.** The Originality Checker is the primary product: `frontend/index.html` +
> `frontend/js/check.js` → `POST /api/check` → `services/plagiarism_matcher.py` (+ `academic_corpus.py`).
> The old stylometric-authorship engine is **legacy**, kept at `frontend/authorship.html` (`/api/analyze`).
> Build on the checker, not the legacy spine. Detection quality is measured by `scripts/eval_matcher.py`.

## Non-negotiable product guardrails
- **Self-check, non-accusatory.** No "plagiarised/guilty" verdicts. Frame as an author's originality report.
- **Calibrated + abstaining.** Prefer a triage band + an explicit **"inconclusive"** state over a false "clean".
- **No unverified accusations.** A low-similarity/topical hit is "related literature (unverified lead)", never a "source match".
- **No claim without a measured number.** Don't reintroduce "100% accuracy / zero false positives / prosecutable".

## How to run
```powershell
cd backend && venv\Scripts\uvicorn main:app --host 127.0.0.1 --port 8000   # offline OK, no key needed
cd frontend && python _serve.py 3000                                        # http://localhost:3000 (no-cache)
```
Offline tests (no server/key): `venv\Scripts\python -m pytest` (unit + `/api/check` integration, in `backend/tests/`),
`venv\Scripts\python scripts\eval_matcher.py` (legacy 32-case smoke), `venv\Scripts\python _smoketest_check.py` (matcher).
**Real paraphrase benchmark (ADR-0016):** `venv\Scripts\python -m eval.run_pairs sample` (offline smoke); fetch real
public sets first with `venv\Scripts\python -m eval.fetch_datasets paws mrpc` then `... -m eval.run_pairs paws mrpc --gate`.
Browser E2E: `cd d:\PRISM-UI\_e2e && node check_e2e.mjs`. CI runs all of these.

## Checking CI without `gh`
`gh` is not installed, but the repo is **public**, so the Actions API is readable unauthenticated:
```bash
curl -s "https://api.github.com/repos/HarshalAndhale9657/P.R.I.S.M/actions/runs?per_page=5" \
  -H "Accept: application/vnd.github+json"        # .workflow_runs[]: status, conclusion, head_sha, jobs_url
curl -s "<jobs_url>" -H "Accept: application/vnd.github+json"   # per-job + per-step conclusions
```
Use this to confirm a push is green instead of waiting for an email — GitHub only emails on **failure**, so
"no email" is not proof of success. A `cancelled` run is usually normal: `ci.yml` sets
`concurrency: cancel-in-progress: true`, so a newer push cancels the older run.

## Repo map (essentials)
- `backend/main.py` — FastAPI app. **`POST /api/check`** = the checker; `_compute_check` runs the **pipeline** below.
- `backend/pipeline/` — **pluggable check pipeline** (ADR-0015/0016): `base.py` (CheckContext + Stage), `stages.py`
  (live RetrieveStage/MatchStage/LocalizeStage + skeleton rerank/ai_risk/triage/coach/report), `orchestrator.py`.
  Matcher + `academic_search` are **injected from main's globals** — keep it that way (the tests monkeypatch them).
- `backend/services/` — **checker:** `plagiarism_matcher.py` (verbatim + paraphrase + translated),
  `academic_corpus.py` (OpenAlex + arXiv), `local_embeddings.py` (MiniLM). **Legacy pipeline:** `pdf_parser`,
  `feature_engine`, `hdbscan_detector`, `gpt_analyzer`, `citation_forensics`, `source_tracer`, `report_generator`.
- `backend/modelhub/` — model registry/cache/version (the "models/ layer"; named `modelhub/` because `models.py`
  is the legacy Pydantic module). `get_embedder("bi-encoder")` today; W3 adds bge/gte ONNX, W4 the cross-encoder.
- `backend/eval/` — **public-dataset paraphrase harness** (ADR-0016, the real gate): `pairs.py` (unified
  `pairs.jsonl` schema + PAWS/MRPC/STS-B/QQP/PAWS-X loaders), `fetch_datasets.py`, `metrics.py`, `scorer.py`
  (embedder seam W3/W4 swap), `run_pairs.py` CLI, `data/sample/` (committed smoke set). **NO PAN.**
- `backend/scripts/eval_matcher.py` — legacy 32-case matcher eval (now a smoke; the real gate is `eval/`).
- `frontend/` — `index.html` + `js/check.js` = the checker; `authorship.html` + `js/{app,upload,heatmap,charts,
  citations,sources,report}.js` = legacy. `css/styles.css` (light design system). `_serve.py` = no-cache dev server.
- `research/` — ⚠️ `datasets/pan/` is PAN-2023 **style-change** data (legacy authorship task) — **not** for the
  matcher (no doc→source pairs). Do not use PAN (ADR-0016). Also old-engine ablation/eval results.

## Conventions & gotchas
- The venv lives at `backend/venv`. Use `venv\Scripts\python` / `venv\Scripts\pip`. Windows shell.
- Frontend has **no build step**. Don't hardcode colors — use CSS vars. Don't rename IDs the JS reads
  without updating both sides. The dev server sends `no-store`; still hard-refresh after big HTML changes.
- API-contract quirks to respect/fix: `clustering.confidence` is a *string* ("high/medium/low") in the
  main path but a float elsewhere; `noise_percentage` is **0–100** (not a 0–1 fraction). Prefer Pydantic
  response models when you touch this.
- `/api/check` is **async**: `POST` → `202 + job_id` (uploads validated synchronously), heavy work runs in a
  bounded in-process `ThreadPoolExecutor`; poll `GET /api/check/{job_id}`. The job store + content-hash cache
  are **in-process only** (not shared across workers / not restart-durable) — use Redis + a real queue to scale.
- Matcher thresholds (ADR-0017): verbatim min 8 words / k-gram 5. Paraphrase has **two** cutoffs — a reporting
  floor `paraphrase_threshold=0.66` and a confidence cutoff `confident_threshold=0.78`. Matches in between are
  reported with `confidence="review"` (explicit inconclusive band); at/above 0.78 they are `"confident"`.
  Verbatim is always confident. `overall` carries `confident_pct` / `review_pct` / `review_count`.
  **Never present a `review` match as confirmed plagiarism.**
- **Cross-encoder rerank (W4) is OPT-IN**: `PRISM_RERANK=1` (model via `PRISM_RERANK_MODEL`, default
  `cross-encoder-stsb`). It measurably cuts false positives (MRPC FPR 0.643→0.403) but adds a CPU forward pass
  per *borderline* pair, so it is off by default until the <60s latency budget is measured. It reranks only
  semantic matches with cosine in [0.60, 0.92] (verbatim is exact — never reranked), caps at 200 pairs, keeps
  the displayed bi-encoder `similarity`, and writes `rerank_score` + a re-decided `confidence`.
- ⚠️ **`scripts/eval_matcher.py` is a SMOKE TEST, not a quality gate** (ADR-0017): its synthetic negatives never
  reach the boundary (FPR 0.000 at every threshold 0.66-0.82), so its precision/FPR must never be quoted as
  accuracy. **The quality gate is `python -m eval.run_pairs`** on public data (STS-B/MRPC/QQP/PAWS). Real
  numbers + the separation-gap analysis live in `docs/PROGRESS.md`.
- When you change product shape: add an ADR, update CHANGELOG `[Unreleased]`, and log in `docs/PROGRESS.md`.

## Current priorities
See [`TODO.md`](TODO.md) / [`ROADMAP.md`](ROADMAP.md). Shipped: Phases 1–3 + report + eval. Next: honesty pass on the
legacy README, a light security baseline on `/api/check`, then robustness (pytest/TestClient, async job model).
