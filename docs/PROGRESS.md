# Progress Log

Running worklog — the **memory of *what happened when***. Newest first. One entry per working session.
(Decisions go in [`DECISIONS.md`](DECISIONS.md); shipped changes go in [`../CHANGELOG.md`](../CHANGELOG.md).)

---

## 2026-08-30 — Core-ML direction locked (ADR-0016) + W1 re-architecture landed

**Decisions (owner Q&A → ADR-0016, amends ADR-0015):** invest in real ML **plagiarism-first**,
**pretrained-first + fine-tune selectively** (only the paraphrase cross-encoder, on free Colab/Kaggle GPU, and
only if it beats pretrained), measured on **ready-made PUBLIC datasets** (PAWS/MRPC/STS-B/QQP/PAWS-X). **No PAN**
— found the on-disk `research/datasets/pan/` (14,473 docs) is PAN-2023 *style-change* (labels
`is_multi_author/num_authors/boundaries`): the authorship task we pivoted away from, with no doc→source pairs, so
it cannot benchmark/train the matcher (and owner excluded PAN anyway). AI-text detector **deferred** behind the
plagiarism work (still honesty-gated). Rewrote LAUNCH_PLAN §3/§5/§9, ROADMAP, TODO to match.

**W1 shipped (offline re-architecture) — the existing matcher/corpus are now stage implementations:**
- `backend/pipeline/` — injectable stages `parse → retrieve → match → rerank → ai_risk → triage → coach → report`
  (`base.py` context/protocol, `stages.py` live RetrieveStage/MatchStage/LocalizeStage + skeletons, `orchestrator.py`).
  `main._compute_check` now runs the pipeline; matcher + `academic_search` injected from module globals so the
  22 existing tests (incl. the two monkeypatch seams) still pass unchanged.
- `backend/eval/` — dataset-agnostic paraphrase-pillar harness: unified `pairs.jsonl` schema + loaders
  (`pairs.py`), `fetch_datasets.py` (explicit HF download → schema), stdlib-only `metrics.py` (P/R/F1/FPR +
  FPR-by-stratum + threshold sweep + Brier), `scorer.py` (embedder-cosine seam W3/W4 will swap), `run_pairs.py`
  CLI. Committed a 10-pair smoke sample (NOT a benchmark) so it runs offline.
- `backend/modelhub/` — model registry/cache/version layer (named `modelhub/` since `models.py` is taken);
  registers the bi-encoder today, ready for W3 bge/gte ONNX + W4 cross-encoder.
- Verification: full pytest green (22 existing + new pipeline/eval tests), `eval_matcher.py` gate still PASS
  (matcher untouched), `eval.run_pairs sample` runs end-to-end.

**W2 — the honest real-data baseline (PAWS 2000 val, MRPC 408 val; bi-encoder cosine, matcher threshold 0.66):**
| dataset | P | R | F1 | FPR | Brier | note |
|---|---|---|---|---|---|---|
| **PAWS** | 0.434 | 1.000 | 0.606 | **1.000** | 0.538 | flags *everything*; no threshold separates (best-F1 t=0.86 → FPR 0.978) |
| **MRPC** | 0.759 | 0.935 | 0.838 | **0.643** | 0.193 | to hit FPR≤0.15 recall collapses to 0.45 (t=0.90) |

**This is the point of the whole exercise.** My self-authored 32-case set reported **P=1.00 / FPR=0.00**; real
third-party data says the paraphrase pillar (bi-encoder cosine in isolation, on sentence pairs) runs at **FPR
0.64–1.00** at the same threshold. The self-authored benchmark was drastically over-optimistic. Caveats (honesty):
this measures the *pairwise paraphrase scorer alone*, not the full matcher in product context, and **PAWS is
adversarial by construction** (word-order swaps with near-identical bag-of-words — designed to break bi-encoders),
so PAWS FPR=1.0 is a worst-case stress test, not expected real-world prevalence. But the direction is unambiguous:
a bi-encoder cosine + single threshold cannot handle high-overlap negatives (the ESL/shared-terminology trap).
Artifacts: `eval/results/pairs_paws.json`, `pairs_mrpc.json`. **This is the frozen baseline** the W3/W4 work must beat.
**Next (W3/W4):** stronger ONNX bi-encoder, then the **cross-encoder reranker** (the real fix for PAWS-style
word-order sensitivity), recalibrate threshold on this data. Gate stays defined but non-blocking in CI until it's in range.

**W3/W4 — detection-lift experiments (same PAWS 2000 / MRPC 408; model quality via torch, ONNX packaging deferred to W6):**
| model | PAWS FPR@0.66 | PAWS best-F1 | MRPC FPR@0.66 | MRPC F1 | MRPC recall@FPR≤15% |
|---|---|---|---|---|---|
| MiniLM (W2 baseline) | 1.00 | 0.61 | 0.64 | 0.84 | 0.44 |
| all-mpnet-base-v2 (W3) | 0.99 | 0.62 | 0.64 | 0.84 | 0.44 |
| cross-encoder STS (W4) | 0.99 | 0.62 | **0.40** | **0.865** | **0.61** |

Honest findings: (1) a **stronger bi-encoder barely helps** — mpnet ≈ MiniLM everywhere; bi-encoders plateau on
this. (2) The **cross-encoder materially helps *realistic* paraphrase (MRPC): FPR 0.64→0.40, F1 0.84→0.865,
recall@FPR≤15% 0.44→0.61** — validates the W4 direction. (3) **PAWS stays hard for all three** because I used an
*STS-similarity* cross-encoder (`stsb-roberta`), and STS still rates word-order swaps as "similar"; PAWS needs a
**paraphrase-identity** model (`cross-encoder/quora-roberta`, already registered) or the W5 fine-tune. Artifacts:
`eval/results/pairs_*_{mpnet,…}.json` (git-ignored; numbers here are the record). **Next:** cross-encoder-qqp on
PAWS; then recalibrate the live threshold (MRPC best-F1 is already ≈0.66, so the cross-encoder is a drop-in on threshold).

**W4b + broadened benchmark (STS-B 1221, QQP 3000 added; 4 real datasets, 6629 pairs total).**
Cross-encoder comparison — **no single pretrained winner**, they trade off:
| model | PAWS FPR@0.66 | PAWS TN | PAWS Brier | MRPC F1 | MRPC FPR@0.66 |
|---|---|---|---|---|---|
| MiniLM (baseline) | 1.00 | 0 | 0.538 | 0.84 | 0.64 |
| mpnet | 0.99 | 6 | 0.516 | 0.84 | 0.64 |
| CE-stsb | 0.99 | 16 | 0.519 | **0.865** | **0.40** |
| CE-qqp | **0.85** | **167** | **0.430** | 0.788 | 0.52 |
CE-qqp is the first model to move PAWS at all (TN 0→167) but regresses MRPC — pretrained-first is now exhausted.

**⚠️ CORRECTION to the W2 alarm (I over-generalized from PAWS).** Adding two datasets whose negatives are
*same-topic but independently written* — the real ESL/boilerplate/shared-terminology risk — shows the baseline
bi-encoder is **much better than W2 implied**, and that **the threshold, not the model, is the main problem**.
Separation gap (mean pos − mean neg) is the decisive diagnostic:
| dataset | gap | FPR@0.66 | best operating point |
|---|---|---|---|
| STS-B | **0.460** | 0.234 | t=0.82 → **FPR 0.063, R 0.841, F1 0.813** |
| QQP | 0.303 | 0.451 | t=0.78 → FPR 0.257, R 0.856 |
| MRPC | 0.141 | 0.643 | t=0.82 → FPR 0.302, R 0.720 |
| PAWS | **0.007** | 1.000 | *none exists* |
**PAWS gap = 0.007** (mean pos 0.981 vs neg 0.974) — the distributions coincide, so **no threshold can ever
separate them**; that is a representational limit of bi-encoders on word-order/role swaps, not miscalibration.
It also confirms PAWS is partly **task-mismatched** for us: both its sentences always share an origin, so it tests
*semantic equivalence*, while plagiarism asks about *derivation* (reusing a source's words with roles swapped is
arguably a true positive for us). STS-B/QQP/MRPC are the product-relevant sets.
**Live threshold 0.66 is too low** (it was fitted to the self-authored set). Moving to ~0.78–0.82 roughly halves
FPR on every product-relevant set for ~10–15pp recall — the right trade for a tool whose cardinal sin is a false
accusation. **Caveat:** these are *pairwise* numbers, but the matcher takes a **max over many source sentences**,
which biases the top score upward (multiple comparisons) — so the pairwise-optimal threshold is a **lower bound**
for production. Verify on the matcher itself before changing the default.

**Threshold test on the ACTUAL matcher (synthetic set) — the two benchmarks disagree, and that IS the finding:**
| threshold | recall | FPR | smoke gate |
|---|---|---|---|
| 0.66 (live) | 0.765 | **0.000** | PASS |
| 0.70 → 0.82 | 0.647 | **0.000** | FAIL (old MIN_RECALL 0.70) |
FPR is **0.000 at every threshold** → the synthetic negatives never approach the boundary, so raising the cutoff
is pure recall loss there while the real data shows a large FPR win. Conclusion: the *synthetic instrument* is
wrong, not the real-data conclusion.

**→ Shipped (ADR-0017), decided with the owner:**
1. **Confidence band instead of moving one cutoff.** 0.66 is now the *reporting floor*; `confident_threshold=0.78`
   is the *confidence* cutoff. Each match carries `confidence: confident|review`; `overall` gains
   `confident_pct` / `review_pct` / `review_count`; verbatim is always confident. **Additive — nothing detected is
   lost, borderline hits are just labelled honestly.** Implements the standing "prefer an inconclusive band over a
   false clean" guardrail.
2. **`scripts/eval_matcher.py` demoted to a SMOKE TEST** (banner + MIN_RECALL 0.70→0.55); **the quality gate is
   `python -m eval.run_pairs`** on public data. Its FPR must never be quoted as accuracy again.
**Still open:** render the review band distinctly in the UI/report (frontend follow-up); re-derive the cutoff after
the cross-encoder rerank lands (and account for the max-over-sources upward bias).

## 2026-08-21 (cont.) — Expanded eval set + threshold recalibration (ADR-0013)

- Expanded the benchmark to **32 labelled cases** (`scripts/eval_data.json`): positives by type × difficulty
  (verbatim/paraphrase/translated × easy/medium/hard incl. FR/ES/DE translations); negatives by **stratum**
  (same-topic, boilerplate, **ESL**, shared-terminology, unrelated). Rewrote `eval_matcher.py` to report
  **recall-by-group** + **FPR-by-stratum**, list misclassifications, and gate on overall recall/FPR + a
  per-stratum FPR ceiling.
- First run: **FPR 0.00 on every stratum** (incl. ESL — the group flagged as most at-risk) but paraphrase
  medium/hard recall was 0/3 each at threshold 0.75. A **threshold sweep** showed **0.66** is optimal:
  recall 0.647 → **0.765**, FPR still **0.00 everywhere**. Recalibrated 0.75 → 0.66 (ADR-0013); updated docs/UI.
- Honest remaining gap: **hard paraphrases** (0/3) — needs better features/sliding windows, not a lower threshold.
- **Verified**: eval gate PASS (P=1.00, R=0.765, FPR=0.00), matcher smoke PASS, pytest 22/22, all three E2E green.

---

## 2026-08-21 (cont.) — arXiv corpus (+ Crossref evaluated & dropped) (ADR-0012)

- Probed providers: OpenAlex ✅ (abstracts), arXiv ✅ (full summaries), Crossref 200 but **0/5 had abstracts**,
  Semantic Scholar 429. → Added **arXiv**, kept OpenAlex, **dropped Crossref** for content matching.
- Refactored `academic_corpus.py` into per-provider functions run **concurrently** (`ThreadPoolExecutor`),
  merged + de-duplicated by normalised title (prefer longer abstract), capped, re-id'd. Each provider is
  independently defensive (failure → warning). arXiv capped to 4 queries (slower).
- Frontend: "arXiv" origin badge (+ link) in the match list, comparison, and downloadable report.
- **Verified**: live `search()` returned 19 sources (10 arXiv + 9 OpenAlex), deduped, no warnings; pytest
  22/22; academic browser E2E green (0 errors).

---

## 2026-08-21 (cont.) — Async job model for /api/check (ADR-0011)

- `POST /api/check` now validates + reads uploads synchronously (fast-fail 400/413) then submits the heavy
  work (parse → sources → OpenAlex → match) to a bounded in-process `ThreadPoolExecutor` (4 workers) and
  returns **202 + job_id**. New **`GET /api/check/{job_id}`** returns `queued|running|done|error` (+ result).
- Added a **content-hash result cache** (idempotent re-submits return instantly — verified via curl) and a
  bounded in-memory job store. Made the embedding singleton **thread-safe** (double-checked locking) since
  matching now runs in worker threads.
- Frontend (`check.js`): submit → `pollJob()` loop → render. Refactored the endpoint body into a pure
  `_compute_check`; user-safe errors (`CheckError`) surface as the job error, everything else as a generic 500.
- **Verified**: pytest 22/22 (incl. 202 submit, 404 unknown job, worker generic + user-safe errors); manual
  curl submit→poll→done (cache hit was instant); all three browser E2E modes green (0 errors).
- Follow-ups: per-provider circuit breaker; Redis/persistent store for multi-worker scale.

---

## 2026-08-21 (cont.) — Robustness: pytest suite + error-leak sweep

- **Test suite** (`backend/tests/`, pytest + FastAPI `TestClient`): 19 offline, deterministic tests.
  `test_matcher.py` — verbatim/paraphrase/translated + edge cases (empty doc, no sources, non-overlapping
  spans, case/punct-insensitivity); model-dependent cases skip if sentence-transformers is absent.
  `test_check_api.py` — `/api/check` success contract, 400 (no source / bad type), 413 (size cap via
  monkeypatch), 422/400 (empty), and a test that internal exception text never leaks. `pytest.ini` scopes
  collection to `tests/` (so the legacy manual scripts aren't run). `requirements-dev.txt` added; CI runs `pytest`.
- **Error-leak sweep**: added `_server_error(context)` (logs server-side, returns generic 500); replaced raw
  `str(e)` in every client-facing handler (`/api/check`, `/api/upload`, and legacy read endpoints).
- Verified: `pytest` 19/19 green; compile + import clean; eval + smokes still pass.

---

## 2026-08-21 (cont.) — NOW list: honesty & safety (ADR-0010)

- Ran a read-only audit (3 parallel agents) → confirmed by grep: README overclaims, `/api/check` security
  gaps, and that all 8 "v3" modules are unreferenced by live code.
- **README de-hyped**: removed "100% accuracy / ZERO false positives / prosecutable / measurably superior /
  Full (Idea Triplets)"; benchmark section relabelled "Legacy Benchmark (N=2 — illustrative only)".
- **Security baseline** on `main.py`: CORS explicit allow-list (`PRISM_ALLOWED_ORIGINS`); `_enforce_size`
  20 MB cap (413) covering the primary paper across all read endpoints + `/api/upload`; generic client
  errors for `/api/check` + `/api/upload` (details logged server-side).
- **Deleted 8 dead modules** (`pipeline_orchestrator`, `clustering`, `boundary_fusion`, `pelt_detector`,
  `topic_coherence`, `scoring_engine`, `window_aggregator`, `embedding_similarity_detector`).
- **Verified**: eval gate PASS (P=1.00/R=0.86/FPR=0.00), matcher smoke PASS, backend imports clean, CORS
  header correct for allowed origin, and all three E2E modes (references/academic/translated) green — 0 errors.
- Follow-ups: sweep `str(e)` from legacy endpoints; auth/rate-limit + async job model before multi-user.

---

## 2026-08-21 (cont.) — Evaluation harness (measured trust)

- Built `backend/scripts/eval_matcher.py`: a controlled, labelled benchmark (verbatim / paraphrase /
  translated positives + hard negatives incl. same-topic originals & boilerplate). Reports passage-level
  precision / recall / F1, per-type recall, and the **false-positive rate**; writes a JSON artifact.
- Current results: **Precision 1.00, Recall 0.86, F1 0.92, FPR 0.00** (verbatim 3/3, paraphrase 2/3,
  translated 1/1). Honestly surfaces one missed paraphrase (below the 0.75 threshold) rather than
  rubber-stamping. Wired into CI as a regression gate (recall ≥ 0.60, FPR ≤ 0.34).
- This is the credibility backbone the product analysis called for — measured numbers, esp. the FPR that
  matters for a non-accusatory self-check tool.

---

## 2026-08-21 (cont.) — Phase 3 (part 1): translated-plagiarism detection

- Verified feasibility: `paraphrase-multilingual-MiniLM` scores EN↔FR translation ≈ 0.94 (unrelated ≈ 0.09);
  `langdetect` identifies languages reliably (ADR-0009).
- Matcher: detect passage + source language; when they differ, re-classify the paraphrase match as
  `translated` (carry `doc_lang`/`source_lang`); aggregation adds `translated_pct`.
- Frontend: teal highlight/bar/legend/badge, **language pair** (e.g. FR→EN) in the match list, comparison,
  and downloadable report.
- Tests: matcher smoke gains a cross-lingual case (fr→en, sim 0.91 → "translated"); new Playwright E2E
  (`check_translated_e2e.mjs`) green; references + academic E2E still green. Added `langdetect` to requirements.
- Deferred: AI-generated-text detection (Phase 3 part 2) until it can be calibrated + hedged.

---

## 2026-08-21 (cont.) — Phase 2: academic-database corpus (OpenAlex)

- Probed academic APIs (OpenAlex 200, Crossref 200, arXiv 301, Semantic Scholar 429) → chose **OpenAlex** (ADR-0008).
- `services/academic_corpus.py`: builds distinctive queries from the doc, searches OpenAlex, reconstructs
  abstracts from the inverted index, returns `SourceDoc`s. Defensive (network failure → warning).
- `POST /api/check` gains `use_academic`; matches carry `source_origin`/`source_url`; `SourceDoc` extended.
- UI: academic toggle (references optional when on), OpenAlex origin badges, clickable source links.
- **Verified:** seeded a doc with a real abstract sentence → OpenAlex retrieved that exact paper and the
  matcher flagged a 100% verbatim match attributed to it. Academic-mode Playwright E2E green (0 errors);
  references-mode E2E still green.
- Follow-ups: Crossref/arXiv corpora, async job model, sliding windows.

**Also shipped:** a **downloadable/printable evidence report** — "Download report" saves a self-contained
HTML (score, highlighted document, side-by-side matches with source links, method/limitations footer);
"Print / Save PDF" opens it to print. Client-side, offline, deterministic. Verified in the E2E (download
event + content assertions) and visually.

---

## 2026-08-21 (cont.) — Phase 1: Originality Checker shipped

**Goal:** build the first slice of the pivoted product — source-attribution plagiarism, references-first (ADR-0006).

- **Matcher** (`services/plagiarism_matcher.py`): pure/deterministic. Verbatim via k-gram anchoring +
  greedy extension (exact char spans, punctuation/case-insensitive); paraphrase via local MiniLM sentence
  embeddings (cosine). Calibrated threshold to **0.75** (measured: true paraphrase ≈ 0.81 vs unrelated ≈ 0.06–0.16).
  Degrades to verbatim-only if the model can't load.
- **API** (`POST /api/check`): paper + reference files (PDF/TXT) → localized matches (type, similarity,
  doc span, source span + context, paragraph) + overall/verbatim/paraphrase %. Input guards
  (size/count), graceful skips with warnings.
- **Frontend:** new primary `index.html` + `js/check.js` — dual upload (paper + references), highlighted
  document, ranked match list, side-by-side source comparison, reset. Legacy authorship app moved to
  `authorship.html`. New CSS component block.
- **Dependency:** added `sentence-transformers` (torch) to requirements + venv.
- **Tests:** `_smoketest_check.py` (offline matcher: verbatim + paraphrase found, original not flagged) and
  a Playwright E2E (`_e2e/check_e2e.mjs`) — both green, **0 console/page errors**. HTTP `/api/check` verified.

**Next:** the 🔴 NOW safety list (truthful copy, inconclusive state, neuter source tracer, security), then Phase 2 (academic-DB corpus).

---

## 2026-08-21 — Stabilize, redesign, analyze, pivot

**Goal:** make the app work end-to-end, bring the UI to industry grade, then decide the real product direction.

**Backend — fixed offline end-to-end (was crashing/garbage offline):**
- `report_generator.py`: `noise_percentage` was 0–100 but treated as 0–1 → every offline report said
  "Highly Plagiarized / 0.0" with "10000% noise". Fixed units, gated penalties on clustering reliability,
  rewrote the summary to name real signals.
- `gpt_analyzer.py`: `boundaries` are ints, not dicts → `AttributeError` silently killed AI reasoning. Fixed.
- `hdbscan_detector.py`: added missing `WarningCode` members; implemented documented noise-saturation override.
- Verified via new `backend/_smoketest.py` (in-process, offline) and a live `POST /api/analyze` (HTTP 200).

**Frontend — contract fixes + full redesign:**
- Fixed `heatmap.js` data paths (`data.features.*`), name-keyed profile lookup, reasoning shape →
  feature bars + AI reasoning now render. `report.js` sub-scores derived from real data.
- Rewrote `sources.js` / `citations.js` to clean light-theme classes.
- **Redesign:** new `index.html` SaaS shell (sidebar workflow nav, SVG icons, contextual topbar);
  rewrote `css/styles.css` into a cohesive light design system; `app.js` updates topbar per panel.
- Verified with Playwright E2E (`d:\PRISM-UI\_e2e\`): all panels render, **0 console/page errors**.
- Added `frontend/_serve.py` (no-cache dev server) after a browser-cache issue showed stale HTML.

**Product analysis (8-lens, grounded in repo + web):**
- Convergent finding: the authorship detection is near-noise (F1 ≈ 0.40; features add ~+0.02 over a
  topic-tracking embedding); README overclaims contradict internal audits; not safe to accuse on.

**Pivot decided (owner Q&A):** core → **source-attribution plagiarism** (verbatim + paraphrase +
translated + AI), corpora = user uploads + open-access DBs, user = student self-check, retire the
stylometry spine. Captured in `PROJECT_BRIEF.md` + `docs/DECISIONS.md` (ADR-0001..0006).

**Also added:** `backend/.env.example`; project scaffolding (this file, CHANGELOG, ROADMAP, TODO,
CONTRIBUTING, SECURITY, CLAUDE.md, CI workflow).

**Next:** confirm Phase 1 build order (ADR-0006), then build the MVP matcher + reference-upload flow.
