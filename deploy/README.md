# Deploying P.R.I.S.M. (single VPS runbook)

Target: one Linux box (LAUNCH_PLAN §4 — Hetzner CX32-class, 4 vCPU / 8 GB), Docker + Compose v2,
a DNS `A` record for your domain pointing at it. Total time first run: ~15 minutes (mostly the image build).

## 1. First deploy
```bash
# on the server
git clone https://github.com/HarshalAndhale9657/P.R.I.S.M.git && cd P.R.I.S.M/deploy
cp prism.env.example prism.env && $EDITOR prism.env       # origins, contact email, Sentry DSN
export PRISM_DOMAIN=check.example.org
docker compose up -d --build                              # builds the API image, starts Caddy
docker compose logs -f api                                # wait for "embedding model warm"
curl -fsS https://$PRISM_DOMAIN/health/ready | jq .        # status: ok, model_loaded: true
```
Open `https://$PRISM_DOMAIN/` and run a check with a real 20-page PDF. Record the wall time from
`timings_ms` in the result — that number decides whether `PRISM_RERANK=true` is affordable here.

## 2. Upgrade
```bash
git pull
docker compose build api                                  # new image, old one keeps serving
docker compose up -d api                                  # Caddy waits for the new container's readiness
curl -fsS https://$PRISM_DOMAIN/health | jq .version
```
In-flight checks on the old container are lost (job state is in-process until W7). Deploy at quiet hours;
the frontend tells users whose job vanished to simply re-run it.

## 3. Rollback
Images are tagged by `PRISM_TAG` (default `local`). To keep a rollback target, build with a tag:
```bash
PRISM_TAG=$(git rev-parse --short HEAD) docker compose build api
PRISM_TAG=$(git rev-parse --short HEAD) docker compose up -d api
# roll back:
PRISM_TAG=<previous-sha> docker compose up -d api
```

## 4. Monitoring
- **Uptime:** point UptimeRobot (free) at `https://$PRISM_DOMAIN/health/ready` — 503 = model not loaded.
- **Errors:** set `PRISM_SENTRY_DSN` in `prism.env`.
- **Logs:** `docker compose logs api` is JSON, one object per line, each with `request_id` and `job_id`.
  A user's `X-Request-ID` (visible in browser dev tools) greps straight to their request.
- **Embedding cache:** `GET /health` → `embedding_cache.hit_rate`. A low rate with high latency means the cache is
  too small for the traffic (raise `PRISM_EMBEDDING_CACHE_ENTRIES`, ~1.5 KB/entry) or sources rarely repeat.
- **Capacity:** `GET /health` → `queue.pending` near `capacity` means checks are being refused with 503;
  raise `PRISM_MAX_PENDING_JOBS` only if RAM allows (`pending × PRISM_MAX_REQUEST_BYTES`).

## 5. Optional pieces, and what is deliberately not here
- **Database (optional, ADR-0029).** With `PRISM_DATABASE_URL` unset, nothing is persisted: a manuscript lives in
  memory for `PRISM_JOB_TTL_SECONDS` and is then gone, and you must run **one** API replica. Set it to a Postgres
  DSN (Hetzner's managed Postgres, or a `postgres:16` container on this box) and job state survives restarts and
  any replica can serve `GET /api/v1/check/{id}`. Execution still happens on the replica that accepted the job,
  so replicas are safe for reads, not a queue. Rows still expire on the same TTL — durability buys restarts and
  replicas, not retention. `GET /health` → `store` says which is in use.
- **Accounts (optional, ADR-0030).** Unset = anonymous, as before. Set `PRISM_AUTH_JWT_SECRET` *or*
  `PRISM_AUTH_JWKS_URL` from the Supabase project and tokens are verified; `PRISM_AUTH_REQUIRED=true` makes them
  mandatory; `PRISM_QUOTA_CHECKS` gives signed-in users a per-user budget (402 over it) instead of the per-IP
  limiter. `GET /health` → `auth` is `off | optional | required`.
- **Coaching (optional, ADR-0031).** Dark until `PRISM_COACH_ENABLED=true` and `PRISM_OPENAI_API_KEY` are set.
  Use an account with Zero Data Retention; only the flagged passage and the source excerpt are sent. Watch
  `coach_summary.estimated_cost_usd` in results and `PRISM_COACH_MAX_CALLS_PER_DAY`.
- Backups: none. The only durable data is the job table (TTL-expired) and the usage ledger (owner id +
  timestamp). If you run Postgres, snapshot it the way you snapshot the box.
- Secrets live in `prism.env` on the box. Fine for one operator; move to a secret manager when there are two.
