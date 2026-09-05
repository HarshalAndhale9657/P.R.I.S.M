# Security Policy

## Status
PRISM is **pre-launch**. The backend is designed to be safe to expose on the public internet as an
*anonymous, unauthenticated* checker with the controls below, but it is not yet a multi-user service:
there are no accounts, nothing is persisted, and a single operator runs a single box. Treat analysis
output as advisory.

## Reporting a vulnerability
Email the maintainer listed on the GitHub repository with details and a reproduction. Please do not open
a public issue for security problems. We aim to acknowledge within a few days.

## Current controls (as of 2026-09-06 — every item below is in code and covered by a test)

| Area | Control | Where |
|---|---|---|
| **Upload size** | 20 MiB per file (413), **60 MiB aggregate per check** (413), `Content-Length` pre-check before the body is read | `app/routers/check.py`, `app/middleware.py` |
| **Queue / memory** | Bounded pending queue → **503 + Retry-After**; worst-case upload memory = `max_pending_jobs × max_request_bytes` | `worker/executor.py`, `app/settings.py` |
| **Rate limiting** | Per-IP fixed window on submissions (**429 + Retry-After**); honours `X-Forwarded-For` only when `PRISM_TRUST_PROXY=true` | `app/limits.py` |
| **Data retention** | Job results and the content-hash cache are **purged after `PRISM_JOB_TTL_SECONDS`** (default 30 min) and bounded by count; nothing is written to disk | `worker/store.py` |
| **PDF handling** | Page cap (300), extracted-text cap (2M chars), encrypted/corrupt PDFs handled without raising | `services/document_parser.py` |
| **Error leakage** | Client sees either a user-safe `PipelineError` message or a generic error; internals only in server logs; tested | `worker/runner.py`, `tests/test_check_api.py` |
| **CORS** | Explicit allow-list (`PRISM_ALLOWED_ORIGINS`), `allow_credentials=False` | `app/factory.py` |
| **Headers / TLS** | Caddy: automatic TLS, CSP, `X-Frame-Options DENY`, `nosniff`, `Referrer-Policy`; API never exposed directly | `deploy/Caddyfile`, `deploy/docker-compose.yml` |
| **Container** | Multi-stage image, non-root user, read-only root FS, CPU-only torch, models baked and `HF_HUB_OFFLINE=1` at runtime | `backend/Dockerfile` |
| **XSS** | All user/API strings pass through `esc()` before `innerHTML`; CSP forbids inline scripts | `frontend/js/check.js` |
| **Dependencies** | Exact pins in `requirements.txt`, fully-resolved `requirements.lock`; ruff blocking in CI | `backend/requirements*.txt` |
| **Secrets** | None in the repo; configuration via `PRISM_*` env / `.env` (git-ignored) | `backend/.env.example` |
| **Correlation** | `X-Request-ID` echoed; `request_id` / `job_id` on every log line | `app/middleware.py`, `app/logging_config.py` |

## Third-party data flow
When the user enables academic search, **up to 8 short excerpts (≤18 words each) of the manuscript's longest
sentences** are sent as search queries to OpenAlex and arXiv. This is disclosed on the toggle in the UI and in
the API docstring. Nothing else leaves the server; no LLM is called. Set `PRISM_CONTACT_EMAIL` in production
so those services can reach the operator (OpenAlex "polite pool"). With `PRISM_ACADEMIC_FULLTEXT=true` (default)
the server additionally **downloads up to 8 public open-access PDFs per check** from links those services return
(`services/fulltext.py`): https-only, loopback/private/link-local hosts refused before and after redirects, 15 MiB
streaming cap, `%PDF` magic required, parsed under the same page/char caps, cached 1 h. Nothing of the user's is
included in those requests.

## Known gaps (tracked for W7+ in `TODO.md`)
| Gap | Plan |
|---|---|
| **No authentication** — anyone can submit; anyone with a job id can read its result (ids are 128-bit random) | Supabase JWT + ownership on `/api/v1/check/{id}` (W7) |
| **Rate limit is per IP, in-process** | per-user quotas backed by Postgres/Redis (W7) |
| **No persistence** — a restart drops in-flight checks | Postgres `JobStore` behind the existing Protocol (W7) |
| **No dependency vulnerability scan in CI** | add `pip-audit` once the lockfile stabilises |
| **No OCR** — scanned PDFs are rejected with a clear message | later |

## Principles
- **Minimise + delete:** hold text only as long as the user could still be polling for it; never persist without consent.
- **Self-check framing:** we analyse the author's *own* document for the author — not surveillance.
- **No silent degradation:** every skipped reference, excluded reference list, or disabled model shows up in `warnings`.
