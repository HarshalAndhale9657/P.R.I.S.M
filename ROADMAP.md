# Roadmap

Vision: **the honest originality checker** — show a writer exactly what's copied, where, and from which source,
without ever falsely accusing them — growing into an honest **publication-readiness coach** (ADR-0014).
Spec: [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md) · authoritative plan: [`docs/LAUNCH_PLAN.md`](docs/LAUNCH_PLAN.md) · tasks: [`TODO.md`](TODO.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` todo · _(S/M/L/XL)_ effort.

---

## ✅ Shipped — the Originality Checker (Aug 2026)
- [x] **Matcher** — verbatim (k-gram → exact spans) + paraphrase (sentence-embedding cosine) + translated (language pair).
- [x] **Async API** — `POST /api/v1/check` → 202 + job id; poll for result; content-hash cache.
- [x] **Checker UI** — dual upload, banded score, highlighted document, match list, side-by-side comparison, origin badges.
- [x] **Downloadable evidence report** with method + coverage footer.
- [x] **Confidence band** (ADR-0017) — `confident` vs `review`; UI and report render it as inconclusive, never confirmed.

## ✅ Shipped — the honest core (core-ML W1–W4, Aug 30–31 2026)
- [x] **W1** pluggable pipeline + `eval/` harness + `modelhub/`.
- [x] **W2** real baseline on PAWS/MRPC — exposed that the self-authored set was drastically over-optimistic.
- [x] **W3** stronger bi-encoder (mpnet) — **negative result**, not shipped.
- [x] **W4a** cross-encoder rerank stage (opt-in), latency measured; STS-B/QQP added; separation-gap analysis.

## ✅ Shipped — industry-grade pass (Sep 6 2026; ADR-0018/0019/0020)
- [x] Legacy authorship engine **deleted**; repo hygiene (PAN corpus untracked).
- [x] `app/` + `worker/` + `ParseStage`; Pydantic API contract at `/api/v1`; bounded queue (503), TTL store, aggregate
      size cap, per-IP rate limit (429); request ids, JSON logs, per-stage timings, `/health/ready`.
- [x] Checker-specific PDF parser (no 80-char floor; headers/footers/reference list handled; page + char caps).
- [x] Relevance-based source-sentence budgeting.
- [x] Docker (multi-stage, non-root, CPU torch, baked model) + Compose + Caddy + runbook; lockfile.
- [x] CI: ruff blocking · coverage floor · Docker build + readiness smoke · Playwright E2E · **public-dataset benchmark gate**.
- [x] False "offline" UI claims removed; README/SECURITY/BRIEF/CLAUDE synced with reality.

## ✅ Shipped — depth, triage and speed (Sep 6 2026; ADR-0021/0022/0023)
- [x] **W4b · Retrieval depth** (ADR-0021) — Semantic Scholar (keyed) + **open-access full text** fetched safely from the
      providers' OA links, so academic matches can be verbatim; every source labelled *full text* / *abstract only*.
- [x] **W8 · Flag triage + coach card** (ADR-0022) — brought forward because it is the product's core (LAUNCH_PLAN §13):
      8 deterministic remediation types, prioritised "What to fix" panel, per-flag coach card, report section.
- [x] **Embedding cache** (ADR-0023) — re-check after edits **6.0× faster** (39.3 s → 6.6 s), measured.

## 🟠 NOW — go live, then finish the core
- [ ] **W6 · First deploy** — run `deploy/README.md` on the real VPS; measure `timings_ms` there (rerank + full text);
      decide the rerank default and the embedding-cost lever; UptimeRobot on `/health/ready`; Sentry. _(S)_
- [~] **W5 · Selective cross-encoder fine-tune** — kit ready; needs one human-run GPU session; ship only if it beats pretrained on the gates. _(M)_
- [ ] Re-derive the confident cutoff once rerank is default-on (max-over-sources bias); refresh `gates.json` baselines. _(S)_
- [ ] Cold first-check cost: ~77–93 s per 6 000 sentences on CPU — tune `PRISM_MAX_SOURCE_SENTENCES` and the batch
      size on the real box, using `timings_ms` and the `/health` cache hit rate. _(M)_

## 🟢 NEXT — the product (W7, W9–W12)
- [ ] **W7** Accounts (Supabase JWT) + `PostgresJobStore` + ownership on job reads + per-user quotas + ephemeral storage policy. _(L)_
- [ ] **W9** **CoachStage** — gpt-4o-mini honest-fix coaching, cached, matcher post-filter, source always visible, no auto-rewrite. _(L)_
- [ ] **W10** **ReportStage** — submission-risk report + re-check. _(M)_
- [ ] **W11** Razorpay + Privacy/ToS/AUP + CI honesty gate on copy. _(M)_
- [ ] **W12** Launch (~15–30 paying users = validation). 

## 🔵 LATER
- [ ] AI-generated-text signal — deferred (ADR-0016); honesty-gated on RAID/HC3/M4 + a real ESL set; else disclosure coach only.
- [ ] OCR for scanned PDFs; PAWS-X for translated evaluation; batch + history.
- [ ] (If institutional) SOC 2, LTI 1.3, SSO — only after validity + calibration are proven.

---
_All finalized decisions are ADRs in [`docs/DECISIONS.md`](docs/DECISIONS.md); measurements in [`docs/PROGRESS.md`](docs/PROGRESS.md)._
