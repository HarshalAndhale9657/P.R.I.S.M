# P.R.I.S.M. — Project Brief & Knowledge Base

> Single source of truth for what PRISM is, what's built, and what's next. Keep this current.
> History: [`CHANGELOG.md`](CHANGELOG.md) / [`docs/PROGRESS.md`](docs/PROGRESS.md) · decisions: [`docs/DECISIONS.md`](docs/DECISIONS.md) ·
> plan: [`docs/LAUNCH_PLAN.md`](docs/LAUNCH_PLAN.md) (authoritative) · near-term: [`TODO.md`](TODO.md).
>
> **Last updated:** 2026-09-06 · **Status:** Originality Checker functional, honestly benchmarked, production-shaped
> (ADR-0018/0019/0020: legacy engine removed; `app/` + `worker/` + pipeline-owned parsing; bounded, ephemeral,
> observable; public-dataset regression gates in CI). **Not yet a public service** — accounts, persistence and
> payments are W7–W12. Next: W4b retrieval depth → W6 first deploy on the real box.

---

## 1. One-liner

**PRISM helps a writer find plagiarism in a paper — *what* is copied, *where* it is, and *which source* it came
from** — as a non-accusatory self-check, backed by false-positive rates measured on public data.

Originally (April 2026) a hackathon *stylometric authorship* tool ("does this read like one author?"); pivoted
to source-attribution plagiarism in August 2026 because that is the real job-to-be-done and the old engine's
detection was near-noise (§6). The old engine was deleted in September 2026 (ADR-0018).

---

## 2. Product direction (finalized)

| | Old (deleted) | Now (shipped) | Next (W7–W12) |
|---|---|---|---|
| Core question | "How many authors?" | "Is any passage copied, **where**, and **from what source**?" | "…and what is the **honest fix**?" |
| Method | spaCy stylometry → HDBSCAN | **Source-matching** every passage against a corpus | + deterministic triage + LLM coaching |
| Output | Integrity verdict, 0–10 score | **Originality report**: highlighted matches → sources, %, confidence band | + submission-risk report, re-check |

**Finalized decisions (owner Q&A + ADRs):**
- **Product (ADR-0014):** a freemium **publication-readiness / integrity coach** for authors submitting to
  IEEE / arXiv / journals (ESL and early-career especially). Detect → **triage each flag by remediation type** →
  **coach the honest fix** (quote+cite, add reference, disclose self-reuse/AI use, or author-driven rewrite with
  the source shown) → submission-risk report. Mirrors/reduces the publisher's gate; **never** promises a pass.
- **⛔ Hard ethical boundary:** **no detection-evasion** — no auto-rewrite-to-lower-similarity, no "AI humanizer".
- **Core ML (ADR-0015/0016):** pretrained-first, fine-tune selectively (only the paraphrase cross-encoder, free GPU,
  ship only if it beats pretrained); **public datasets only** (PAWS/MRPC/STS-B/QQP); **no PAN**; AI-text detector deferred.
- **Honesty (ADR-0017/0020):** explicit `confident | review` band; the synthetic 32-case set is a smoke test;
  quality is gated in CI on public data at the confident cutoff.
- **Detect:** verbatim + paraphrase + translated ✅ · AI-generated risk ⏳ deferred.
- **Corpora:** user uploads ✅ + **OpenAlex + arXiv (+ Semantic Scholar with a key)** ✅ with **open-access full text** fetched where available (ADR-0021) ✅ · web layer later (paid).

---

## 3. Architecture (implemented — ADR-0019)

```
frontend/  ──►  POST /api/v1/check (202 + job_id)  ──►  GET /api/v1/check/{id}
                       │
                app/     FastAPI: settings (PRISM_*) · Pydantic schemas · request-id · body-size guard
                         · per-IP rate limit (429) · /health · /health/ready · create_app()
                       │
                worker/  BoundedExecutor (503 + Retry-After) · InMemoryJobStore + TTLCache (purged by time)
                         · CheckRunner (lifecycle, content-hash cache, `engine` block)
                       │
        pipeline/  parse ─► retrieve ─► match ─► rerank (opt-in) ─► localize ─► [triage ─► coach ─► report]
                     │          │          │          │
   services/document_parser  academic_corpus  plagiarism_matcher  modelhub/ (registry)   eval/ (harness + gates)
```

1. **Parse** (`services/document_parser.py`) — PDF (PyMuPDF) or text → offset-preserving paragraphs with pages.
   Keeps every block with real words; strips repeated running headers/footers and page numbers; **excludes and
   reports** the reference list; re-joins hyphenated line breaks; page (300) and char (2M) caps; encrypted/corrupt
   PDFs handled. References that fail to parse are skipped with a warning, never fatal.
2. **Retrieve** (`services/academic_corpus.py` + `services/fulltext.py`) — opt-in OpenAlex + arXiv (+ Semantic
   Scholar with `PRISM_S2_API_KEY`), concurrent, deduped, pooled session with retries; sends ≤8 short excerpts as
   queries (disclosed in the UI). Up to 8 of the most relevant candidates with an OA PDF are **downloaded and
   matched in full text** (https-only, private hosts refused, 15 MiB cap, `%PDF` sniffed, cached); the rest stay
   `kind="abstract"` and are labelled so. No sources at all → user-safe error.
3. **Match** (`services/plagiarism_matcher.py`, pure) — **verbatim** k-gram anchoring + greedy extension (exact
   spans); **paraphrase** sentence-embedding cosine with a reporting floor **0.66** and confidence cutoff **0.78**;
   **translated** = paraphrase path re-labelled on language mismatch. Large reference sets are budgeted by **TF-IDF
   relevance across all sources**, never by upload order. Degrades to verbatim-only if the model is unavailable.
4. **Rerank** (opt-in, `PRISM_RERANK`) — pretrained cross-encoder re-decides the confidence band of borderline
   matches (cosine 0.60–0.92, ≤200 pairs, strongest first). Displayed similarity stays the bi-encoder's.
5. **Localize** — map spans to paragraph index + page.
6. **Assemble** — `overall` (similarity/verbatim/paraphrase/translated/**confident/review** %), `per_source`,
   `matches`, `warnings`, per-stage `timings_ms`, and an **`engine`** block (version, model, both thresholds,
   rerank, coverage statement) that drives the report's method footer.

**Frontend** (`index.html` + `js/check.js`, no build): dual upload, academic toggle (with data-flow disclosure),
banded score, breakdown bars, highlighted document (review band rendered dashed/muted), ranked match list,
side-by-side comparison, downloadable/printable report whose method footer comes from `engine`. API base from
`<meta name="prism-api-base">` → same origin → `localhost:8000`.

---

## 4. Features (shipped)

- Passage-level **verbatim / paraphrase / translated** detection with exact spans and language pair.
- **Source attribution** against uploads + OpenAlex/arXiv/Semantic Scholar — **full text where an OA PDF exists**, abstract otherwise, each labelled (origin badges + links).
- **Confidence band**: `confident` vs `review` ("Needs review" — never shown as confirmed copying).
- In-context highlighting, side-by-side comparison, downloadable evidence report with honest method + coverage footer.
- **Bounded service**: per-file 20 MiB, per-check 60 MiB, pending-queue cap → 503, per-IP rate limit → 429,
  30-minute TTL on results (nothing persisted), request ids, JSON logs, `/health/ready`.
- **Measured** on public data with regression gates in CI (§6); synthetic set kept as a smoke tripwire.
- Production packaging: multi-stage non-root Docker image (CPU torch, model baked), Compose + Caddy (TLS, CSP), runbook.

Deferred: AI-generated-text signal (honesty-gated when built); OCR; batch/history; accounts/payments (W7+).

---

## 5. Guardrails & principles (non-negotiable)

- **Self-check, non-accusatory** — no verdicts; an author's originality report.
- **Never present a `review`-band or topical hit as a confirmed "source match".**
- **Bias awareness** — same-topic ESL/technical writing is exactly where similarity scores are least trustworthy;
  that is why the review band exists and why FPR is gated on same-topic negatives (MRPC/QQP).
- **No claim without a measurement on public data** — never reintroduce "100% accuracy / zero FP / prosecutable".
- **Data minimisation** — manuscripts live in memory for the TTL and are gone; only short excerpts leave the server,
  only when the user enables academic search, and the UI says so.
- **No detection-evasion features. Ever.**

---

## 6. What the numbers actually are

**Why we pivoted** (`research/HONEST_AUDIT.md`, `research/legacy_prism_diagnostic.md`): authorship boundary
**F1 ≈ 0.40**; the 27 stylometric features added ~+0.02 over a topic-tracking embedding; the old README
"benchmark" was N=2 and the "Idea Triplet" feature was dead code.

**The new matcher, measured on public sentence-pair data** (bi-encoder baseline, validation splits, at the
**confident cutoff 0.78** — these are the CI gates in `backend/eval/gates.json`):

| dataset | n | recall | FPR | gate |
|---|---|---|---|---|
| STS-B | 1,221 | 0.901 | 0.097 | R ≥ 0.86, FPR ≤ 0.12 |
| QQP | 3,000 | 0.856 | 0.257 | R ≥ 0.81, FPR ≤ 0.28 |
| MRPC | 408 | 0.785 | 0.442 | R ≥ 0.74, FPR ≤ 0.47 |
| PAWS | 2,000 | 1.000 | 0.997 | reported, not gated (unsolvable for bi-encoders; equivalence ≠ derivation) |

The cross-encoder rerank (opt-in) improves MRPC (FPR 0.643 → 0.403 at the 0.66 floor). The self-authored
32-case set reports P=1.00/FPR=0.00 — that is an artifact of easy negatives and **must never be quoted as accuracy**
(ADR-0017). Full history incl. negative results: `docs/PROGRESS.md`.

---

## 7. Codebase state

| Path | Role |
|---|---|
| `backend/main.py` | two-line shim → `app.create_app()` |
| `backend/app/` | settings · schemas · middleware · limits · routers (`check`, `health`) · factory |
| `backend/worker/` | executor (bounded) · store (TTL job store, cache; `JobStore` Protocol = W7 seam) · runner |
| `backend/pipeline/` | `base` (CheckContext, RawInput, Document, PipelineError) · `stages` · `orchestrator` (timings, `build_check_stages`) |
| `backend/services/` | `document_parser` · `plagiarism_matcher` · `academic_corpus` · `fulltext` · `local_embeddings` |
| `backend/modelhub/` | model registry (`get_embedder`, `get_cross_encoder`) |
| `backend/eval/` | public-dataset harness; `gates.json`; `run_pairs --gate`; `data/sample/` smoke set (**no PAN**) |
| `backend/training/` | W5 cross-encoder fine-tune kit (self-gating; needs a GPU session) |
| `backend/scripts/eval_matcher.py` | synthetic 32-case **smoke** |
| `backend/tests/` | 100+ offline tests (API contract, worker, parser, limits, corpus, matcher, pipeline, eval, W5 gate) |
| `frontend/` | `index.html` · `js/check.js` · `css/styles.css` · `_serve.py` |
| `e2e/` | Playwright specs + fixtures (`node run.mjs`) |
| `deploy/` | `docker-compose.yml` · `Caddyfile` · `prism.env.example` · runbook |
| `research/` | historical record of the pre-pivot engine (`datasets/pan/` untracked) |

**Stack:** Python 3.12 · FastAPI · pydantic-settings · sentence-transformers (torch CPU) · scikit-learn · PyMuPDF ·
requests/arxiv · langdetect · vanilla JS · Docker + Caddy · GitHub Actions (ruff, pytest+coverage, Docker
build+readiness, Playwright E2E, benchmark gate).

**API:** `POST /api/v1/check` (202) · `GET /api/v1/check/{job_id}` · `GET /health` · `GET /health/ready` · `GET /docs` (non-prod).

---

## 8. How to run / test
See [`README.md`](README.md) (run), [`CONTRIBUTING.md`](CONTRIBUTING.md) (verify), [`deploy/README.md`](deploy/README.md) (deploy).

## 9. Glossary
**Verbatim** — copied text (n-gram overlap). **Paraphrase** — reworded (embedding cosine). **Translated** — copied
across languages. **Source attribution** — linking a passage to the document it came from. **Confidence band** —
`confident` (at/above 0.78) vs `review` (0.66–0.78, inconclusive). **Coverage** — what was actually compared against.
**Self-check** — the author checks their own draft.
