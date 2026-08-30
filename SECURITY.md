# Security Policy

## Status
PRISM is **pre-production / research-grade**. Do **not** deploy the current backend on the public
internet with real user data — it has known gaps (below). Treat all analysis output as advisory.

## Reporting a vulnerability
Email the maintainers (see `README.md` contributors) with details and a reproduction. Please don't open
a public issue for security problems. We aim to acknowledge within a few days.

## Known gaps (must fix before handling real/multi-user data)
Tracked in [`TODO.md`](TODO.md) (🔴) and [`ROADMAP.md`](ROADMAP.md) (NOW).

| Area | Current state | Required |
|---|---|---|
| **Auth** | None — every `/api/*` route is open | API key/OIDC on all routes |
| **CORS** | `allow_origins=["*"]` **with** `allow_credentials=True` (invalid/insecure) | Explicit origin allow-list |
| **Upload limits** | No size/page cap; whole body read into memory | Reject > ~25 MB pre-read; cap pages; PDF-bomb guard |
| **Rate limiting** | None | Per-key/IP limits; the pipeline is expensive |
| **Request timeout** | Sync request blocks 30–120 s, calls OpenAI/arXiv inline | Move to a worker/job model; per-provider timeouts |
| **Error leakage** | `str(e)` returned to clients | Generic errors + server-side logs |
| **Data handling** | Student text sent to OpenAI when a key is set; no retention/encryption policy | Offline-by-default; explicit consent; retention + hard delete |
| **Secrets** | `.env` (gitignored) | Keep out of VCS; use a secret manager in prod |

## Data & privacy principles
- **Offline-first:** the deterministic pipeline must run without sending text to any third party.
- **Minimize + delete:** don't persist uploads longer than needed; support hard delete.
- **Self-check framing:** we analyze the author's *own* document for the author — not surveillance.
- If we ever handle student data at an institution, we must meet the FERPA/GDPR bar first (see PROJECT_BRIEF §6).

## Dependencies
Pin versions in `requirements.txt`; review new deps for maintenance/security. Prefer local/offline
models over sending content to external APIs.
