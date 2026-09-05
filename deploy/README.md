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

## 5. What is deliberately not here yet
- No database and no backups: nothing is persisted (manuscripts live in memory for `PRISM_JOB_TTL_SECONDS`
  and are then gone). This changes at W7 (Postgres job store + accounts).
- One API replica: the job store is in-process. Do not add uvicorn workers or replicas before W7.
- Secrets live in `prism.env` on the box. Fine for one operator; move to a secret manager when there are two.
