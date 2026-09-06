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
venv\Scripts\python -m pip_audit --strict --no-deps --disable-pip -r requirements.lock   # blocking in CI (ADR-0027)
venv\Scripts\python scripts\pg_tests.py                             # the WHOLE suite vs an embedded Postgres — no skips (ADR-0031)
cd ..\e2e && npm install && node run.mjs                         # browser E2E (both servers running)
docker build -t prism-backend backend                            # the production image
```
CI (`.github/workflows/ci.yml`) runs all of these. Check a push without `gh`:
`curl -s https://api.github.com/repos/HarshalAndhale9657/P.R.I.S.M/actions/runs?per_page=5` — GitHub only emails on failure.

## Repo map
- `backend/main.py` — two-line shim → `app.create_app()`.
- `backend/app/` — HTTP layer: `settings.py` (all knobs), `schemas.py` (the API contract), `auth.py` (JWT →
  `Principal`, ADR-0030), `middleware.py`
  (request-id, body-size guard), `limits.py` (rate limiter), `routers/check.py`, `routers/health.py`, `factory.py`.
- `backend/worker/` — `executor.py` (bounded queue → 503), `store.py` (in-memory TTL job store; the `JobStore`
  Protocol), `postgres_store.py` (the durable one, ADR-0029), `runner.py` (job lifecycle; assembles the result).
- `backend/pipeline/` — `parse → retrieve → match → rerank(opt-in) → localize → triage → coach(opt-in)`; the report
  and re-check are assembled by the runner (ADR-0032).
  Collaborators are **injected**; tests patch `app.state.runner.matcher` / `.academic_search`.
- `backend/services/` — `document_parser.py` (checker-specific PDF/text), `plagiarism_matcher.py` (pure matcher),
  `academic_corpus.py` (OpenAlex + arXiv + keyed Semantic Scholar; `ProviderContext`/`Candidate`), `fulltext.py`
  (safe OA-PDF fetcher, ADR-0021), `triage.py` (deterministic remediation rules, ADR-0022),
  `embedding_cache.py` (per-sentence LRU, ADR-0023 — makes re-checks 6× faster),
  `numeric_guard.py` (same shape, different figures → `review`, ADR-0026), `coach.py` (model phrases the fix,
  matcher post-filters it, ADR-0031), `report.py` (risk band + checklist + re-check diff, ADR-0032),
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
- **Plain text is unwrapped before matching** (`document_parser._unwrap`, ADR-0028): a line break is joined only
  when the previous line does not finish a sentence and the next begins lower-case. Without it a 60-column `.txt`
  manuscript is compared line by line — measured, that turned a real paraphrase from **0 matches into 2 at 0.875**.
  PDFs go through `_clean_block` instead; the paths differ because their inputs do, but the same prose must read
  the same either way (there is a test).
- **Sentence splitting lives in `plagiarism_matcher.split_sentences`** (ADR-0026), and its exceptions are load-
  bearing: a period between digits, a listed abbreviation, an initial or a following lower-case letter is not a
  boundary. The naive version truncated every sentence containing a decimal and *dropped* the remainder. If you
  touch it, the tests in `test_matcher.py` pin `p = 0.05`, `Fig. 3`, `et al.`, `J. R. R.` and URLs.
- **The numeric guard** (ADR-0026) moves a confident paraphrase to `review` when it and its source state numbers
  but share ≤`PRISM_NUMERIC_GUARD_GATE` (0.20) of them. Paraphrase only, one band only, never hidden. When you
  write copy about the `review` band, remember there are now **two** reasons for it — the cutoff and this — and
  saying the wrong one is a false statement about the check.
- **Dependencies are audited against `requirements.lock`, not a fresh resolve** (ADR-0027) — the lock is what the
  production image installs. Keep the lock **ASCII**: `pip-audit` decodes requirements with the platform codepage
  and an em dash in the header broke it on Windows. Regenerate the lock with the `uv pip compile` line in its own
  header, then re-run the audit.
- Cross-encoder rerank (W4) is **opt-in** (`PRISM_RERANK=true`, image built with `PRISM_BAKE_RERANK=1`) until
  latency is measured on the real VPS.
- **Job state:** in-process memory by default; set `PRISM_DATABASE_URL` for `PostgresJobStore` (ADR-0029) — then
  state survives restarts and any replica can serve `GET /check/{id}`. Execution is still the in-process executor
  on the accepting replica, and the result cache + per-IP limiter are still in-process. Unset = **one replica**.
  The `JobStore` contract in `tests/test_job_store_contract.py` runs against both; CI supplies a real Postgres and
  fails if that half was skipped. Locally: `PRISM_TEST_DATABASE_URL=postgresql://…` to run it yourself.
- **Auth (ADR-0030):** unconfigured = anonymous, unchanged. `PRISM_AUTH_JWT_SECRET` (HS256) or `PRISM_AUTH_JWKS_URL`
  turns verification on; `PRISM_AUTH_REQUIRED` gates the endpoints. Rules with tests behind them: a presented token
  is always verified (bad = 401 even when optional), ownership is **404 not 403**, quota is a ledger (`worker/usage.py`)
  and over it is **402**. Signed-in users skip the per-IP limiter. Never read token claims beyond `sub/email/role`.
- **Coaching (ADR-0031):** dark unless `PRISM_COACH_ENABLED` + `PRISM_OPENAI_API_KEY`. Whatever the model returns
  goes through `services.coach.post_filter` — 8-word copies of the source or the passage, and detector-beating
  language, are replaced by rule text. Keep the evasion lexicon *narrow*: rule text must be able to say "do not
  just change a few words". Never send more than the two excerpts. Cards are always labelled `ai_written`.
- **Report + re-check (ADR-0032):** `report` is part of the cached result; `recheck` is attached by the runner
  *after* the cache lookup and must stay out of the cache. The band is never "pass"; the `clear` reason must
  keep saying it is about the sources checked. `compare_to` obeys the GET ownership rule (404).
- **Every new field on the result must be added to the Pydantic schema** — Pydantic drops unknown keys silently
  (ADR-0031's engine fields were lost this way for one commit). A test that reads the field back through the API
  is the guard.
- **Import layering:** `worker` → `pipeline`/`services`/`utils`; never `worker` → `app` except `app.settings`/
  `app.schemas`. `app/__init__` resolves `create_app` lazily for exactly this reason; context vars live in
  `utils/context.py`. `python -c "import worker"` must work cold — it is the regression check.
- Every result's `engine` block drives the report's method footer — never hard-code thresholds in copy.
- Triage guidance must never suggest evasion; `tests/test_triage.py::test_guidance_never_suggests_evasion` enforces it.
- Frontend: vanilla JS, `esc()` everything before `innerHTML`, CSS variables only, don't rename IDs the JS reads.
- When you change product shape: add an ADR, update CHANGELOG `[Unreleased]`, log the session in `docs/PROGRESS.md`.

## Current priorities

**State as of 2026-09-07** (`main` @ `5032bc6` + the ADR-0032 pass, 287 tests + 18 Postgres-only (305 vs an embedded Postgres), lint clean, E2E 2/2, audit clean):
W1–W4b + W8 shipped · licensed PolyForm Noncommercial 1.0.0 · PAN purged from history.
Full narrative in [`docs/PROGRESS.md`](docs/PROGRESS.md) (newest entry first); decisions in ADR-0018…0032.

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
   then score passages known not to derive from it. Only then refit and refresh `eval/gates.json`. Note that
   both were measured with the **pre-ADR-0026 splitter**, which truncated every sentence containing a decimal.
3. **W5 fine-tune** — kit is ready and self-gating; needs one human-run Colab/Kaggle GPU session. "Do not ship"
   is a legitimate outcome.
4. **W7, W9 and W10 — code-complete** (ADR-0029…0032). W7/W9 are dark until configured: a Supabase project
   (secret or JWKS URL) + free-quota number + sign-in UI; an OpenAI key with ZDR + a read of real cards.
   **What remains — W11 payments + legal, W12 polish + launch — needs the owner's accounts and decisions first.**

**Owner decisions still open** (TODO 🔴, none blocking): the legal copyright holder for `NOTICE`; consent from
three past teammates for ~176 surviving boilerplate lines; confirming the old Vercel/Render demo is offline.

**Before claiming anything works, run the Verify block above.** This project's rule is that a number is only
real if it was measured — two defaults changed on 2026-09-06 purely because measurement contradicted intuition.
