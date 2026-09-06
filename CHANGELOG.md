# Changelog

All notable changes to P.R.I.S.M. are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### 2026-09-07 — Honest coaching, phrased by a model and policed by the matcher (W9, ADR-0031)

#### Added
- **`services/coach.py` + a real `CoachStage`** — up to 3 model calls per check (highest-priority flags first)
  return `what_it_is / why_flagged / honest_fix / do_not`. **Every field is post-filtered through the matcher:**
  any 8-word run copied from the source or the author's passage is replaced with the rule text and marked
  `filtered`; so is instrumental evasion language ("lower the score", "beat the checker", "humanize"…). Cached per
  (model, rule, passage, source); process-wide daily cap; per-call timeout; token usage priced into
  `estimated_cost_usd` from list price. Only the two excerpts ever leave the server. Fails soft with a stated
  reason. Off until `PRISM_COACH_ENABLED=true` + `PRISM_OPENAI_API_KEY`.
- `Match.coach` / `CheckResult.coach_summary` in the API contract; UI and report show the card labelled
  *AI-written guidance, grounded in the source shown*, with the number of parts the post-filter replaced.
- **`scripts/pg_tests.py`** + `pgserver` dev dependency — run the whole suite against an embedded PostgreSQL at
  your desk, no Docker: **293 passed, 0 skipped**.

#### Fixed
- The ADR-0030 CI run was red on one test of its own: `test_postgres_ledger_can_share_the_job_store_pool` dropped
  the store's table in teardown and then called `len(store)` on it. Teardown reordered; all 272 other tests had
  passed.
- The evasion lexicon's first draft banned "change a few words" — and caught the project's own rule text
  forbidding it. Narrowed to detector-beating language only; copied text is caught by the matcher, not the lexicon.

#### Verified
- ruff clean · 20 coaching tests · 275 passed / 18 skipped without a database, 293 / 0 with one · browser E2E 2/2.

### 2026-09-07 — Accounts without a gate: JWT verification, ownership, per-user quota (ADR-0030)

#### Added
- **`app/auth.py`** — verifies Supabase JWTs, HS256 (`PRISM_AUTH_JWT_SECRET`) or asymmetric via JWKS
  (`PRISM_AUTH_JWKS_URL`, cached, one refresh on an unknown `kid`). `current_principal` dependency; `Principal`
  carries only `sub`/`email`/`role`. Unconfigured = anonymous, exactly as before. `/health` reports
  `auth: off | optional | required`.
- **Ownership on jobs** — `JobRecord.owner`, both stores (`owner TEXT`, added idempotently to existing tables).
  `GET /api/v1/check/{id}` is **404** for anyone but the owner; anonymous jobs stay readable by id.
- **`worker/usage.py`** — a per-user usage ledger (memory + Postgres, sharing the job store's pool) behind a
  contract suite. `PRISM_QUOTA_CHECKS` per `PRISM_QUOTA_WINDOW_SECONDS`; over the limit is **402** with
  `X-Quota-Limit`/`X-Quota-Used`. Records acceptance, not completion; rejected uploads record nothing. Signed-in
  users are governed by the quota instead of the per-IP limiter.
- Frontend sends `Authorization: Bearer` when a session token exists; 401/402 surface the server's sentence.
- `PyJWT[crypto] 2.13.0`; lockfile regenerated, `pip-audit` clean. Tests 231 → **255** (+18 Postgres-only in CI).

#### Rules (tested)
- A presented token is **always** verified — bad/expired is 401 even when auth is optional; never a silent
  downgrade to anonymous. `auth_required` gates endpoints, not verification. Ownership answers 404, never 403.

#### Verified
- 255 passed / 18 skipped locally; JWKS path tested with generated RSA keys and a stubbed fetch; browser E2E 2/2
  on the anonymous path; Postgres halves run in CI (which fails if they skip).

### 2026-09-06 — Durable job state: `PostgresJobStore` (W7 storage half, ADR-0029)

#### Added
- **`worker/postgres_store.py`** — the second `JobStore` implementation, selected by `PRISM_DATABASE_URL`
  (unset = in-process memory, as before). Same five methods, same TTL semantics, same `JobRecord`; epoch floats
  in `DOUBLE PRECISION` so the expiry arithmetic is the in-memory store's expression verbatim; `update()`
  whitelists its columns so `**fields` can never reach SQL; one idempotent `CREATE TABLE IF NOT EXISTS`, no
  migration framework. Job state now survives restarts and is readable from any replica; execution stays on the
  replica that accepted the job. `/health` reports `store: memory | postgres`.
- **`tests/test_job_store_contract.py`** — one contract, parametrised over *both* stores. The Postgres half runs
  when `PRISM_TEST_DATABASE_URL` is set; **CI provides a `postgres:16` service container and fails if that half
  was skipped**, so green means Postgres actually ran.
- `psycopg[binary] 3.3.5` + `psycopg-pool 3.3.1`; lockfile regenerated, `pip-audit` clean.

#### Fixed
- **A latent circular import** (`worker.runner` → `app.logging_config`/`app.settings` → `app/__init__` →
  `factory` → `worker`). `import worker` failed cold and `tests/test_worker.py` failed in isolation; the suite only
  passed because an `app`-importing module sorted first. Context vars moved to `utils/context.py`; `app/__init__`
  resolves `create_app` lazily. Structural, not an import-order patch.

#### Verified
- ruff clean · **231 passed, 11 skipped** locally (the Postgres half, visibly) · `tests/test_worker.py` passes
  alone · Postgres contract verified by this commit's CI run (which cannot pass with it skipped).

### 2026-09-06 — Hard-wrapped plain text was checked as line fragments (ADR-0028)

#### Fixed
- **`.txt` / `.md` manuscripts wrapped at 60–80 columns were compared line by line, not sentence by sentence.**
  `_plaintext_blocks` never ran `_clean_block`, so single newlines reached the matcher — where a newline ends a
  sentence — and fragments under `min_sentence_words` were dropped without trace. **Measured: one wrapped
  paragraph checked against a genuine paraphrase of itself went from 5 fragments / 0 matches to 2 sentences /
  2 matches at 0.875 similarity.** A real paraphrase, missed completely.
  `_unwrap()` now joins a break only when the previous line does not finish a sentence *and* the next begins
  lower-case — headings and list items keep their own lines — and rejoins hyphenation across a wrapped line, as
  the PDF path already did.

#### Verified
- The PDF path was audited against a real academic paper (*Attention Is All You Need*, 15 pages) rather than the
  synthetic fixture, and came out clean: 4 969 words, 81 reference entries excluded, no ligature or hyphenation
  artefacts, 247 sentences at a median of 17 words.
- Tests 215 → **221**, including that the same prose reads identically wrapped and unwrapped.

#### Note for anyone comparing results
Documents that were quietly under-checked will now report **more** matches. That is the fix landing, not a
regression.

### 2026-09-06 — pip-audit in CI, and the 16 advisories it found on the first run (ADR-0027)

#### Security
- **Upgraded four vulnerable dependencies.** The first `pip-audit` run against the lockfile reported **16
  advisories in 4 packages**, all with fixes available: `python-multipart` 0.0.9 (**7** — this is the parser
  handling every file a user uploads), `starlette` 0.38.6 (**7** — the ASGI core), `requests` 2.32.5 and
  `python-dotenv` 1.0.1. Now `fastapi 0.115.0 → 0.141.1` (which allows `starlette>=0.46.0`, taking starlette to
  **1.6.0**), `python-multipart → 0.0.32`, `python-dotenv → 1.2.3`, `requests → 2.34.2`, and `arxiv 2.1.3 → 4.0.1`
  — forced by `requests`, since arxiv 2.1.3 pinned `requests~=2.32.0`; its API is unchanged at our call sites.
  **`pip-audit` now reports no known vulnerabilities.**

#### Added
- **`audit` job in CI (blocking)** — `pip-audit --strict --no-deps --disable-pip -r requirements.lock`. The
  *lockfile* is audited, not a fresh resolve: it is the exact set the production image installs. No resolver and
  no downloads, so it runs in seconds. An advisory with no fix goes in as an inline `--ignore-vuln <ID>` with a
  date, a name and a reason; deleting the step is not a way to go green.
- `pip-audit==2.9.0` in `requirements-dev.txt`, so the same command runs locally before pushing.

#### Fixed
- The lockfile header is plain ASCII. It contained an em dash, and `pip-audit` reads requirements files using the
  platform's default codepage — on Windows the audit died with a `UnicodeDecodeError` instead of an answer.

#### Verified
- ruff clean · 215 tests on the new stack · the app starts under a real uvicorn and `/health` answers · browser
  E2E 2/2 with 0 console errors (`TestClient` would not have caught an ASGI regression across a starlette major).

### 2026-09-06 — The sentence splitter was breaking on decimals; and a numeric guard (ADR-0026)

#### Fixed
- **The sentence splitter broke on every period**, so `"…was up 8.79 points, or 0.96 percent, at 929.06."` became
  the sentence `"…was up 8."` and the remaining fragments fell under `min_sentence_words` and were **dropped
  entirely** — most of the passage was never compared against anything. In a checker whose users write `p = 0.05`,
  `Fig. 3`, `et al. 2019` and `J. R. R.` this sat in the middle of the core loop. `split_sentences()` now treats a
  period as a boundary unless it is between digits, the dot of a listed abbreviation, an initial, or followed by a
  lower-case letter; newlines always break; offsets are preserved and the spans tile the text exactly.
  **Measured: the old rule over-split 19.9% of MRPC sentences, 5.8% of STS-B and 4.2% of QQP.**
  Rules with named exceptions, not a library — ADR-0018 deleted the last heavy NLP dependency and this does not
  bring one back.

#### Added
- **`services/numeric_guard.py`** — a confident paraphrase match whose passage and source **state numbers but
  share essentially none of them** is moved to `review`. Paraphrase only (never verbatim, never translated), one
  band only, never below the reporting floor, source always visible. `PRISM_NUMERIC_GUARD=false` disables it;
  `PRISM_NUMERIC_GUARD_GATE` (default 0.20) retunes it. The match carries `numeric_conflict`, triage explains the
  band in plain language, and the report footer says how many matches it moved.
- **`eval/run_numeric.py`** — the measurement that decided it, and the gate.

#### Measured
- At the 0.78 cutoff, over pairs where both sides state a number: catches **72.4%** of STS-B's non-paraphrase
  pairs for 2.0% of its true ones (36.9×), 30.2%/9.6% on QQP (3.15×), 24.0%/8.2% on MRPC (2.91×), and is silent on
  PAWS (0.2%/0.0%), whose negatives keep every number. **The gate is 0.20 because the ratio peaks there** on MRPC
  and QQP independently and sits on STS-B's plateau — not because it is a round number.
- Coverage is stated rather than hidden: the signal is silent on the 53–90% of pairs where one side has no number.

#### Changed
- The UI and report no longer say "below the confidence cutoff" for a match the numeric guard moved — two
  different reasons put a match in `review`, and naming the wrong one is a false statement about the check.
- Tests 188 → **215**. Benchmark gates (STS-B / MRPC / QQP) still pass; browser E2E 2/2, 0 console errors.

### 2026-09-06 — Corpus *relevance* beats corpus size, and the ADR-0024 probe was contaminated (ADR-0025)

#### Added
- **Three honesty knobs on the corpus probe** (`eval/corpus_scale.py`, `eval/run_corpus.py`):
  `--distractors retrieved` orders the corpus by relevance to the manuscript, the way retrieval actually
  assembles one; `--pool <datasets>` / `--pool-only` draw distractors from *other* datasets so no true
  paraphrase can be in the corpus; `--drop-above X` removes corpus sentences within X of any query and reports
  how many. `--examples N` dumps the top-scoring flags — every one a false positive by construction — so a human
  can see whether the construction is lying. Tests 180 → 188.
- `eval/data/README.md` documents the contamination found in QQP (unlabelled duplicate questions across pairs)
  and between STS-B and MRPC (shared source sentences).

#### Measured
- **Relevance is worth 10–30× the corpus size.** With the corpus ordered by relevance, the false-positive rate is
  flat in N: 87% of QQP's eventual FPR is present at **100** sentences (100% on STS-B). A retrieved 100-sentence
  corpus behaves like a random 1 000–3 000-sentence one.
- **ADR-0024's numbers were overstated.** On a corpus that cannot contain a true match, QQP's FPR is **0.000 at
  every threshold and size** (top score never exceeds 0.634). On the same-dataset pool, dropping 58 near-certain
  duplicates moves FPR@0.78 at N=3 000 from 0.108 to **0.088** and the p95 from 0.882 to **0.837** — and that is
  still an upper bound. The drift itself survives: **≈0.17 per decade**, reproducing ADR-0024's 0.16.
- **What survives de-duplication is boilerplate, not topic drift**: two S&P-500 report sentences with opposite
  directions and different numbers score **0.877**.

#### Changed
- `PlagiarismMatcher.confident_threshold_for` — the docstring now quotes the bounded numbers and states plainly
  that the formula counteracts the smaller half of the effect. **No behaviour change:** `k`, `pivot` and
  `ceiling` are unchanged, because the honest interval is wider than any refit would move them.

### 2026-09-06 — Corpus-scale calibration (ADR-0024)

#### Added
- **`eval/corpus_scale.py` + `eval/run_corpus.py`** — measure the multiple-comparisons effect the matcher lives
  with: FPR/recall vs corpus size, top-score drift for queries with no true match, and the lowest threshold that
  holds a given FPR budget at each size. `python -m eval.run_corpus qqp stsb`.
- **Corpus-size-aware confidence cutoff** — `confident(N) = clamp(base + 0.06·log10(N/500), base, 0.92)`,
  configurable via `PRISM_CONFIDENCE_*` and disableable. Results expose `confident_threshold` (applied),
  `confident_threshold_base` and `corpus_sentences`; a warning and the report footer explain the raise.

#### Measured
- Top score for text with **no** true match drifts ≈**0.16 per decade** of corpus size (QQP and STS-B agree).
  At 3 000 source sentences the p95 is **0.88** — above the old fixed 0.78 cutoff, i.e. 5% of unrelated text
  would have been labelled "confident".
  > **Corrected by ADR-0025 (same day):** part of that came from unlabelled duplicates in QQP — real matches
  > counted as errors. Bounded values: drift ≈0.17/decade (holds), p95 at 3 000 = **0.837**, FPR@0.78 = **0.088**,
  > and 0.000 on a corpus that cannot contain a true match. The entry above is kept as the record of what was
  > believed when the cutoff shipped.

#### Changed
- `RerankStage` re-decides the confidence band against the cutoff the matcher actually applied, not the base.

### 2026-09-06 — Embedding cache: re-checks are 6× faster (ADR-0023)

#### Added
- **`services/embedding_cache.py`** — process-wide LRU of sentence embeddings keyed by `(model_key, sha1(text))`.
  Source sentences only; duplicates within a call embedded once; vectors stored read-only; bounded in entries
  (`PRISM_EMBEDDING_CACHE_ENTRIES`, default 50 000 ≈ 75 MB, `0` disables); any failure degrades to a plain embed.
- Hit rate, entries, capacity and evictions on **`GET /health`** (`embedding_cache`).
- Tests 151 → 165 (correctness vs uncached, partial overlap, duplicate collapsing, order, model namespacing,
  LRU eviction, read-only storage, broken-cache fallback, bad-embedder fallback, config/disable).

#### Measured
- 1 800 source sentences over 2 papers, manuscript edited between runs: first check **39.3 s** → re-check
  **6.6 s** (**6.0×**, 32.8 s saved). Cold first checks are unchanged.

#### Fixed
- `PlagiarismMatcher` gains `embedding_model_key` so cached vectors are namespaced per model.

### 2026-09-06 — W8 flag triage + coach card (ADR-0022)

#### Added
- **`services/triage.py`** — deterministic remediation typing from auditable signals (quotation marks, citation
  markers in the containing paragraph, confidence band, cross-source repetition) into 8 types with priorities:
  `verbatim_uncited`, `paraphrase_uncited` (P1) · `verbatim_cited_unquoted`, `quoted_uncited` (P2) ·
  `paraphrase_cited`, `needs_review` (P3) · `common_phrase` (P4) · `quoted_cited` (P5). Each carries plain-language
  *what* + *honest fix* text; a test asserts that text never suggests detection-evasion.
- **`TriageStage`** is live (after localize, fails soft). Matches gain `triage`; results gain `triage_summary`
  (counts, prioritised action items, method/limits note). Both in the Pydantic contract.
- **UI:** a "What to fix" panel above the results, a triage badge on every match row, and a **coach card** in the
  detail pane — the fix first, the side-by-side evidence below, with the signals it was derived from.
- **Report:** a "What to fix" section and a per-match "Honest fix" line.
- Tests 130 → 151 (citation patterns incl. non-citations, quote detection, every rule, whole-document summary,
  translated note, anti-evasion assertion); E2E asserts the panel, badges, coach card and report content.

### 2026-09-06 — W4b retrieval depth (ADR-0021)

#### Added
- **Open-access full text.** When a retrieved candidate carries an OA PDF link (arXiv, OpenAlex
  `best_oa_location`, Semantic Scholar `openAccessPdf`), `services/fulltext.py` downloads it (https-only,
  private hosts refused, 15 MiB cap, `%PDF` sniffed, parsed by our parser, cached 1 h) and the matcher runs
  against the **full text** — verbatim matches against the literature are now possible. Up to 8 per check,
  chosen by lexical relevance. Settings: `PRISM_ACADEMIC_FULLTEXT*`.
- **Semantic Scholar** as a third academic provider, enabled only with `PRISM_S2_API_KEY`.
- `SourceDoc.kind` (`fulltext | abstract`) in `sources` and `per_source`; the UI tags abstract-only sources; the
  report's coverage statement says "N with full text, M abstract-only".
- `utils/ttl_cache.py` (shared by the worker and the fetcher). Tests: 105 → 129.

#### Changed
- Providers take a `ProviderContext` and return `Candidate`s (source + PDF links); duplicates across providers
  now union their PDF links.

### 2026-09-06 — Industry-grade pass (ADR-0018 · ADR-0019 · ADR-0020)

#### Removed
- **The legacy stylometric authorship engine** — `feature_engine`, `hdbscan_detector`, `gpt_analyzer`,
  `citation_forensics`, `source_tracer`, `report_generator`, `pdf_parser`, `models.py`, `prompts/`, the seven
  legacy endpoints, `authorship.html` + 7 frontend modules, `scripts/benchmark.py`, `scripts/evaluate.py`,
  legacy smoke scripts. Dependencies dropped: spaCy, HDBSCAN, ruptures, nltk, openai, httpx, tenacity. (ADR-0018)
- **45,099 tracked files** of the PAN-2023 corpus and `.gemini/` tooling untracked (wrong task; not ours to redistribute).
- The hard-coded Render API URL and the `localhost:8000/docs` link in the frontend.
- The false "all offline, on your machine" / "Local engine · offline" claims in the UI and report.

#### Changed — **BREAKING**
- API moves to **`/api/v1/check`** and **`/api/v1/check/{job_id}`**; `GET /` now returns the health snapshot.
- `main.py` is a shim over `app.create_app()`; all configuration via `PRISM_*` env (`app/settings.py`).
- `RetrieveStage` raises a user-safe error when no sources remain (was silently empty).
- Matcher: large reference sets are budgeted by **TF-IDF relevance across all sources** instead of first-N in upload order.
- `eval.run_pairs --gate` reads **per-dataset gates at the confident cutoff** from `eval/gates.json` (ADR-0020).

#### Added
- `app/` — pydantic-settings, **Pydantic response models** (real OpenAPI contract), request-id middleware,
  `Content-Length` guard, **per-IP rate limiting (429)**, `/health` + `/health/ready`, application factory, JSON logging.
- `worker/` — **bounded executor (503 + Retry-After)**, **TTL job store + result cache** (ephemeral by default),
  `CheckRunner`; results carry per-stage `timings_ms` and an `engine` block (version, model, thresholds, rerank, coverage).
- `services/document_parser.py` — checker-specific PDF/text parser (keeps short paragraphs, strips running
  headers/footers, excludes + reports the reference list, hyphenation repair, page/char caps, encrypted/corrupt handling).
- `pipeline.ParseStage`; `build_check_stages()`; `RawInput`.
- `academic_corpus`: pooled session with retries; contact email sent only when configured.
- Frontend: API base via `<meta name="prism-api-base">`; polling backoff; actionable 404/429/503 messages;
  academic-search data-flow disclosure; report method footer generated from `engine`.
- **Docker**: multi-stage, non-root, CPU-only torch, baked model, Python health probe. **`deploy/`**: Compose + Caddy
  (TLS, CSP) + `prism.env.example` + runbook. `requirements.lock` (uv, Linux/CPU). `.gitattributes` (LF).
- **CI**: ruff blocking; pytest with coverage floor 80%; Docker build + readiness smoke; Playwright E2E (specs now
  in `e2e/`); **public-dataset benchmark gate** (STS-B · MRPC · QQP).
- Tests: parser, worker (store/cache/executor/runner), rate limiter, academic corpus, schema round-trip,
  413/429/503 paths, ParseStage — 57 → 100+.
- Docs: README, SECURITY, PROJECT_BRIEF, CLAUDE, CONTRIBUTING, TODO, ROADMAP rewritten to match the code; ADR-0018/0019/0020.

### Direction
- **Pivot decided:** core reframed from *stylometric authorship* ("how many authors?") to
  **source-attribution plagiarism detection** ("what is copied, where, and from which source?").
  See [`docs/DECISIONS.md`](docs/DECISIONS.md) (ADR-0001..0009) and [`PROJECT_BRIEF.md`](PROJECT_BRIEF.md).
  The source-attribution Originality Checker is now **live** (Phases 1–3 + evaluation harness).
- **Core-ML investment decided (ADR-0015 → refined by ADR-0016):** within the ~3-month timebox, invest in real
  ML **plagiarism-first**, **pretrained-first + fine-tune selectively** (only the paraphrase cross-encoder, on
  free Colab/Kaggle GPU, and only if it beats pretrained), measured on **ready-made PUBLIC datasets**
  (PAWS/MRPC/STS-B/QQP/PAWS-X) — **no PAN** (the on-disk `research/datasets/pan/` is the PAN-2023 *style-change*
  task: wrong task, no doc→source pairs). AI-text detector **deferred** behind this (still honesty-gated). See
  [`docs/LAUNCH_PLAN.md`](docs/LAUNCH_PLAN.md) §5 + [`docs/DECISIONS.md`](docs/DECISIONS.md) ADR-0015/0016.

### Added — core-ML re-architecture (W1)
- **Pluggable pipeline** (`backend/pipeline/`) — clean, injectable stages
  `parse → retrieve → match → rerank → ai_risk → triage → coach → report`. Live today: `RetrieveStage`,
  `MatchStage`, `LocalizeStage` (wrapping the existing matcher + academic corpus); the rest are declared
  skeletons for W3–W9. `main._compute_check` now runs this pipeline (matcher + `academic_search` injected from
  the module globals, so behaviour and the tests' monkeypatch seams are unchanged).
- **Evaluation harness v2** (`backend/eval/`) — dataset-agnostic measurement of the paraphrase pillar against
  **public sentence-pair datasets**: a unified `pairs.jsonl` schema + loaders (`eval.pairs`), `eval.fetch_datasets`
  (explicit HF-`datasets` download → unified schema), stdlib-only `eval.metrics` (P/R/F1/specificity/FPR +
  **FPR-by-stratum** + threshold sweep + Brier), an embedder-cosine `eval.scorer` seam (what W3/W4 swap), and a
  CLI `python -m eval.run_pairs`. Ships a committed 10-pair **smoke sample** (not a benchmark) so it runs offline.
- **Model registry** (`backend/modelhub/`) — one place to name/version/lazily-load/cache models (the "models/
  layer"; named `modelhub/` because `backend/models.py` owns `models`). Registers the bi-encoder today; W3's
  bge/gte ONNX swap and W4's cross-encoder become registry entries.

### Added
- **arXiv academic corpus** — added arXiv alongside OpenAlex. Providers run **concurrently** and results are
  merged + de-duplicated by title (preferring the longer abstract). arXiv matches get an "arXiv" origin badge
  + link (in the UI and the downloadable report). *Crossref was evaluated and intentionally dropped for
  content matching — its records almost never carry abstracts (0/5 in testing), so there's nothing to match against.*
- **Test suite** (`backend/tests/`, pytest + FastAPI `TestClient`) — 19 tests, offline & deterministic:
  matcher unit tests (verbatim/paraphrase/translated/edge cases, model-aware skips) and `/api/check`
  integration tests (success contract, 400/413/422, size cap via monkeypatch, and a check that internal
  exception text never leaks to the client). `requirements-dev.txt` + `pytest.ini` added; wired into CI.
- **Evaluation harness** (`backend/scripts/eval_matcher.py` + `eval_data.json`) — a controlled, labelled
  benchmark (32 cases) that measures passage-level precision / recall / F1, **recall by type × difficulty**
  (verbatim/paraphrase/translated × easy/medium/hard), and the **false-positive rate per negative stratum**
  (same-topic, boilerplate, **ESL**, shared-terminology, unrelated). Writes a JSON artifact; CI-gated on
  overall recall + FPR **and a per-stratum FPR ceiling**. Current: **P=1.00, R=0.765, FPR=0.00 on every
  stratum** (incl. ESL); the honest gap is hard paraphrases (0/3).
- **Translated-plagiarism detection (Phase 3, part 1)** — cross-lingual matches are labelled `translated`
  (language identified with `langdetect`) and shown with the language pair (e.g. FR→EN), a teal
  highlight/bar/badge, and a `translated_pct`. The multilingual MiniLM already embeds across languages, so
  matching is unchanged — the paraphrase path is simply re-classified when source and passage languages differ.
- **Downloadable evidence report** — from the results view, "Download report" saves a self-contained,
  printable HTML report (header, score band, highlighted document, side-by-side matches with source
  links, and a method/limitations footer); "Print / Save PDF" opens it for printing. Offline, deterministic.
- **Academic-database corpus (Phase 2)** — check a paper without uploading sources:
  - `services/academic_corpus.py` — retrieves candidate sources from **OpenAlex** (free, no key):
    builds distinctive queries from the document, reconstructs abstracts, returns `SourceDoc`s that
    feed the same matcher. Fully defensive (network failure → warning, never raises).
  - `POST /api/check` gains `use_academic` (references become optional when on); matches carry
    `source_origin` + `source_url`; response adds `academic_used`.
  - UI: an "Also search open-access academic databases" toggle, **OpenAlex origin badges**, and
    clickable source links in the match list + comparison.
- **Originality Checker (Phase 1)** — the first slice of the new source-attribution engine:
  - `services/plagiarism_matcher.py` — deterministic matcher: **verbatim** (k-gram anchoring →
    exact char spans) + **paraphrase** (local MiniLM sentence embeddings, cosine). Pure & unit-tested;
    degrades to verbatim-only if the embedding model is unavailable.
  - `POST /api/check` — upload a paper + reference sources → localized matches (type, similarity,
    doc span, source span/context, paragraph) + overall/verbatim/paraphrase %; PDF & TXT; input guards.
  - New primary UI `index.html` + `js/check.js`: dual upload (paper + references), **highlighted
    document**, ranked **match list**, and **side-by-side source comparison**. Offline, self-check framed.
  - Legacy authorship app preserved at `authorship.html`.
  - `sentence-transformers` added to `requirements.txt`; `_smoketest_check.py` (offline matcher test).
- `PROJECT_BRIEF.md` — product spec & knowledge base (single source of truth).
- Project scaffolding: `CHANGELOG.md`, `ROADMAP.md`, `TODO.md`, `CONTRIBUTING.md`,
  `SECURITY.md`, `CLAUDE.md`, `docs/DECISIONS.md`, `docs/PROGRESS.md`, `.github/workflows/ci.yml`.
- `backend/.env.example` — documents optional `OPENAI_API_KEY` (system runs offline without it).
- `backend/_smoketest.py` — offline, in-process end-to-end pipeline check (no server/API key).
- `frontend/_serve.py` — no-cache static dev server (prevents stale HTML/CSS during dev).

### Fixed (offline end-to-end now works)
- `report_generator.py`: `noise_percentage` unit bug (0–100 treated as 0–1) that made the
  offline report always return "Highly Plagiarized / 0.0"; penalties now gated on clustering
  reliability; executive summary rewritten to name the real driving signals.
- `gpt_analyzer.py`: `boundaries` were iterated as dicts (`b.get(...)`) but are ints →
  `AttributeError` silently disabled AI reasoning. Now treated as paragraph indices.
- `hdbscan_detector.py`: referenced `WarningCode` members that didn't exist; implemented the
  documented **noise-saturation override** so short all-noise docs aren't flagged 100% anomalous.
- `models.py`: added `CLUSTER_HDBSCAN_UNAVAILABLE`, `CLUSTER_SCALING_FAILED`, `CLUSTER_FIT_FAILED`.
- Frontend `heatmap.js`: read `data.features.profiles`/`feature_names` (were wrong paths),
  name-keyed profile lookup, correct reasoning shape → feature bars & AI reasoning now render.
- `report.js`: derives real evidence sub-scores from the response (were always 10/10).

### Security
- **CORS** now uses an explicit origin allow-list (env `PRISM_ALLOWED_ORIGINS`; defaults to
  `localhost:3000` / `127.0.0.1:3000` / `5173`) instead of `allow_origins=["*"] + credentials`.
- **Upload size cap** — `_enforce_size` rejects files over `MAX_FILE_BYTES` (20 MB) with **413**, now
  covering the primary paper across every read endpoint (previously only reference files were capped) + `/api/upload`.
- **Generic client errors everywhere** — added a `_server_error` helper (logs server-side, returns a generic
  500); swept raw `str(e)` from `/api/check`, `/api/upload`, and the legacy read endpoints
  (`parse|features|cluster|reasoning|citations|analyze`). A test asserts internal detail never reaches the client.

### Removed
- Deleted 8 unreferenced "v3" backend modules (`pipeline_orchestrator`, `clustering`, `boundary_fusion`,
  `pelt_detector`, `topic_coherence`, `scoring_engine`, `window_aggregator`, `embedding_similarity_detector`)
  — verified not imported by live code (the unused fusion bought only ~+0.02 F1). `local_embeddings.py` kept (used by the matcher).

### Changed
- **Recalibrated the paraphrase threshold 0.75 → 0.66** — a data-driven improvement from the expanded eval:
  a threshold sweep showed 0.66 catches medium paraphrases (recall 0.65 → 0.765) with the false-positive rate
  still **0.00 across every stratum** (below ~0.65 a negative starts to flag). Docs/UI updated to match.
- **`/api/check` is now asynchronous** — `POST` validates uploads synchronously (400/413 fail fast) then
  returns **202 + `job_id`**; matching + OpenAlex run in a bounded background worker (`ThreadPoolExecutor`,
  4 workers) so the network call never blocks the request. New **`GET /api/check/{job_id}`** returns
  `queued|running|done|error` (+ the result when done). Adds **content-hash result caching** (idempotent
  re-submits return instantly) and a thread-safe embedding-model singleton. The frontend now submits + polls.
- **UI redesign → state-of-the-art light design system.** Rebuilt `index.html` into a SaaS
  dashboard shell (sidebar workflow nav, SVG icon set, contextual sticky topbar); rewrote
  `css/styles.css` (design tokens, restyled every component); rewrote `sources.js` & `citations.js`
  to clean light-theme classes (removed hardcoded dark inline colors).
- **Legacy README de-hyped** — removed "100% accuracy / ZERO false positives / prosecutable / measurably
  superior / Full (Idea Triplets)"; benchmark relabelled an N=2 illustrative legacy smoke test; added a pivot banner.

### Known / not yet done (see [`ROADMAP.md`](ROADMAP.md) / [`TODO.md`](TODO.md))
- For any multi-user/public deployment: auth + rate limiting; move OpenAlex search off the request path (worker/job model).
- Add Crossref/arXiv corpora; expand the eval set; finer (sliding-window) paraphrase localization.
- AI-generated-text detection intentionally deferred until it can be shipped calibrated + hedged.

---
_Releases will be tagged here once a versioned build of the Originality Checker is cut._
