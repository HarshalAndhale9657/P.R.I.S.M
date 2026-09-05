# Contributing to P.R.I.S.M.

Read [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) first — it's the source of truth for what we're building and why.
Then [`docs/DECISIONS.md`](docs/DECISIONS.md) for the reasoning and [`TODO.md`](TODO.md) for what's next.

## Prerequisites
- Python **3.12**
- Node 20 (only for the Playwright E2E suite)
- Docker (only to build/run the production image)
- No API keys of any kind — the checker runs fully local.

## Setup
```powershell
cd backend
py -3.12 -m venv venv
venv\Scripts\python -m pip install -U pip
venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env      # optional; every setting has a sane default
```

## Run (dev)
```powershell
cd backend  && venv\Scripts\uvicorn main:app --host 127.0.0.1 --port 8000   # API + /docs
cd frontend && python _serve.py 3000                                        # http://127.0.0.1:3000
```

## Verify
```powershell
cd backend
venv\Scripts\python -m ruff check .                     # lint (blocking in CI)
venv\Scripts\python -m pytest                           # offline unit + API tests; coverage floor 80%
venv\Scripts\python scripts\eval_matcher.py             # synthetic smoke — NOT a quality claim
venv\Scripts\python -m eval.fetch_datasets stsb mrpc    # once; then:
venv\Scripts\python -m eval.run_pairs stsb mrpc --gate  # the real benchmark + regression gates
cd ..\e2e && npm install && node run.mjs                # browser E2E (needs both servers up)
```
> New behaviour ships with a test. Keep ruff, pytest and the benchmark gate green — CI enforces all three,
> builds the Docker image, and runs the browser E2E on every push.

## Conventions
- **Branches:** `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, `chore/<slug>`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`; `!` for breaking API changes.
- **Python:** type hints on public functions; pure services (bytes/text in, data out); no network in the request path
  (only the worker talks to the internet); configuration only via `app/settings.py`; ruff config in `pyproject.toml`.
- **API:** every response has a Pydantic model in `app/schemas.py`; breaking changes bump `/api/vN`.
- **Frontend:** vanilla JS, no build step. `esc()` every string before `innerHTML`. CSS variables only. Don't rename
  element IDs the JS depends on. Anything about *method* (thresholds, models, coverage) comes from the result's
  `engine` block, never from hard-coded copy.
- **Dependencies:** pin exactly in `requirements.txt`; regenerate `requirements.lock` (command in its header).
- **Data:** public datasets only, fetched at run time — never commit a corpus. **No PAN** (ADR-0016).
- **When you change the product's shape:** add an ADR to `docs/DECISIONS.md`, update `CHANGELOG.md`
  `[Unreleased]`, and log the session in `docs/PROGRESS.md`.

## Product guardrails (non-negotiable — ADR-0004, ADR-0014, ADR-0017)
- A **self-check** tool: non-accusatory, calibrated, willing to say **"needs review"**.
- Never present a `review`-band or topical hit as a confirmed copy.
- No marketing claim we can't back with a number measured on **public** data.
- **No detection-evasion features.** Ever.

## PR checklist
- [ ] Linked to a TODO/ROADMAP item or an issue.
- [ ] Tests added/updated; `ruff`, `pytest`, and (if the matcher changed) `eval.run_pairs --gate` pass.
- [ ] `CHANGELOG.md` `[Unreleased]` updated.
- [ ] ADR added/updated if behaviour or direction changed.
- [ ] No secrets, no datasets, no `.env` committed.
