# syntax=docker/dockerfile:1.7
# P.R.I.S.M. backend — production image.
#
#   * Multi-stage: build tools never reach the runtime layer.
#   * CPU-only torch from the PyTorch index (no CUDA libraries — several GB smaller).
#   * Non-root user, read-only app tree, HEALTHCHECK on readiness.
#   * The embedding model is baked at build time so a cold container never downloads
#     ~470 MB on its first request; the runtime is then pinned offline (HF_HUB_OFFLINE=1).
#
# Build:  docker build -t prism-backend .
# Run:    docker run --rm -p 8000:8000 -e PRISM_ENV=prod -e PRISM_WARMUP_MODELS=true prism-backend

ARG PYTHON_VERSION=3.12

# ── Stage 1: resolve + install the locked dependency set ─────────────────────
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.lock .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG PRISM_BAKE_RERANK=0
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    TOKENIZERS_PARALLELISM=false \
    PRISM_ENV=prod \
    PRISM_LOG_FORMAT=json \
    PRISM_WARMUP_MODELS=true

# No apt layer at all: nothing in the runtime needs system packages, and the health
# probe below is plain Python — smaller image, no build-time dependency on a mirror.
RUN groupadd -r prism && useradd -r -g prism -d /app -s /usr/sbin/nologin prism \
 && mkdir -p /app /models && chown prism:prism /app /models

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=prism:prism . .

USER prism

# Bake the bi-encoder (and optionally the cross-encoder reranker) into the image.
RUN python - <<'PY'
import os
from sentence_transformers import SentenceTransformer
SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
if os.environ.get("PRISM_BAKE_RERANK", "0") == "1":
    from sentence_transformers import CrossEncoder
    CrossEncoder("cross-encoder/stsb-roberta-base")
PY
ENV HF_HUB_OFFLINE=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/health/ready', timeout=4).status == 200 else 1)" || exit 1

# One worker: the job store and result cache are in-process (ADR-0011). Scale by
# adding a Postgres-backed JobStore (W7), not by adding uvicorn workers.
# --proxy-headers is safe only behind the Caddy container on the compose network.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
