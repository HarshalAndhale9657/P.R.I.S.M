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
- [ ] **W6 follow-up · first-check latency** — the embedding cache (ADR-0023) made *re-checks* 6× faster, but a cold
      first check still embeds everything (6 000 sentences ≈ 77–93 s on this CPU; batch 64 fastest). On the VPS decide
      from `timings_ms` + the `/health` hit rate: lower `PRISM_MAX_SOURCE_SENTENCES`, pin a batch size measured there,
      and/or pre-warm the cache for popular OA sources. _(M)_
- [ ] **W6 follow-up · settle the confidence cutoff against really-retrieved sources.** ADR-0025 took this as far
      as public pair data allows and hit a wall: contamination makes the same-dataset FPR an upper bound (0.088) and
      a cross-dataset corpus a lower one (0.000), and no synthetic probe closes that gap. On the box, run the **full
      pipeline**: let the live retriever assemble a corpus for a real OA paper, then score passages known not to
      derive from it. Only then refit `k` / `pivot` and refresh `eval/gates.json`. _(M)_
- [ ] **Re-run the ADR-0024/0025 corpus calibration on the fixed splitter.** Both were measured while the splitter
      was truncating every sentence containing a decimal (ADR-0026). The pair-based numbers are unaffected — those
      never went through the splitter — but any claim about a *document* check did. Fold this into the W6
      re-measurement rather than repeating the synthetic probe. _(S)_
- [ ] **Realistic fixtures, so this bug class fails loudly.** Two silent bugs in one day (ADR-0026, ADR-0028) both
      sat between the user's text and the encoder, and both survived a green suite because every fixture was clean,
      unwrapped prose. Add a real-manuscript fixture — hard-wrapped text, statistics, `et al.`, a table — and check
      the parser against a downloaded OA PDF in the E2E. _(S)_
- [ ] **Widen the numeric guard's coverage, or decide not to** (ADR-0026). It is silent on the 53–90% of pairs
      where one side states no number. The same "same shape, different facts" idea extends to named entities and
      dates; both need the same measure-first treatment, and "not worth it" is a valid answer. _(M)_

## 🟢 Next — the product (W7–W12, LAUNCH_PLAN §9)
- [~] **W7 · Accounts + persistence** — backend **code-complete** (ADR-0029 store, ADR-0030 auth/ownership/quota,
      2026-09-07). **Needs the owner:** a Supabase project → set `PRISM_AUTH_JWT_SECRET` *or* `PRISM_AUTH_JWKS_URL`
      (+ `PRISM_AUTH_ISSUER`); decide the free quota (`PRISM_QUOTA_CHECKS`); then the sign-in UI (supabase-js magic
      link) that stores the session token for `authHeaders()`. _(S once a project exists)_
- [~] **W9 · CoachStage** — backend **built, dark by default** (ADR-0031, 2026-09-07): ≤3 calls/check, cached,
      daily cap, matcher post-filter + narrow evasion lexicon, labelled AI-written, fails soft. **Needs the owner:**
      an OpenAI key with ZDR → `PRISM_COACH_ENABLED=true` + `PRISM_OPENAI_API_KEY`; then read ~20 real cards for
      tone/quality before exposing it. Per-*account* $ ceiling waits for W11. _(S once a key exists)_
- [ ] **W10 · ReportStage** — submission-risk report + re-check. _(M)_
- [ ] **W11 · Payments + legal** — Razorpay; Privacy/ToS/AUP; CI honesty gate on copy. _(M)_
- [ ] **W12 · Launch.**

## 🔵 Later
- [ ] AI-generated-text signal — deferred (ADR-0016); when built, honesty-gated on RAID/HC3/M4 + a real ESL set.
- [ ] OCR for scanned PDFs (currently rejected with a clear message).
- [ ] Batch upload + history; PAWS-X for translated evaluation.
- [ ] (If institutional) SOC 2, LTI 1.3, SSO.

## ✅ Done
- [x] 2026-09-07 — **W9 coaching backend** (ADR-0031): model phrases, rules decide, matcher post-filters; bounded,
      cached, priced in the open, labelled. Also `scripts/pg_tests.py` (embedded Postgres; 293/0 locally) after a
      one-test red CI run. Tests 255 → 275 (+18 Postgres-only).
- [x] 2026-09-07 — **Auth + ownership + per-user quota** (ADR-0030): Supabase JWT verifier (HS256 + JWKS), 404-not-403
      ownership on jobs, usage ledger with 402 over quota, limiter bypass for accounts. Anonymous unchanged until
      configured. Tests 231 → 255 (+18 Postgres-only in CI).
- [x] 2026-09-06 — **`PostgresJobStore` + JobStore contract suite** (ADR-0029): durable, replica-readable job state
      behind the ADR-0019 seam; CI runs the contract against a real `postgres:16` and fails if it was skipped. Also
      fixed a latent circular import (`import worker` failed cold). Tests 221 → 231 (+11 Postgres-only in CI).
- [x] 2026-09-06 — **Hard-wrapped plain text fixed** (ADR-0028): `.txt`/`.md` manuscripts wrapped at 60–80 columns
      were compared line by line — a wrapped paragraph went from **0 matches to 2 at 0.875** against a genuine
      paraphrase of itself. Found by pointing the parser at a real academic PDF instead of the synthetic fixture;
      the PDF path itself came out clean. Tests 215 → 221.
- [x] 2026-09-06 — **`pip-audit` in CI + 4 dependencies upgraded** (ADR-0027): the first run found **16 advisories
      in 4 packages**, including 7 in `python-multipart` (parses every upload) and 7 in `starlette`. Fixed by
      fastapi 0.115→0.141 (starlette 0.38.6→1.6.0), python-multipart→0.0.32, python-dotenv→1.2.3,
      requests→2.34.2, arxiv→4.0.1. Audit is now blocking and clean; verified with tests, a real uvicorn and E2E.
- [x] 2026-09-06 — **Sentence splitter fixed + numeric guard** (ADR-0026): the splitter broke on every period, so
      any sentence with a decimal (`8.79`, `p = 0.05`) was truncated and its remainder **dropped, never compared** —
      19.9% of MRPC sentences, 5.8% of STS-B, 4.2% of QQP. Fixed with named exceptions, no NLP library. Then the
      guard: a confident paraphrase that shares essentially no figure with its source becomes `review` (STS-B
      72.4% of negatives caught for 2.0% of positives; gate 0.20 because the ratio peaks there). Verified through
      the live API and the browser. Tests 188 → 215.
- [x] 2026-09-06 — **Re-measured ADR-0024 honestly** (ADR-0025): corpus **relevance** beats corpus **size**
      (a retrieved 100-sentence corpus behaves like a random 1 000–3 000-sentence one; FPR is flat in N), and the
      original probe was contaminated by unlabelled duplicates — bounded FPR@0.78 at N=3 000 is 0.088, not 0.108,
      and 0.000 where no true match can exist. Drift (≈0.17/decade) holds. **No behaviour change, deliberately.**
      Probe gained `--distractors retrieved`, `--pool`/`--pool-only`, `--drop-above`, `--examples`. Tests 180 → 188.
- [x] 2026-09-06 — **Corpus-scale calibration** (ADR-0024): measured the max-over-N effect (top score for
      unrelated text drifts ≈0.16/decade; p95 = 0.88 at 3 000 sentences, above the old 0.78 cutoff) and made the
      confidence cutoff scale with corpus size. Only ever moves matches to `review`, never to clean.
- [x] 2026-09-06 — **Embedding cache** (ADR-0023): keyed by (model, sentence); measured **6.0× faster re-check**
      (39.3 s → 6.6 s); bounded, disableable, fails soft, hit rate on `/health`. Tests 151 → 165.
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
