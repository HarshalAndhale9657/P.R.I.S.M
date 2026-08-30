# TODO — near-term backlog

Actionable tasks. Full plan: [`ROADMAP.md`](ROADMAP.md) · rationale: [`docs/DECISIONS.md`](docs/DECISIONS.md).
Check items off with a date. Newest priorities on top.

> **AUTHORITATIVE PLAN:** [`docs/LAUNCH_PLAN.md`](docs/LAUNCH_PLAN.md) — 12-week solo/bootstrap plan to a paid launch
> (beachhead = India/UGC PhD authors; honest coach; ₹149 hero SKU; no evasion).
> **⚙️ REVISED core-ML-first (ADR-0015 + ADR-0016):** weeks 1–5 buy the honest core before SaaS plumbing —
> **pretrained-first, plagiarism-first, public datasets only, NO PAN.**
> **Week 1 (start here, offline):** re-architect into a **pluggable pipeline** (`parse → retrieve → match → rerank →
> ai_risk → triage → coach → report`) + first-class `eval/` harness (pluggable dataset loader) + `models/` layer;
> existing matcher/corpus become stage impls; keep all 22 tests green. **Week 2:** stand up a **REAL benchmark** from
> **public paraphrase sets (PAWS/MRPC/STS-B/QQP)** — no PAN — freeze as the CI gate (synthetic 32-case → smoke test).
> Then: bi-encoder upgrade (W3), pretrained cross-encoder rerank + OA full-text (W4), selective reranker fine-tune on
> free GPU only if it beats pretrained (W5), deploy (W6). **AI detector deferred** behind this.

## 🔴 Now — core ML (ADR-0015 + ADR-0016: pretrained-first, plagiarism-first, public data, NO PAN)
- [ ] **W1 · Re-architect to a pluggable pipeline** — stage interfaces `parse → retrieve → match → rerank → ai_risk →
      triage → coach → report`; move `plagiarism_matcher`/`academic_corpus` behind them; add `eval/` (run any stage over
      a dataset, pluggable dataset loader) + `models/` (download/cache/version). Keep the 22 tests green. _(L)_ **← start here (offline).**
- [ ] **W2 · Real benchmark = CI gate (public sets, NO PAN)** — loaders for **PAWS, MRPC, STS-B, QQP** (+ **PAWS-X**);
      run the ACTUAL matcher; report P/R/**FPR per stratum** incl. a high-overlap-not-paraphrase stratum (≈ ESL/boilerplate
      risk); freeze as the gate. Keep `eval_data.json` (32) only as a fast smoke. _(L)_
- [ ] **W3 · Bi-encoder upgrade (no training)** — MiniLM → `bge-base`/`gte-base` (ONNX; multilingual for translated);
      recalibrate on the real benchmark; **ship only if recall ↑ with FPR flat** (esp. high-overlap negatives); torch fallback. _(M)_
- [ ] **W4 · Cross-encoder rerank (pretrained) + OA full-text** — pretrained cross-encoder over top-k for hard
      paraphrases (recall 0.77 → ↑); add **Semantic Scholar** + **Unpaywall/arXiv/PMC** full text; re-eval, keep gate green. _(L)_
- [~] **W5 · Selective cross-encoder fine-tune (go/no-go)** — **kit is ready**: `backend/training/` (script +
      README + 8 gate tests). Full fine-tune (not LoRA — roberta-base is small; rationale in the README) on a free
      Colab/Kaggle T4; **the script enforces the gate itself** (FPR must not rise, best-F1 +≥0.01, Brier must not
      worsen). ⏳ **Needs someone to run one GPU session** — cannot be driven from the coding environment.
      "Do not ship" is a legitimate outcome; keep `cross-encoder-stsb` and bank the time. _(M)_
- [ ] **Later · AI-text detector** — deferred behind plagiarism-first (ADR-0016); when built, honesty-gated on RAID/HC3/M4 + real ESL set. _(L)_

## ✅ Now — honesty & safety (done)
- [x] `README.md` de-hyped (removed overclaims; benchmark relabelled N=2 legacy; pivot banner).
- [x] `main.py` security baseline: CORS allow-list (`PRISM_ALLOWED_ORIGINS`), paper size cap (413 via
      `_enforce_size`), generic client errors everywhere (`_server_error` helper; `str(e)` swept from every endpoint).
- [x] Deleted the 8 dead "v3" modules (verified unreferenced by live code).

## 🟢 Next — robustness & coverage
- [x] `tests/`: pytest + FastAPI `TestClient` suite (22 tests, offline, CI-gated) — matcher units + async `/api/check` lifecycle/errors.
- [x] Async job model for `/api/check` (202 + job_id; bounded `ThreadPoolExecutor` worker; `GET /api/check/{job_id}`; content-hash cache).
      Follow-up: per-provider circuit breaker; Redis/persistent store for multi-worker scale.
- [x] Added **arXiv** alongside OpenAlex (concurrent + deduped). Crossref dropped (no abstracts); Semantic Scholar needs a key.
- [x] Expanded eval (`scripts/eval_data.json`, 32 cases): recall-by-type/difficulty + **per-stratum FPR** + gates;
      recalibrated paraphrase threshold 0.75 → 0.66. (Later: a small real-corpus study.)
- [ ] 2–3-sentence sliding windows for finer paraphrase localization (targets hard-paraphrase misses). _(now folded into W4 cross-encoder rerank.)_
- [ ] Calibrated similarity → confidence + abstain band. _(now folded into W3/W5 calibration on the real benchmark.)_

## 🔵 Later
- [ ] AI-generated-text signal — **deferred behind plagiarism-first** (ADR-0016); honesty-gated on RAID/HC3/M4 + real ESL set. See core-ML section.
- [ ] Batch upload + analysis history.
- [ ] Pydantic response models; structured logging/metrics.
- [ ] (If institutional) SOC 2, LTI 1.3, SSO.

## ✅ Done
- [x] Fixed legacy pipeline offline end-to-end (report units, gpt boundaries, cluster warnings/override).
- [x] Full light-theme UI redesign (sidebar shell, SVG icons, restyled components).
- [x] Deep product analysis + PROJECT_BRIEF + project scaffolding.
- [x] **Phase 1** — verbatim + paraphrase vs. uploaded references; highlighted doc + side-by-side.
- [x] **Phase 2 (core)** — OpenAlex academic corpus (opt-in), origin badges + source links.
- [x] **Phase 3 (part 1)** — translated detection (cross-lingual + language pair).
- [x] **Downloadable evidence report** (HTML → Save as PDF).
- [x] **Evaluation harness** (precision/recall/F1 + FPR) wired into CI as a gate.
