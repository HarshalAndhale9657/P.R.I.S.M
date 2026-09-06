# CLAUDE.md — operating manual for AI assistants on P.R.I.S.M.

Read this first, then [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) (spec) and [`docs/DECISIONS.md`](docs/DECISIONS.md) (why).
Keep [`CHANGELOG.md`](CHANGELOG.md), [`docs/PROGRESS.md`](docs/PROGRESS.md) and [`TODO.md`](TODO.md) updated as you work.

## What this is
A **source-attribution originality checker**: a writer uploads a manuscript (+ references, and/or open-access
search) and gets verbatim / paraphrase / translated matches localized to the character, attributed to a source,
with an explicit `confident | review` band. Direction: an honest **publication-readiness coach** (ADR-0014).
**Hard boundary:** no detection-evasion features, ever.

The legacy stylometric authorship engine was **deleted** (ADR-0018). Do not resurrect it; it is in git history.

## Non-negotiable product guardrails
- **Self-check, non-accusatory.** No "plagiarised/guilty" verdicts.
- **Calibrated + abstaining.** A `review` match must never be presented as a confirmed copy (ADR-0017).
- **No unverified accusations.** Topical similarity is "related literature", never a "source match".
- **No claim without a measured number — on public data.** The synthetic 32-case set is a smoke test only.

## How to run
```powershell
cd backend
venv\Scripts\uvicorn main:app --host 127.0.0.1 --port 8000     # http://127.0.0.1:8000/docs
cd ..\frontend && python _serve.py 3000                          # http://127.0.0.1:3000 (no-cache)
```
Config is `PRISM_*` env vars (see `backend/.env.example`; source of truth `backend/app/settings.py`).

## Verify before you claim anything works
```powershell
cd backend
venv\Scripts\python -m ruff check .                              # blocking in CI
venv\Scripts\python -m pytest                                    # 100+ offline tests, coverage floor 80%
venv\Scripts\python scripts\eval_matcher.py                      # synthetic SMOKE (not a quality gate)
venv\Scripts\python -m eval.run_pairs stsb mrpc qqp --gate       # the REAL gate (fetch sets first: -m eval.fetch_datasets stsb mrpc qqp --limit 3000)
cd ..\e2e && npm install && node run.mjs                         # browser E2E (both servers running)
docker build -t prism-backend backend                            # the production image
```
CI (`.github/workflows/ci.yml`) runs all of these. Check a push without `gh`:
`curl -s https://api.github.com/repos/HarshalAndhale9657/P.R.I.S.M/actions/runs?per_page=5` — GitHub only emails on failure.

## Repo map
- `backend/main.py` — two-line shim → `app.create_app()`.
- `backend/app/` — HTTP layer: `settings.py` (all knobs), `schemas.py` (the API contract), `middleware.py`
  (request-id, body-size guard), `limits.py` (rate limiter), `routers/check.py`, `routers/health.py`, `factory.py`.
- `backend/worker/` — `executor.py` (bounded queue → 503), `store.py` (TTL job store + result cache; `JobStore`
  Protocol is the W7 Postgres seam), `runner.py` (job lifecycle; assembles the result incl. `engine` block).
- `backend/pipeline/` — `parse → retrieve → match → rerank(opt-in) → localize → triage` (+ skeleton coach/report).
  Collaborators are **injected**; tests patch `app.state.runner.matcher` / `.academic_search`.
- `backend/services/` — `document_parser.py` (checker-specific PDF/text), `plagiarism_matcher.py` (pure matcher),
  `academic_corpus.py` (OpenAlex + arXiv + keyed Semantic Scholar; `ProviderContext`/`Candidate`), `fulltext.py`
  (safe OA-PDF fetcher, ADR-0021), `triage.py` (deterministic remediation rules, ADR-0022),
  `embedding_cache.py` (per-sentence LRU, ADR-0023 — makes re-checks 6× faster),
  `local_embeddings.py` (bi-encoder singleton). `backend/utils/` — `TTLCache`.
- `backend/modelhub/` — model registry/cache (`get_embedder`, `get_cross_encoder`).
- `backend/eval/` — public-dataset harness; `gates.json` holds the per-dataset regression gates (ADR-0020). **No PAN.**
- `backend/training/` — W5 cross-encoder fine-tune kit (needs a GPU session; self-gating).
- `frontend/` — `index.html` + `js/check.js` + `css/styles.css`; no build step; API base via `<meta name="prism-api-base">`.
- `e2e/` — Playwright specs + fixtures (`node run.mjs`; `E2E_NETWORK=1` adds the OpenAlex spec).
- `deploy/` — `docker-compose.yml` + `Caddyfile` + runbook for the single-VPS deployment.
- `research/` — historical record of the pre-pivot engine. `research/datasets/pan/` is untracked and off-limits (ADR-0016).

## Conventions & gotchas
- Venv at `backend/venv`; Windows shell. LF line endings are enforced by `.gitattributes`.
- Matcher thresholds (ADR-0017): reporting floor `paraphrase_threshold=0.66`, confidence cutoff
  `confident_threshold=0.78`; verbatim is always confident. `overall` carries `confident_pct/review_pct/review_count`.
- The confidence cutoff **scales with corpus size** (ADR-0024): `base + 0.06·log10(N/500)`, capped at 0.92. Always
  quote `engine.confident_threshold` (applied), never the configured base — `eval/run_corpus.py` is the measurement.
- **Corpus-probe numbers are upper bounds** (ADR-0025). The public sets label *pairs*, not corpora: QQP holds
  unlabelled duplicate questions across pairs and STS-B/MRPC share source sentences, so a similarity-ranked corpus
  counts real matches as false positives. Never quote a corpus FPR without `--pool-only`, `--drop-above` or reading
  the `--examples` dump. And note **relevance beats size**: a *retrieved* 100-sentence corpus behaves like a random
  1 000–3 000-sentence one, so the size scaling counteracts the smaller half of the effect.
- Cross-encoder rerank (W4) is **opt-in** (`PRISM_RERANK=true`, image built with `PRISM_BAKE_RERANK=1`) until
  latency is measured on the real VPS.
- The job store is **in-process**: exactly one uvicorn worker / one replica until the Postgres store lands (W7).
- Every result's `engine` block drives the report's method footer — never hard-code thresholds in copy.
- Triage guidance must never suggest evasion; `tests/test_triage.py::test_guidance_never_suggests_evasion` enforces it.
- Frontend: vanilla JS, `esc()` everything before `innerHTML`, CSS variables only, don't rename IDs the JS reads.
- When you change product shape: add an ADR, update CHANGELOG `[Unreleased]`, log the session in `docs/PROGRESS.md`.

## Current priorities

**State as of 2026-09-06** (`main` @ `aaafa0c` + the ADR-0025 measurement pass, 188 tests, lint clean):
W1–W4b + W8 shipped · licensed PolyForm Noncommercial 1.0.0 · PAN purged from history.
Full narrative in [`docs/PROGRESS.md`](docs/PROGRESS.md) (newest entry first); decisions in ADR-0018…0025.

**Next, in order:**
1. **W6 — first deploy.** `deploy/README.md` is a complete runbook; it needs a VPS and nothing else. On the box:
   measure `timings_ms` on a real 20-page PDF with `PRISM_RERANK=true` and academic full text on, then set the
   rerank default and `PRISM_MAX_SOURCE_SENTENCES` **from those numbers**. Also point UptimeRobot at
   `/health/ready` and set `PRISM_CONTACT_EMAIL` + `PRISM_SENTRY_DSN`.
2. **Settle the confidence cutoff on the box.** ADR-0025 took this as far as public pair data allows: the probe
   was contaminated (its "no true match in the corpus" guarantee held only pairwise), the bounded FPR@0.78 at
   N=3 000 is 0.088 rather than 0.108, and *relevance* moved the number far more than *size*. `k`/`pivot` were
   deliberately left alone — the honest interval is wider than a refit would move them. What settles it is the
   **full pipeline against really-retrieved sources**: let the live retriever build a corpus for a real OA paper,
   then score passages known not to derive from it. Only then refit and refresh `eval/gates.json`.
3. **W5 fine-tune** — kit is ready and self-gating; needs one human-run Colab/Kaggle GPU session. "Do not ship"
   is a legitimate outcome.
4. **W7** — Supabase JWT + `PostgresJobStore` implementing the existing `worker.store.JobStore` Protocol.

**Owner decisions still open** (TODO 🔴, none blocking): the legal copyright holder for `NOTICE`; consent from
three past teammates for ~176 surviving boilerplate lines; confirming the old Vercel/Render demo is offline.

**Before claiming anything works, run the Verify block above.** This project's rule is that a number is only
real if it was measured — two defaults changed on 2026-09-06 purely because measurement contradicted intuition.
