# Roadmap

Vision: **the honest originality checker** — show a writer exactly what's copied, where, and from
which source, without ever falsely accusing them. Spec: [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` todo · _(S/M/L/XL)_ effort.

---

## ✅ Shipped (the Originality Checker)
- [x] **Matcher** — verbatim (k-gram → exact spans) + paraphrase (MiniLM cosine ≥ 0.75) + **translated**
      (cross-lingual + language pair via langdetect). Pure, deterministic, graceful degradation.
- [x] **`POST /api/check`** — paper + references (PDF/TXT) and/or **OpenAlex** (`use_academic`); input guards.
- [x] **Checker UI** (`index.html` + `check.js`) — dual upload, score + breakdown, highlighted document,
      match list, **side-by-side source comparison**, OpenAlex origin badges + links.
- [x] **Downloadable/printable evidence report** (self-contained HTML → Save as PDF) with limitations footer.
- [x] **Evaluation harness** (`scripts/eval_matcher.py`) — precision/recall/F1 + **false-positive rate** on hard
      negatives; JSON artifact; **CI gate**. Current: P=1.00, R=0.86, F1=0.92, FPR=0.00.
- [x] Legacy authorship engine fixed to run offline end-to-end; preserved at `authorship.html`.
- [x] State-of-the-art light UI + project scaffolding (CHANGELOG/ROADMAP/TODO/DECISIONS/PROGRESS/CI/SECURITY).

## 🎯 NORTH STAR — "publication-readiness / integrity coach" (ADR-0014, core-ML-first per ADR-0015)
> **The authoritative 12-week plan-to-launch is [`docs/LAUNCH_PLAN.md`](docs/LAUNCH_PLAN.md)** (beachhead = India/UGC
> PhD authors; stack, pricing ₹149 hero / ₹749 Pro, GTM, unit economics, milestones, risks). This epic is the summary.
>
> **⚙️ Sequencing (ADR-0015 + ADR-0016):** weeks 1–5 buy the honest core FIRST, **plagiarism-first** — re-architect
> to a pluggable pipeline (W1) → stand up a **real benchmark from public paraphrase sets** (PAWS/MRPC/STS-B/QQP, **no
> PAN**) as the CI gate (W2) → **bi-encoder upgrade** (W3) → **pretrained cross-encoder rerank + OA full-text** (W4) →
> **selective reranker fine-tune** on free GPU, ship only if it beats pretrained (W5) — then deploy (W6) and wrap in
> the compressed SaaS + coach + payments (W7–12). **Pretrained-first, fine-tune selectively; AI detector deferred.**
> Near-term tasks: [`TODO.md`](TODO.md).

Freemium tool: an author checks a manuscript before submitting to IEEE/arXiv/a journal and **fixes issues
honestly** so it clears the integrity gate. Detect → triage → coach the honest fix → submission-risk report.
**No detection-evasion** (no auto-rewrite-to-beat-the-score, no AI "humanizer"). Build phases:
- [ ] **A. AI-generated-risk module** — calibrated + hedged per-passage signal ("how a detector likely sees
      this + why"), never a verdict; the missing detection pillar. _(L)_
- [ ] **B. Flag triage** — classify each match: un-quoted quotation · cited/attributed · missing-citation ·
      common-phrase/boilerplate · self-plagiarism · too-close-paraphrase · AI-heavy (the fix differs per type). _(M)_
- [ ] **C. Honest remediation coaching** — per flag: quote+cite / add reference / disclose self-reuse+AI use per
      journal policy / author-driven rewrite in a source-visible workspace. (No one-click "beat the detector".) _(L)_
- [ ] **D. Submission-risk report** — estimated similarity + AI risk vs typical journal thresholds, a fix
      checklist, and a **re-check** after edits. Honest: "reduces risk", not "guaranteed pass". _(M)_
- [ ] **E. Freemium + reach** — accounts, per-month limits, paid tier; later a (paid) web-corpus layer. _(XL)_
> Feeds from NEXT below: sliding-window localization + calibrated confidence directly improve A–C.

## ✅ NOW — honesty & safety (done)
- [x] **De-hyped the legacy README** — removed "100% accuracy / ZERO false positives / prosecutable /
      measurably superior / Idea-Triplets"; benchmark relabelled N=2 legacy; pivot banner added.
- [x] **Security baseline** — CORS explicit allow-list (`PRISM_ALLOWED_ORIGINS`); paper upload size cap
      (413 via `_enforce_size`, all read endpoints); generic client errors for `/api/check` + `/api/upload`.
- [x] **Deleted the 8 dead "v3" backend modules** (verified unreferenced).
- [x] Swept raw `str(e)` from every endpoint (`_server_error` helper; generic client messages, server-side logs).

## 🟢 NEXT — robustness & coverage (1–3 months)
- [x] **pytest + FastAPI `TestClient` suite** — 22 offline tests (matcher units + async `/api/check` lifecycle/errors), CI-gated. _(M)_
- [x] **Async job model** — `POST` returns `202 + job_id`; a bounded worker runs matching + OpenAlex off the
      request path; `GET /api/check/{job_id}` polling; content-hash cache. (Follow-up: per-provider circuit
      breaker; Redis/persistent store for multi-worker scale.) _(L)_
- [x] **More corpora** — added **arXiv** (concurrent with OpenAlex, deduped). Crossref dropped (no abstracts to
      match against); Semantic Scholar needs a key (429 without). _(M)_
- [x] **Expanded the eval set** — 32 cases by type × difficulty + negative strata; recall-by-group + **FPR-by-stratum**;
      per-stratum FPR gate. Recalibrated paraphrase threshold 0.75 → 0.66 (R 0.65 → 0.765, FPR 0.00 everywhere). _(M)_
- [ ] **Finer localization** — 2–3-sentence sliding windows for paraphrase (targets hard-paraphrase misses). _(folded into W4 cross-encoder rerank.)_ _(M)_
- [ ] **Calibrated similarity** — map cosine → a calibrated confidence + abstain band. _(folded into W3/W5 calibration on the real benchmark.)_ _(L)_

## 🔵 LATER — depth & scale (3 months+)
- [ ] **AI-generated-text signal** — **deferred behind plagiarism-first** (ADR-0016); when built: *calibrated + hedged +
      honesty-gated* on RAID/HC3/M4 + a real ESL set (ships only if it clears a strict ESL false-positive bar, else disclosure-coach). _(L)_
- [ ] Batch upload + analysis history. _(L)_
- [ ] Pydantic response models to lock the API contract; structured logging/metrics. _(M)_
- [ ] (If institutional) SOC 2, LTI 1.3, SSO — only after validity + calibration are proven. _(XL)_

---
_All finalized decisions are logged as ADRs in [`docs/DECISIONS.md`](docs/DECISIONS.md); near-term tasks in [`TODO.md`](TODO.md)._
