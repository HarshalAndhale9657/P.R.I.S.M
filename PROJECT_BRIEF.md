# P.R.I.S.M. — Project Brief & Knowledge Base

> Single source of truth for what PRISM is, what's built, and what's next.
> Keep this current. Detailed history lives in [`CHANGELOG.md`](CHANGELOG.md) /
> [`docs/PROGRESS.md`](docs/PROGRESS.md); decisions in [`docs/DECISIONS.md`](docs/DECISIONS.md); plan in [`ROADMAP.md`](ROADMAP.md).
>
> **Last updated:** 2026-08-30 · **Status:** Originality Checker **live** (Phases 1–3 + eval). **Core-ML W1 landed**:
> re-architected to a pluggable pipeline + public-dataset eval harness + model registry (ADR-0015/0016; pretrained-first,
> plagiarism-first, **no PAN**). Next: W2 real baseline on PAWS/MRPC.

---

## 1. One-liner

**PRISM helps a writer find plagiarism in a paper — *what* is copied, *where* it is, and *which source* it came from** — as a non-accusatory self-check, backed by a measured false-positive rate.

Originally a hackathon *stylometric authorship* tool ("does this read like one author?"); **pivoted** to source-attribution plagiarism because that's the real job-to-be-done (the old engine's detection was near-noise — see §6).

---

## 2. Product direction (finalized)

| | Old (legacy) | Now (shipped) |
|---|---|---|
| Core question | "How many authors?" | "Is any passage copied, **where**, and **from what source**?" |
| Method | spaCy stylometry → HDBSCAN clustering | **Source-matching** every passage against a corpus |
| Output | Integrity verdict + 0–10 score | **Originality report**: highlighted matches → sources + overall % |

**Finalized decisions** (Q&A + ADRs):
- **Product (ADR-0014):** a freemium **"publication-readiness / integrity coach"** — an author preparing a
  manuscript for **IEEE / arXiv / a journal** (all disciplines; ESL/early-career esp.) checks it *before*
  submitting and **fixes issues honestly** so it clears the publisher's integrity gate (iThenticate/Crossref
  Similarity + AI checks). Detect → **triage each flag by remediation type** → **coach the honest fix**
  (quote+cite, add reference, disclose self-reuse/AI use, or author-driven rewrite with the source shown) →
  submission‑risk report. Mirrors/reduces the gate; does **not** promise a guaranteed pass.
- **⛔ Hard ethical boundary:** **no detection-evasion** — no auto-rewrite-to-lower-similarity, no "AI
  humanizer." Those deceive the publisher's check = academic fraud, and kill the honest brand. Rewriting is
  only ever author-driven, source-visible, own-understanding revision.
- **Detect:** verbatim + paraphrase + translated ✅ · **AI-generated risk** ⏳ (now in scope — calibrated + hedged, part of the coach).
- **Corpora:** user-uploaded references ✅ + open-access academic DBs (**OpenAlex + arXiv**) ✅ · web layer later (phased). (Crossref dropped — no abstracts.)
- **Legacy stylometry engine:** retired as the spine (kept at `authorship.html`); PDF parser reused.

---

## 3. Architecture (implemented)

New endpoint **`POST /api/check`** (paper + optional references + `use_academic`):

1. **Parse & segment** — `pdf_parser` (PDF) or plaintext (TXT) → paragraphs with page/char anchors; matcher segments into word tokens + sentences (offset-preserving).
2. **Sources** — user uploads (local, full-text) and/or **OpenAlex + arXiv** candidates (`academic_corpus.py`: builds queries from the doc, fetches abstracts from both providers concurrently, dedups by title).
3. **Match** (`plagiarism_matcher.py`, pure/deterministic):
   - **Verbatim** — k-gram anchoring + greedy extension → exact char spans (case/punct-insensitive).
   - **Paraphrase** — local MiniLM sentence-embedding cosine ≥ 0.66 (recalibrated via the expanded eval).
   - **Translated** — same paraphrase path; when passage vs source **language differs** (`langdetect`), re-labelled `translated` with the language pair.
   - Degrades to verbatim-only if the model is unavailable; academic search degrades to a warning on network failure.
4. **Aggregate** — per passage: best match (type, similarity, doc span, source span+context, paragraph, origin, url); overall / verbatim / paraphrase / translated %.
5. **Report UI** (`index.html` + `js/check.js`): overall score (banded), breakdown bars, **highlighted document** (red/amber/teal by type), ranked **match list**, **side-by-side source comparison**, OpenAlex origin badges + links, and a **downloadable/printable evidence report**.

Honest constraint: verbatim needs source **full text** → most reliable against user uploads; OpenAlex gives **abstracts**, so academic matches are mostly semantic/paraphrase.

---

## 4. Features (shipped)

- Passage-level detection: **verbatim, paraphrase, translated** (with language pair).
- **Source attribution** against user references + **OpenAlex** (opt-in), with links.
- **In-context highlighting** + **side-by-side source comparison**.
- Overall similarity % + verbatim/paraphrase/translated breakdown + ranked matches.
- **Downloadable evidence report** (self-contained HTML → Print/Save PDF) with a method/limitations footer.
- Runs **offline** (no API key needed for the local matcher).
- **Measured**: CI-gated eval harness (precision/recall/F1 + false-positive rate).

Deferred: AI-generated-text signal (until calibrated/hedged); Crossref/arXiv corpora; async job model; batch/history.

---

## 5. Guardrails & principles (non-negotiable)

- **Self-check, non-accusatory** — no verdicts; framed as an author's originality report.
- **Never call a low-similarity/topical hit a "source match."**
- **Bias awareness** — semantic matching can over-flag ESL/technical writers; keep the human in the loop; limitations shown on every report.
- **No claim without a measured number** — do not reintroduce "100% accuracy / zero FP / prosecutable" (those were false; see §6).
- **Offline-by-default** — the deterministic path sends nothing to third parties.

---

## 6. Why we pivoted (measured reality of the legacy engine)

From `research/…/evaluation_results.json`, `ablation_results.json`, `prism_diagnostic.md`, `research/HONEST_AUDIT.md`:
- Authorship boundary **F1 ≈ 0.40**, recall ≈ 0.33 (PAN SOTA > 0.85).
- The 27 stylometric features add **~+0.02 F1** over a generic embedding that tracks **topic, not authorship**.
- Paragraph-level Yule's K / hapax / burstiness are statistically invalid < ~500 words.
- The old README "benchmark" is **N=2**; the "Idea Triplet" feature was **dead code**.

**New matcher, measured** (`scripts/eval_matcher.py`, controlled labelled set): **Precision 1.00 · Recall 0.86 · F1 0.92 · FPR 0.00** (verbatim 3/3, paraphrase 2/3, translated 1/1). Honest and CI-gated.

---

## 7. Codebase state

### 7.1 New (source-attribution) — the primary product
- `backend/pipeline/` — **pluggable check pipeline** (ADR-0015/0016): `base.py` (CheckContext + Stage protocol),
  `stages.py` (live RetrieveStage/MatchStage/LocalizeStage + skeletons for rerank/ai_risk/triage/coach/report),
  `orchestrator.py`. `main._compute_check` runs this; matcher + academic-search are injected (tests' seams intact).
- `backend/services/plagiarism_matcher.py` — the matcher (verbatim + paraphrase + translated). Pure, tested.
- `backend/services/academic_corpus.py` — OpenAlex + arXiv candidate retrieval (concurrent, deduped).
- `backend/modelhub/` — **model registry/cache/version** layer (bi-encoder today; W3 bge/gte ONNX + W4 cross-encoder slot in here).
- `backend/eval/` — **public-dataset paraphrase harness** (ADR-0016): `pairs.py` (unified schema + PAWS/MRPC/STS-B/QQP/PAWS-X loaders),
  `fetch_datasets.py`, `metrics.py` (P/R/F1/FPR + per-stratum + sweep + Brier), `scorer.py` (embedder seam), `run_pairs.py` CLI, `data/sample/` smoke set. **No PAN.**
- `backend/main.py` → `POST /api/check`.
- `frontend/index.html` + `frontend/js/check.js` + `css/styles.css` — the checker SPA.
- `backend/scripts/eval_matcher.py` — legacy 32-case eval harness (CI gate; now a *smoke test* — the real gate is `eval/`).

### 7.2 Legacy authorship engine (kept, secondary)
Served at `frontend/authorship.html`; `/api/analyze` pipeline: `pdf_parser → feature_engine → hdbscan_detector → gpt_analyzer → citation_forensics → source_tracer → report_generator`. Fixed this cycle so it runs offline end-to-end, but it is **not** the product spine.

### 7.3 Dead / parallel code — REMOVED (2026-08-21)
Deleted the 8 unreferenced "v3" modules (`pipeline_orchestrator`, `clustering`, `boundary_fusion`, `pelt_detector`, `topic_coherence`, `scoring_engine`, `window_aggregator`, `embedding_similarity_detector`) — verified not imported by live code (the unused fusion bought only ~+0.02 F1). `local_embeddings.py` is kept (used by the matcher).

### 7.4 Tech stack
- **Backend:** Python 3.12, FastAPI, **sentence-transformers** (MiniLM multilingual) + **langdetect**, spaCy, HDBSCAN, scikit-learn, PyMuPDF + pdfplumber, NLTK, arxiv, requests; OpenAI **optional**.
- **Frontend:** vanilla HTML/CSS/JS (no build step); Chart.js (legacy page only).

### 7.5 API endpoints
`GET /` · **`POST /api/check`** → `202 + job_id` (async; validates uploads synchronously) · **`GET /api/check/{job_id}`** → `queued|running|done|error` (+ result) · `POST /api/upload` · `/api/parse` · `/api/features` · `/api/cluster` · `/api/reasoning` · `/api/citations` · `/api/analyze` (legacy) · `/api/v1/benchmark`.
> `/api/check` runs matching + OpenAlex in a bounded in-process worker (ThreadPoolExecutor) with a content-hash result cache. In-process only — use Redis/a real queue to scale across workers (ADR-0011).

### 7.6 Repo layout (key paths)
```
P.R.I.S.M/
├── PROJECT_BRIEF.md   CLAUDE.md   README.md(legacy, being de-hyped)   prism_diagnostic.md
├── CHANGELOG.md  ROADMAP.md  TODO.md  CONTRIBUTING.md  SECURITY.md
├── docs/            DECISIONS.md, PROGRESS.md
├── .github/workflows/ci.yml
├── backend/
│   ├── main.py  models.py  requirements.txt  .env.example
│   ├── _smoketest.py (legacy pipeline)   _smoketest_check.py (matcher)
│   ├── scripts/eval_matcher.py (+ eval_matcher_results.json)
│   ├── services/  (plagiarism_matcher, academic_corpus, local_embeddings + legacy stages + dead v3)
│   └── prompts/   venv/(gitignored)
├── frontend/
│   ├── index.html (Originality Checker)   authorship.html (legacy)   _serve.py (no-cache dev server)
│   ├── css/styles.css   js/ (check.js + legacy app/upload/heatmap/charts/citations/sources/report)
├── research/   tests/(0-byte placeholder PDFs)
```
> Browser E2E harness is outside the repo at `d:\PRISM-UI\_e2e\` (Playwright + screenshots).

---

## 8. How to run (dev)
```powershell
cd P.R.I.S.M\backend  && venv\Scripts\uvicorn main:app --host 127.0.0.1 --port 8000   # offline OK
cd P.R.I.S.M\frontend && python _serve.py 3000     # http://localhost:3000  (Originality Checker)
```
Legacy authorship view: `http://localhost:3000/authorship.html`. Add `OPENAI_API_KEY` to `backend/.env` only for the legacy GPT features.

## 9. Testing
- `backend/scripts/eval_matcher.py` — **evaluation harness** (precision/recall/F1 + FPR); CI gate.
- `backend/_smoketest_check.py` — offline matcher unit-smoke (verbatim + paraphrase + translated).
- `_e2e/check_e2e.mjs`, `check_academic_e2e.mjs`, `check_translated_e2e.mjs` — Playwright E2E (all green, 0 errors).
- Legacy: `backend/_smoketest.py`, `_e2e/test.mjs`.
- CI: `.github/workflows/ci.yml` (imports, smokes, eval gate, JS syntax).

## 10. Glossary
- **Verbatim** — copied text (n-gram overlap). **Paraphrase** — reworded (embedding cosine). **Translated** — copied across languages (cross-lingual embedding + language-pair). **Source attribution** — linking a passage to the document it came from. **Self-check** — the author checks their own draft.
