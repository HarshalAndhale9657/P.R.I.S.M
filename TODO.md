# TODO — near-term backlog

Actionable tasks. Full plan: [`docs/LAUNCH_PLAN.md`](docs/LAUNCH_PLAN.md) (authoritative) · rationale: [`docs/DECISIONS.md`](docs/DECISIONS.md).
Check items off with a date. Newest priorities on top.

## 🔴 Owner decisions (blocking nothing, but real)
- [ ] **Licence follow-ups (LICENSE added 2026-09-06: PolyForm Noncommercial 1.0.0).** (a) Replace "the P.R.I.S.M.
      authors" in `NOTICE` with the legal name/entity that will hold the copyright. (b) ~176 surviving boilerplate lines
      (CSS/HTML/README) were written by three past teammates — send each: *"PRISM is now licensed under PolyForm
      Noncommercial 1.0.0; are you OK with your past contributions being licensed under it? A yes here is enough."*
      Record the replies (issue or PROGRESS). If anyone declines, I rewrite those lines.
- [ ] **Confirm the old Vercel/Render demo is offline** (its README link was removed 2026-09-06). If it still
      serves the pre-refactor backend, take it down — it has none of the new controls.

## 🟠 Now — finish the core (ADR-0016; pretrained-first, plagiarism-first, public data, NO PAN)
- [~] **W5 · Selective cross-encoder fine-tune** — kit ready (`backend/training/`, 8 gate tests, self-enforcing
      ship/no-ship). ⏳ **Needs one free Colab/Kaggle T4 session run by a human.** "Do not ship" is a valid outcome. _(M)_
- [ ] **W6 · First deploy on the real box** — `deploy/README.md` runbook; then **measure** `timings_ms` on a real
      20-page PDF with `PRISM_RERANK=true` and academic full text on, and decide the rerank default; set `PRISM_CONTACT_EMAIL`
      (+ optional `PRISM_S2_API_KEY`); UptimeRobot on
      `/health/ready`; Sentry DSN. _(S)_
- [ ] **W6 follow-up · embedding latency** — benchmarked on this CPU: **6 000 sentences = 77–93 s** (batch 64 fastest;
      128/256 worse). That, not downloading, is the full-text cost. On the VPS decide from `timings_ms`: an **embedding
      cache keyed by source URL** (a popular OA paper embedded once) and/or a lower `PRISM_MAX_SOURCE_SENTENCES`;
      re-check the batch size there before pinning one. _(M)_
- [ ] **Re-derive the confident cutoff once rerank is default-on**, accounting for the max-over-sources upward bias
      (pairwise 0.78 is a lower bound — ADR-0017). Update `eval/gates.json` baselines from the new measurement. _(S)_
- [ ] `pip-audit` step in CI once the lockfile has settled. _(S)_

## 🟢 Next — the product (W7–W12, LAUNCH_PLAN §9)
- [ ] **W7 · Accounts + persistence** — Supabase JWT verify as a FastAPI dependency; `PostgresJobStore` implementing
      `worker.store.JobStore`; ownership check on `GET /api/v1/check/{id}`; per-user quota replaces the per-IP limiter. _(L)_
- [ ] **W9 · CoachStage** — replace the *static* per-type `fix` string with gpt-4o-mini prose grounded in the triage
      type + the shown source: JSON, ≤3 calls/check, cached, per-account $ ceiling; **matcher post-filter** so coaching
      can never launder copied text; source always visible; no auto-rewrite (ADR-0014). Rules stay the backbone. _(L)_
- [ ] **W10 · ReportStage** — submission-risk report + re-check. _(M)_
- [ ] **W11 · Payments + legal** — Razorpay; Privacy/ToS/AUP; CI honesty gate on copy. _(M)_
- [ ] **W12 · Launch.**

## 🔵 Later
- [ ] AI-generated-text signal — deferred (ADR-0016); when built, honesty-gated on RAID/HC3/M4 + a real ESL set.
- [ ] OCR for scanned PDFs (currently rejected with a clear message).
- [ ] Batch upload + history; PAWS-X for translated evaluation.
- [ ] (If institutional) SOC 2, LTI 1.3, SSO.

## ✅ Done
- [x] 2026-09-06 — **W8 flag triage + coach card** (ADR-0022): 8 deterministic remediation types with priorities and
      honest-fix guidance; "What to fix" panel, per-match badges, coach card, report section. Tests 130 → 151.
- [x] 2026-09-06 — **W4b retrieval depth** (ADR-0021): OA full-text fetch (safe, capped, cached) for the most relevant
      candidates; Semantic Scholar provider (keyed); `kind` = fulltext/abstract surfaced in UI + report coverage. Tests 105 → 129.
- [x] 2026-09-06 — **PAN corpus purged from git history** (owner's decision; `git filter-repo`; pack 33.65 → 2.77 MiB; all
      SHAs changed; pre-rewrite backup bundle kept outside the repo; PAN data also deleted from disk).
- [x] 2026-09-06 — **Industry-grade pass** (ADR-0018/0019/0020): legacy engine deleted; `app/` + `worker/` +
      `ParseStage`; Pydantic API contract at `/api/v1`; bounded queue (503) + TTL store + aggregate size cap + per-IP
      rate limit (429); checker-specific PDF parser (no 80-char floor, headers/footers/reference list handled, page +
      char caps); relevance-based source budgeting; request ids + JSON logs + per-stage timings + `/health/ready`;
      multi-stage non-root Docker image with baked model; Compose + Caddy + runbook; lockfile; ruff blocking;
      coverage floor; Docker + E2E + **public-dataset benchmark gate in CI**; false "offline" UI claims removed;
      README/SECURITY/BRIEF/CLAUDE synced; PAN corpus + `.gemini/` untracked. Tests 57 → 100+.
- [x] 2026-08-31 — W4 cross-encoder rerank stage (opt-in) + latency measured; W5 training kit; confidence band in UI + report (ADR-0017).
- [x] 2026-08-30 — W1 pluggable pipeline + eval harness + modelhub; W2 real baseline on PAWS/MRPC; W3 mpnet (no lift — not shipped); W4b STS-B/QQP added, separation-gap analysis.
- [x] 2026-08-21..26 — Phases 1–3 (verbatim, OpenAlex/arXiv, translated), downloadable report, async job model, pytest suite, security baseline, README de-hype.
