# Contributing to P.R.I.S.M.

Thanks for working on PRISM. Read [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) first — it's the source of truth
for what we're building and why. Then check [`ROADMAP.md`](ROADMAP.md) / [`TODO.md`](TODO.md) for what's next.

## Prerequisites
- Python **3.12+**
- Node 18+ (only for the Playwright E2E harness)
- No OpenAI key required — the backend runs fully offline in degraded mode.

## Setup
```powershell
cd backend
py -3.12 -m venv venv
venv\Scripts\python -m pip install -U pip
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m spacy download en_core_web_sm
venv\Scripts\python -m nltk.downloader punkt punkt_tab
copy .env.example .env   # optional: add OPENAI_API_KEY to enable GPT + OpenAI embeddings
```

## Run (dev)
```powershell
# backend
cd backend && venv\Scripts\uvicorn main:app --host 127.0.0.1 --port 8000
# frontend (no-cache server — avoids stale HTML/CSS)
cd frontend && python _serve.py 3000     # http://localhost:3000
```

## Test
```powershell
cd backend
venv\Scripts\pip install -r requirements-dev.txt   # once (adds pytest)
venv\Scripts\python -m pytest                       # unit + /api/check integration tests (offline)
venv\Scripts\python scripts\eval_matcher.py         # matcher precision/recall/FPR gate
venv\Scripts\python _smoketest_check.py             # matcher offline smoke
# browser end-to-end (needs both servers running)
cd ..\..\_e2e && node check_e2e.mjs                 # + check_academic_e2e.mjs, check_translated_e2e.mjs
```
> New backend behaviour must ship with a test. Keep `pytest` and the eval gate green (CI enforces both).
> `pytest.ini` scopes collection to `backend/tests/` — don't rely on the legacy `_smoketest*.py` / `test_pipeline.py`.

## Conventions
- **Branches:** `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, `chore/<slug>`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- **Python:** type hints on public functions; keep services single-responsibility; don't add network/LLM
  calls to the request path (use the worker model once it exists). Match existing style.
- **Frontend:** vanilla JS, no build step. Don't hardcode colors — use the CSS variables in `styles.css`.
  Don't rename element IDs the JS depends on without updating both sides.
- **When you change the product's shape:** add an ADR to [`docs/DECISIONS.md`](docs/DECISIONS.md), update
  [`CHANGELOG.md`](CHANGELOG.md) `[Unreleased]`, and log the session in [`docs/PROGRESS.md`](docs/PROGRESS.md).

## Product guardrails (non-negotiable — see ADR-0004)
- This is a **self-check** tool: **non-accusatory**, calibrated, and willing to say **"inconclusive"**.
- Never present a low-similarity/topical hit as a confirmed "source match".
- No marketing claim we can't back with a measured number.

## PR checklist
- [ ] Linked to a TODO/ROADMAP item or an issue.
- [ ] Tests added/updated and passing.
- [ ] CHANGELOG `[Unreleased]` updated.
- [ ] Docs/ADR updated if behavior or direction changed.
- [ ] No secrets committed; `.env` stays untracked.
