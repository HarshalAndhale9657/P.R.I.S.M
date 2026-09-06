# Decision Log (ADRs)

Lightweight [Architecture Decision Records](https://adr.github.io/). Each entry is the **memory of *why*** —
newest at the bottom. Status: `Proposed` · `Accepted` · `Superseded`.

> When you make a real decision, append an ADR here. Don't rewrite history; supersede instead.

---

## ADR-0001 — Pivot to source-attribution plagiarism detection
**Status:** Accepted (2026-08-21)
**Context:** PRISM was built as a stylometric *authorship* tool. The owner clarified the real goal:
find plagiarism in a paper — *what* is copied, *where* it is, and *from which source*. Internal
audits also show the authorship engine is near-noise (boundary F1 ≈ 0.40; features add ~+0.02 over a
generic embedding that tracks topic, not authorship).
**Decision:** Make **source-attribution plagiarism detection** the product core. Authorship/"how many
authors" is no longer the spine.
**Consequences:** New matching-centric pipeline; new report (highlighted passages + linked sources +
overall %); repositioning away from "integrity verdict."

## ADR-0002 — Retire the stylometry/authorship-clustering engine as the spine
**Status:** Accepted (2026-08-21)
**Context:** Source-matching compares *every* passage against a corpus regardless of writing style.
An authorship pre-filter adds nothing, and (being near-noise) would *hurt recall* — it'd skip
plagiarism that matches the student's own style.
**Decision:** Drop authorship clustering + the integrity verdict. **Salvage:** PDF parsing/segmentation;
**repurpose `burstiness` → the AI-text signal**; keep **citation forensics** as a bonus panel.
**Consequences:** HDBSCAN/clustering removed from the product path; existing dead "v3" clustering
modules become deletable (see PROJECT_BRIEF §7.2).

## ADR-0003 — Corpora = user-uploaded references + open-access academic DBs
**Status:** Accepted (2026-08-21)
**Context:** "Attribute to a source" requires something to compare against. Options weighed: open web
(needs paid index), private repo (needs storage), academic DBs (free APIs), user uploads (local).
**Decision:** Support **(a) user-uploaded reference set** (local, deterministic, full-text) and
**(b) open-access academic DBs** (OpenAlex, Semantic Scholar, arXiv, Crossref). Defer open-web and
private-repo corpora.
**Consequences:** Verbatim matching is most reliable against user uploads (full text); academic-DB
matching leans on abstracts + OA text (semantic/paraphrase). Drives the phasing.

## ADR-0004 — Primary user = student self-check (non-accusatory)
**Status:** Accepted (2026-08-21)
**Context:** Accusation tools that emit verdicts on a weak signal cause real harm (false positives on
ESL/technical writers; litigation; university bans).
**Decision:** First user is the **author self-checking their own draft**. Framing is a
**non-accusatory "originality report"** — no verdicts, calibrated + abstaining.
**Consequences:** UI/report language avoids "plagiarised/guilty"; sidesteps FERPA / EU AI Act
high-risk decisioning; simplifies compliance for the MVP.

## ADR-0005 — Detection scope = verbatim + paraphrase + translated + AI-generated
**Status:** Accepted (2026-08-21)
**Context:** Owner wants all four kinds caught.
**Decision:** Target all four. Methods: verbatim → n-gram fingerprinting; paraphrase → local
sentence embeddings; translated → multilingual embeddings; AI-generated → separate calibrated,
hedged classifier (never a verdict).
**Consequences:** Adds a `sentence-transformers` dependency (local MiniLM + multilingual MiniLM).
Sequenced across phases (see ROADMAP).

## ADR-0006 — Phase 1 build order
**Status:** Accepted (2026-08-21)
**Context:** Two viable starting points for the MVP.
**Options:** (A) **user-uploaded references first** — fully offline, deterministic, reliable verbatim +
span highlighting; (B) **academic-DB search first** — works without user-supplied sources but matches
mostly against abstracts.
**Decision:** (A) references-first. Shipped: `plagiarism_matcher` + `POST /api/check` + the new checker UI.
**Consequences:** Built the reusable matcher/segmentation/report-UI core; Phase 2 (academic DBs) now
plugs a second corpus into the same matcher. `sentence-transformers` added as a dependency.

## ADR-0007 — Reuse local MiniLM (paraphrase-multilingual) for paraphrase matching
**Status:** Accepted (2026-08-21)
**Context:** Paraphrase detection needs semantic similarity offline; a multilingual model also sets up
Phase 3 (translated).
**Decision:** Reuse `services/local_embeddings.py` (`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim).
Paraphrase threshold **0.75** (empirically: true paraphrase ≈ 0.81 vs unrelated ≈ 0.06–0.16).
**Consequences:** Adds torch/sentence-transformers (~heavy). Matcher degrades to verbatim-only if the
model can't load, so the feature never hard-fails.

## ADR-0008 — OpenAlex as the Phase 2 academic corpus
**Status:** Accepted (2026-08-21)
**Context:** Probed the free academic APIs: OpenAlex 200, Crossref 200, arXiv 301 (redirect),
Semantic Scholar 429 (needs a key). Need abstracts + metadata to generate candidate sources.
**Decision:** Use **OpenAlex** first — free, no key, returns abstracts (inverted index) + URLs inline.
Retrieval is opt-in (`use_academic`), synchronous with timeouts, and degrades to a warning on failure.
**Consequences:** Academic matches are mostly semantic/paraphrase against **abstracts** (not full text).
Crossref/arXiv are easy follow-ups; the request-path network call should move to a worker in Phase 2b.

## ADR-0009 — Translated detection via language-pair re-classification (not a new matcher)
**Status:** Accepted (2026-08-21)
**Context:** The paraphrase model (`paraphrase-multilingual-MiniLM`) already scores true translations very
high (measured EN↔FR ≈ 0.94; unrelated ≈ 0.09). So translated plagiarism is already *found* — it just
needs to be *labelled*.
**Decision:** Detect the language of each matched passage + source sentence with **langdetect** (seeded
for determinism); if they differ, re-classify the paraphrase match as `translated` and surface the
language pair. No separate cross-lingual matcher.
**Consequences:** Adds a tiny `langdetect` dependency; degrades to "paraphrase" if it's unavailable or the
text is too short to identify. AI-generated-text detection (the 4th type) is deliberately deferred until
it can be shipped calibrated + hedged (a naive detector would undermine trust).

## ADR-0010 — Honesty & safety pass (README de-hype, security baseline, dead-code removal)
**Status:** Accepted (2026-08-21)
**Context:** With the checker now a real product, the analysis's "NOW" items became worth doing: the legacy
README overclaimed ("100% accuracy / zero FP / prosecutable"), `/api/check` had `CORS *`+credentials and no
paper size cap, and ~1000 LOC of dead "v3" modules invited confusion.
**Decision:** (1) De-hype the legacy README (remove false claims; relabel the N=2 benchmark; add a pivot
banner) — do **not** rewrite it fully; it's legacy. (2) Security baseline on the current product: explicit
CORS allow-list via `PRISM_ALLOWED_ORIGINS`; a 20 MB upload cap enforced in `_read_pdf_bytes` (covers all
read endpoints) + `/api/upload`; generic client errors for `/api/check` + `/api/upload`. (3) Delete the 8
dead modules (verified unreferenced by grep + a read-only audit agent).
**Consequences:** Auth/rate-limiting and moving OpenAlex off the request path remain for a multi-user
deployment; raw `str(e)` in the *legacy* endpoints is a noted follow-up. All eval/smoke/E2E stayed green.

## ADR-0011 — Async job model for `/api/check` (in-process worker, not Redis)
**Status:** Accepted (2026-08-21)
**Context:** OpenAlex search ran synchronously on the request path (30–120s worst case, races the proxy
timeout). It needed to move off the request path — but this is a single-process, self-check tool, so
standing up Redis + Celery/RQ is overkill right now.
**Decision:** `POST /api/check` validates + reads uploads synchronously (fast-fail 400/413), then submits
the heavy work (parse → gather sources → OpenAlex → match) to a **bounded in-process `ThreadPoolExecutor`
(4 workers)** and returns **`202 + job_id`**. **`GET /api/check/{job_id}`** polls status/result. In-memory
job store (bounded ~200) + **content-hash result cache** (idempotent re-submits). Made the embedding
singleton thread-safe (double-checked locking) since matching now runs in worker threads.
**Consequences:** No external dependency; fully testable (TestClient submit→poll); network off the request
path. Jobs don't survive restart and aren't shared across processes — switch to **Redis + a real queue**
(RQ/arq/Celery) to scale to multiple workers/instances. Per-provider circuit breakers remain a TODO.

## ADR-0012 — Academic corpora: OpenAlex + arXiv; Crossref dropped
**Status:** Accepted (2026-08-21)
**Context:** To match against academic literature we need candidate documents that carry **abstract text**
(the matcher compares text). Probed the free providers: OpenAlex (abstracts via inverted index ✅),
arXiv (full summaries ✅), Crossref (200 OK but **0/5 records had abstracts** — publishers rarely deposit
them), Semantic Scholar (429 without a key).
**Decision:** Use **OpenAlex + arXiv**, run **concurrently** in `academic_corpus.search()` (a small
`ThreadPoolExecutor`), merge + de-duplicate by normalised title (prefer the longer abstract). **Do not**
add Crossref as a content corpus — it yields almost no matchable text; it stays a candidate for a future
metadata/verification feature. Semantic Scholar deferred (needs a key).
**Consequences:** Broader coverage (arXiv is strong for CS/ML). arXiv is slower per call, so it's capped to
the first 4 queries. Each provider degrades to a warning independently; the search never raises.

## ADR-0013 — Expanded eval set + paraphrase threshold recalibration 0.75 → 0.66
**Status:** Accepted (2026-08-21)
**Context:** The original eval (12 cases) passed but was small and hid failure modes. Expanded to **32
labelled cases** in `scripts/eval_data.json`: positives tagged by **type × difficulty** and negatives by
**stratum** (same-topic, boilerplate, **ESL**, shared-terminology, unrelated), with per-group recall and
**per-stratum FPR** reporting + gates. The richer eval revealed the matcher missed **all** medium/hard
paraphrases at threshold 0.75 while having **zero** false positives (huge headroom).
**Decision:** A threshold sweep over the benchmark found **0.66** is the best operating point — recall
0.65 → 0.765, FPR still **0.00 on every stratum** (at ≤0.64 a negative begins to flag). Recalibrated the
default paraphrase threshold **0.75 → 0.66** (supersedes the value in ADR-0007). Gates: overall recall ≥ 0.70,
FPR ≤ 0.15, and per-stratum FPR ≤ 0.34.
**Consequences:** Better paraphrase recall at no measured false-positive cost on the benchmark. Hard
paraphrases (heavy rewrites) are still missed — surfaced honestly in the report; addressing them needs
better features / sliding windows, not a lower threshold (which would start flagging originals). Note the
benchmark is synthetic/self-authored — a real held-out corpus remains a later step.

## ADR-0014 — Product direction: honest "publication-readiness / integrity coach" (+ hard ethical boundary)
**Status:** Accepted (2026-08-21)
**Context:** Owner goal = a real product people pay for. Target user = an **author preparing a manuscript for
IEEE / arXiv / a journal** (all disciplines; ESL/early-career especially). The job: before submitting, know
the **AI %**, the **similarity/plagiarism** and **where from**, and **fix each issue** so the paper clears the
publisher's integrity gate (iThenticate/Crossref Similarity + AI checks) and gets published. Model = freemium.
**Decision:** Build the **honest integrity coach → publication-ready** product:
detect (plagiarism + attribution + a calibrated AI-risk signal) → **triage each flag by remediation type**
(un-quoted quotation, missing citation, common-phrase/boilerplate, self-plagiarism, too-close paraphrase,
AI-heavy) → **coach the honest fix** (quote+cite, add reference, disclose self-reuse/AI use per journal
policy, or rewrite from the author's own understanding with the source shown) → an "estimated submission
risk" report + re-check. Corpus phased (uploads + arXiv/OpenAlex now; paid web layer later). It reduces
risk and mirrors the gate — it does **not** promise a guaranteed pass (their tools are proprietary).
**HARD BOUNDARY (non-negotiable):** we will **NOT** build detection-evasion features — no auto-rewriting
copied text to lower a similarity score, and no "AI humanizer" to defeat AI detectors. Their purpose is to
deceive a publisher's integrity check = facilitating academic misconduct; it also destroys the honest brand
and is legally/commercially toxic. Rewriting is only ever offered as author‑driven, source‑visible,
own‑understanding revision — never as one‑click "beat the detector."
**Consequences:** The coach achieves the legitimate goal (papers pass because they become genuinely clean).
Requires a new **AI‑risk module** (calibrated + hedged) and a **flag‑triage + coaching** layer on top of the
existing matcher. Supersedes the narrower "student self‑check" framing (ADR‑0004) — same ethics, wider user.

## ADR-0015 — Invest in the core ML (real benchmark + best pretrained + re-architecture), timeboxed to ~3 months
**Status:** Accepted (2026-08-21)
**Context:** The honesty check exposed that the "detection moat" is unproven — the P=1.00/FPR=0.00 number is
from a **32-case benchmark I self-authored** (synthetic, self-graded), and recall on hard paraphrases is 0/3.
So the plan cannot be "wrap a coaching layer on the existing matcher"; detection quality must be genuinely
built and honestly measured. Owner chose: **keep ~3 months** (timeboxed), **best pretrained models + real
benchmark + better retrieval (NO custom training)**, **build the AI detector now but gate it on honesty**, and
**re-architect into a real ML pipeline**.
**Decision:**
1. **Real benchmark first** — validate the ACTUAL pipeline on THIRD-PARTY labelled data (PAN plagiarism
   corpora + assembled real paper pairs; public human-vs-AI sets like RAID/HC3/M4 for the AI detector). This
   replaces the self-graded eval as the source of truth; report precision/recall/**FPR per stratum incl. ESL**.
2. **Detection lift, no training** — upgrade the bi-encoder (e.g. `bge-base`/`gte-base`/`all-mpnet` via ONNX)
   + add a **cross-encoder reranker** on top candidates to catch hard paraphrases; expand retrieval/corpus
   (OpenAlex + arXiv + Semantic Scholar + OA full-text via Unpaywall/PMC). Re-measure on the real benchmark.
3. **AI detector now, honesty-gated** — a calibrated Low/Elevated/High + hard **Inconclusive** signal from
   perplexity (small LM) + burstiness + an open pretrained detector, fused + calibrated; **ship only if it
   clears a strict ESL-false-positive bar** on real ESL human text, else fall back to disclosure-coach only.
   OpenAI is never the detector.
4. **Re-architect** into clean pluggable stages: `parse → retrieve → match → rerank → ai_risk → triage →
   coach → report`, with a first-class **eval/model harness** and a `models/` cache/version layer.
**Consequences:** Front-loads ML + benchmark + refactor; compresses the SaaS plumbing (Supabase/Razorpay are
fast). Slightly heavier models mean we likely **keep PyTorch** for the cross-encoder/AI models and size up to a
~8GB VPS (~€8/mo) rather than the "drop torch, €5 box" move — still bootstrap-cheap. Aggressive for one person
in 3 months; "strong-enough" = ship what clears the honesty bar, defer the rest (web-corpus, batch). Revises
[`LAUNCH_PLAN.md`](LAUNCH_PLAN.md) accordingly.

## ADR-0016 — Core-ML specifics: pretrained-first + selective fine-tune, plagiarism-first, free-GPU, public datasets, NO PAN
**Status:** Accepted (2026-08-30) — **amends ADR-0015** (owner Q&A).
**Context:** ADR-0015 said "no custom training." Owner reopened that and gave concrete direction on model, data,
compute, and focus. Also: the on-disk `research/datasets/pan/` (14,473 docs) is **PAN 2023 *style-change /
multi-author* data** (labels: `is_multi_author / num_authors / boundaries`) — the *authorship* task we pivoted
away from. It has **no document→source pairs and no plagiarism spans**, so it cannot benchmark or train the
source-attribution matcher. Owner also directed: **do not use PAN at all** as our dataset.
**Decision (4 answers):**
1. **Training posture = pretrained-first, fine-tune selectively.** Use the best off-the-shelf models now
   (amends 0015's "no training"). The **only** sanctioned fine-tune candidate for v1 is the **paraphrase
   cross-encoder reranker**, and it ships **only if it beats the pretrained cross-encoder on our real eval**.
   No from-scratch training. The AI detector's trainable head is deferred (it's phase-2 focus, see #2).
2. **Focus = plagiarism / source-matching FIRST.** All model effort → retrieval (bi-encoder) → paraphrase
   similarity → **cross-encoder rerank**. The **AI-text detector is deferred** behind this (still honesty-gated
   per ADR-0015 when it comes).
3. **Compute = free cloud GPU (Colab/Kaggle).** Any fine-tune is a small/LoRA notebook job on a T4/P100;
   **inference stays CPU (ONNX)** on the VPS. No paid GPU, no local GPU assumed.
4. **Data = ready-made public datasets ONLY** (owner did **not** opt into build-our-own-from-papers, and did
   **not** require per-item approval). For plagiarism/paraphrase: **PAWS, MRPC, STS-B, QQP** (+ **PAWS-X** for
   multilingual/translated). These double as the **real third-party eval**, replacing **both** PAN *and* the
   self-authored 32-case set as the source of truth. (Human-vs-AI sets RAID/HC3/M4 are reserved for the later
   AI-detector phase.) License-clear only; **no PAN**.
**Consequences:** W2's benchmark = a loader over public paraphrase sets (not PAN). "Detection lift" (ADR-0015
§2) is now *pretrained bi-encoder + a cross-encoder that may be lightly fine-tuned on PAWS/MRPC*. The moat stays
the **product/coach + honesty**, with a modest ML edge from a tuned reranker if it earns its place on the eval.
Keeps everything bootstrap-cheap (free GPU, CPU inference). Revises [`LAUNCH_PLAN.md`](LAUNCH_PLAN.md) §3/§5/§9.

## ADR-0017 — Confidence band ("review" vs "confident") + synthetic set demoted to a smoke test
**Status:** Accepted (2026-08-31) — owner Q&A, following the W2-W4b measurements.
**Context:** Measuring the matcher's paraphrase pillar on four *public* datasets (STS-B 1221, MRPC 408,
QQP 3000, PAWS 2000) produced two findings that change how we report and how we gate:
1. **The live threshold 0.66 is too low.** It was fitted to the self-authored 32-case set. On real
   same-topic-but-independently-written negatives — our actual ESL / boilerplate / shared-terminology risk —
   FPR at 0.66 is **0.234 (STS-B) / 0.451 (QQP) / 0.643 (MRPC)**. At ~0.78-0.82 it roughly halves
   (STS-B 0.097@0.78, 0.063@0.82) for ~10-15pp recall. The **separation gap** (mean positive − mean negative)
   confirms the model itself is fine where the task is well posed: STS-B **0.460**, QQP 0.303, MRPC 0.141.
2. **The synthetic 32-case set is not a quality instrument.** Its FPR is **0.000 at every threshold 0.66-0.82**
   — its negatives never approach the decision boundary — so its "precision 1.00 / FPR 0.00" is an artifact of
   easy negatives. Raising the threshold on it only *loses* recall (0.765 → 0.647) while its FPR signal stays flat.
   (Separately, **PAWS's gap is 0.007** — mean pos 0.981 vs neg 0.974 — so no threshold can ever separate it;
   that is a representational limit of bi-encoders on word-order/role swaps, and PAWS is also partly
   *task-mismatched* for us: its pairs always share an origin, so it tests semantic equivalence, whereas
   plagiarism asks about **derivation**. STS-B/QQP/MRPC are the product-relevant sets.)
**Decision:**
1. **Ship an explicit inconclusive band instead of moving one cutoff.** `paraphrase_threshold=0.66` becomes the
   *reporting floor*; new `confident_threshold=0.78` is the *confidence* cutoff. Every match carries
   `confidence: "confident" | "review"`, and `overall` gains `confident_pct` / `review_pct` / `review_count`.
   Verbatim is always `confident`. This is **additive**: nothing previously detected is dropped, borderline
   semantic hits are simply labelled honestly. It implements the standing guardrail — *"prefer a triage band +
   an explicit inconclusive state over a false clean"* — and avoids presenting a 0.70-cosine hit as a confirmed copy.
2. **Demote `scripts/eval_matcher.py` to a smoke test.** It stays in CI as a fast, offline, download-free
   tripwire ("does the matcher still run and still catch obvious copies?"), with loosened gates
   (MIN_RECALL 0.70 → 0.55) and a banner saying its FPR is uninformative. **The quality gate is
   `python -m eval.run_pairs`** over the public datasets.
**Consequences:** The UI/report should render the review band distinctly (not as confirmed plagiarism) — a
frontend follow-up. `similarity_pct` keeps its old meaning (all matches) for API compatibility; consumers that
want the strict number use `confident_pct`. **Caveat carried forward:** these are *pairwise* calibrations, but the
matcher takes a **max over many source sentences**, which biases the top score upward (multiple comparisons), so
0.78 is a **lower bound** for production — revisit after the cross-encoder rerank lands.

## ADR-0018 — Delete the legacy stylometric authorship engine
**Status:** Accepted (2026-09-06)
**Context:** After the pivot (ADR-0001/0002) the authorship engine — spaCy stylometry → HDBSCAN clustering →
GPT reasoning → citation forensics → source tracer → report generator, seven endpoints, `authorship.html` and
seven frontend modules — was "retired as the spine" but still wired into `main.py`. It instantiated at import,
ran CPU-bound work synchronously inside `async` handlers (blocking every concurrent request), pulled spaCy /
HDBSCAN / ruptures / nltk / openai into the image, doubled the attack surface, and its README described an
architecture (`unstructured` dual-pass parsing) that never actually ran because the dependency was absent.
Its measured detection quality was near-noise (F1 ≈ 0.40, `research/HONEST_AUDIT.md`).
**Decision:** Delete it — backend services, prompts, endpoints, scripts, legacy frontend, and its dependencies.
Keep the research record (`research/`, `research/legacy_prism_diagnostic.md`) as history. Nothing is lost:
every file remains in git history at `b095257` and earlier (SHAs changed on 2026-09-06 when the PAN corpus was purged from history — see PROGRESS).
**Consequences:** `requirements.txt` drops to 12 direct dependencies; the image no longer needs a compiler; the
API surface is exactly `/api/v1/check`, `/api/v1/check/{id}`, `/health`, `/health/ready`. Anyone who wants the
old engine checks out the tag/commit. The PDF parser it owned is replaced by a checker-specific one (ADR-0019).

## ADR-0019 — Backend re-architecture: `app/` + `worker/` + pipeline-owned parsing; bounded, ephemeral, observable
**Status:** Accepted (2026-09-06)
**Context:** `main.py` (872 lines) mixed routing, an in-process job queue with an *unbounded* backlog, document
extraction and the legacy engine. Every queued check held up to ~520 MB of raw upload in RAM with no aggregate
cap and no TTL — a one-line memory DoS, and a contradiction of the "ephemeral-by-default" promise. Parsing
lived outside the pipeline (so the eval harness could never exercise the real PDF path) and used the legacy
parser's policy: every paragraph under 80 characters was silently dropped — for a plagiarism checker, a
passage never checked. There was no auth, no rate limit, no response schema, no request correlation, and
`/` said "ok" before the model existed.
**Decision:**
1. **Composition root** `app/factory.py::create_app(settings)`; `main.py` is a two-line shim. All operational
   knobs in `app/settings.py` (pydantic-settings, `PRISM_*`), nothing else reads the environment.
2. **Contract:** Pydantic response models for every endpoint (`app/schemas.py`); the API is versioned at
   `/api/v1`; results carry an `engine` block (version, model, both thresholds, rerank, coverage statement) so
   reports and UIs describe the method from data, not from copy that goes stale.
3. **Bounded worker** (`worker/`): `BoundedExecutor` refuses with **503 + Retry-After** when the pending queue
   is full; `InMemoryJobStore` and `TTLCache` purge by **time** as well as count; an aggregate per-request byte
   cap plus a `Content-Length` pre-check. Worst-case upload memory = `max_pending_jobs × max_request_bytes`,
   a number, not a hope. `JobStore` is a Protocol so W7's Postgres store is a new class, not surgery.
4. **Per-IP rate limiting** on submission (fixed window, in-process; the key becomes the user at W7).
5. **Parse is a pipeline stage** (`ParseStage`) backed by `services/document_parser.py`: keeps every block with
   real words, strips repeated running headers/footers and page numbers, **excludes and reports** the reference
   list, re-joins hyphenated line breaks, enforces page and character caps, handles encrypted/corrupt PDFs.
6. **Observability:** `X-Request-ID` in/out, `request_id`/`job_id` on every log line via contextvars, optional
   JSON logs, per-stage `timings_ms` in every result, `/health` (snapshot) and `/health/ready` (503 until the
   model is warm), optional Sentry.
7. **Quality gates in CI:** ruff blocking, coverage floor 80%, Docker build + readiness smoke, browser E2E,
   and the public-dataset benchmark gate (ADR-0020).
**Consequences:** 102 offline tests (was 57). The matcher, modelhub and eval packages are untouched in spirit —
this was a refactor of the edges, not the core. Breaking change for any client of the old `/api/check` path.
**Not done (deliberately):** authentication and persistence (W7), a distributed rate limiter (unnecessary on
one box), OCR for scanned PDFs.

## ADR-0020 — Honest regression gates on public data, at the confident cutoff; source-sentence budgeting by relevance
**Status:** Accepted (2026-09-06)
**Context:** ADR-0017 declared `python -m eval.run_pairs` "the quality gate", but it was not in CI, and its
provisional thresholds (`FPR ≤ 0.15` at 0.66) would have failed on every product-relevant dataset (measured
FPR at 0.66: STS-B 0.234, QQP 0.451, MRPC 0.643). A gate nobody runs, set at a level nothing passes, is
documentation, not a gate. Separately, the matcher truncated large reference sets to the *first* 6000 source
sentences in upload order — with 25 references the last ones were never compared, and only a warning said so.
**Decision:**
1. Gates live in `eval/gates.json` as data, **per dataset**, evaluated at the **confident cutoff (0.78)** — the
   score the product presents as a confirmed match — and set from the measured 2026-08-30 baseline with a
   small margin (recall −0.04, FPR +0.02). They are **regression tripwires, not targets**, and the file says so
   beside each baseline. PAWS is reported but not gated (its distributions coincide; it tests equivalence, not
   derivation — ADR-0017). CI runs the gate on STS-B, MRPC and QQP (validation splits; QQP sampled to 3000)
   on every push.
2. When source sentences exceed the embedding budget, keep the **top-N by TF-IDF similarity to the document
   across all sources** instead of the first N. Model-free and cheap; the warning states exactly what was
   searched and that paraphrases sharing almost no words may be missed.
**Consequences:** A model or threshold change that regresses a public set now fails the build with the number
that regressed. Tightening a gate is a deliberate act after a measured improvement. The synthetic 32-case set
remains a smoke tripwire only.

## ADR-0021 — Retrieval depth (W4b): Semantic Scholar as a keyed provider; open-access full text via OA links
**Status:** Accepted (2026-09-06)
**Context:** Academic sources were abstracts only (OpenAlex inverted index, arXiv summaries), so a copied
paragraph from a paper could at best appear as a *paraphrase-shaped* match against its abstract; verbatim
detection against the literature was impossible by construction. LAUNCH_PLAN §5.4 asked for Semantic Scholar
plus Unpaywall/arXiv/PMC full text. Probing: Semantic Scholar returns **429 without an API key**; OpenAlex
already exposes Unpaywall-derived OA locations (`best_oa_location.pdf_url`, `open_access.oa_url`); arXiv has a
PDF for every record.
**Decision:**
1. **Semantic Scholar is a third provider, enabled only when `PRISM_S2_API_KEY` is set.** Unauthenticated
   calls would fail predictably and pollute warnings; a key is free.
2. **Full text comes from the OA PDF links the providers already return** (arXiv `pdf_url`, OpenAlex
   `best_oa_location.pdf_url` / `oa_url`, S2 `openAccessPdf.url`). **Unpaywall is not called** — OpenAlex
   ingests it — and there is no separate PMC client: PMC PDFs arrive through those same OA locations.
3. `services/fulltext.py` treats every download as hostile input: http(s) only, loopback/private/link-local
   hosts refused (also after redirects), streamed with a hard byte cap (15 MiB), first bytes must be `%PDF`
   regardless of Content-Type, parsed by our own parser under its page/char caps, results *and* failures cached
   (1 h) so a popular paper is fetched once and a dead link is not hammered.
4. Budget: at most `academic_fulltext_max_docs` (8) downloads per check, chosen by **lexical overlap between
   the document and each candidate's abstract** (cheap, model-free), fetched concurrently, ≤2 link attempts each.
5. **Honesty in the data model:** `SourceDoc.kind ∈ {fulltext, abstract}` flows into `sources`, `per_source`,
   the UI ("abstract only" tag) and the report's coverage statement ("N with full text, M abstract-only").
   A user can always see whether a source was compared in full or only by its abstract.
**Consequences:** Verbatim matches against open-access literature are now possible. Each check may download up
to 8 public PDFs (nothing of the user's is sent — only the provider queries, as before); latency rises by the
download time, bounded by the 15 s per-fetch timeout and concurrency of 4. Full-text sources can be long, so
the matcher's relevance-based budgeting (ADR-0020) matters more, not less.

## ADR-0022 — Flag triage: deterministic remediation types, and the coach card as the primary view
**Status:** Accepted (2026-09-06)
**Context:** Detection alone tells an author *that* a passage matched, which is exactly the anxiety-producing,
non-actionable output the product exists to replace (LAUNCH_PLAN §13: "triage + honest coaching IS the product").
The pipeline had a `TriageStage` skeleton since W1. The question was what it may use as evidence.
**Decision:**
1. **Rules, not a model.** Triage is computed from four auditable signals — quotation marks immediately around the
   span, citation markers in the containing paragraph (numeric `[12]`, author-year `(Smith et al., 2020)`,
   narrative `Smith (2020)`, superscript), the ADR-0017 confidence band, and how many distinct sources contain the
   same verbatim text — producing one of eight types with a priority (1 = fix before submitting … 5 = attributed,
   nothing to do). Deterministic means reproducible, explainable to a user, and testable per rule; an LLM here
   would be unaccountable for a judgement that shapes what the author changes in their manuscript.
2. **Every type ships with plain-language `what` + `fix` text**, and a **CI-enforced test asserts none of that text
   suggests evasion** (no "lower the score", "beat the checker", "humanize"). The fix is always quote+cite, add a
   reference, or restate in your own words *keeping* the citation (ADR-0014).
3. **The coach card is the primary detail view** — what this is, the honest fix, and the signals it was derived
   from — shown *above* the side-by-side evidence, with a prioritised "What to fix" panel above the results and the
   same content in the downloadable report.
4. **Labels describe the text, never the person:** "Word-for-word, not cited", not "Copied/plagiarised". Every
   card lists the signals it used, so a wrong call is visibly wrong rather than mysterious.
5. **Limits are stated in the product, not just the code:** citation detection is pattern-based and only looks at
   the containing paragraph (a citation elsewhere in the paper is not seen), and self-reuse cannot be detected
   without the author's prior work. That sentence ships in the UI panel and the report.
**Consequences:** `TriageStage` is live after `LocalizeStage` (it needs paragraph context) and fails soft — an
internal error leaves matches un-triaged with a warning rather than failing the check. Each match gains `triage`;
the result gains `triage_summary` (counts, prioritised action items, method note); both are in the Pydantic
contract. Next: W9 replaces the *static* `fix` string with per-flag LLM prose, constrained to this same type and
the shown source, with a matcher post-filter — the rules stay the backbone, the LLM only phrases them.

## ADR-0023 — Cache sentence embeddings by (model, text); the re-check loop is 6× faster
**Status:** Accepted (2026-09-06)
**Context:** After open-access full text landed (ADR-0021) a real check took **50 s**, and the W4b measurement
showed the cost was *not* the PDF downloads. Benchmarked directly on this CPU: **6 000 source sentences take
77–93 s** to embed (batch 64 fastest; 128/256 worse). Embedding is the product's dominant cost, and the same
sentences are embedded over and over — most importantly in the **re-check after edits**, which is the core
product loop (W10: "before/after re-check") and where the manuscript changes but the sources are byte-identical.
**Decision:** A process-wide LRU of sentence embeddings keyed by **`(model_key, sha1(text))`**.
1. **Keyed by text, not by source.** The relevance budget (ADR-0020) selects a *different subset* of a source's
   sentences for each manuscript, so a per-source key would miss on every new document. Text keys also pick up
   repeated boilerplate and sources shared across manuscripts.
2. **Source sentences only.** The manuscript's own sentences change every check; caching them would fill the
   cache with single-use entries and evict the useful ones.
3. **`model_key` namespaces every entry**, so swapping the bi-encoder (W3/W5) can never reuse stale vectors.
4. **Bounded in entries, not bytes** (default 50 000 ≈ 75 MB at 384 dims), so the ceiling does not silently move
   when the model's dimensionality changes. `PRISM_EMBEDDING_CACHE_ENTRIES=0` disables it.
5. **The cache can never break a check:** any failure in the cache path logs and degrades to a plain embed, and a
   test asserts that. Vectors are stored read-only so a caller cannot corrupt a shared entry in place.
6. **Hit rate is exposed on `/health`** — an operator tuning the box needs to see it, not guess.
**Measured (this machine, 1 800 source sentences over 2 papers, manuscript edited between runs):**
first check **39.3 s** → re-check **6.6 s** = **6.0×**, 32.8 s saved; 1 800 hits / 0 misses on the second pass.
A cold first check is unchanged — this buys repeats, and says so.
**Consequences:** Memory grows to the configured ceiling on a busy box; that is the trade being made deliberately
and it is visible on `/health`. The remaining first-check cost is still real, so the W6 levers
(`PRISM_MAX_SOURCE_SENTENCES`, batch size on the actual VPS) stay open. **Found while building this:** the class
defines `__len__`, so an empty cache is falsy and `cache = cache or get_cache()` silently discarded an injected
cache — caught by the tests, fixed with `is None`.

## ADR-0024 — Measure the max-over-sources effect, and scale the confidence cutoff with corpus size
**Status:** Accepted (2026-09-06)
**Context:** Every number PRISM has ever published is **pairwise** — one candidate sentence against one source
sentence. The matcher does not work that way: for each document sentence it takes the **maximum similarity over
every source sentence**. With N sources that is N chances to score high, so the top score drifts upward with N.
ADR-0017 flagged this and called 0.78 a "lower bound", but the effect was never measured. `eval/corpus_scale.py`
+ `eval/run_corpus.py` measure it: build a distractor corpus of N sentences, ask how often a query sentence whose
paraphrase is **absent** still gets flagged (that flag rate *is* the FPR), and sweep N.
**Measured** (250 negative / 250 positive queries, bi-encoder; `eval/results/corpus_*.json`):

| corpus | mean top score, no true match (QQP) | p95 | FPR @0.78 |
|---|---|---|---|
| 100 | 0.343 | 0.505 | 0.000 |
| 1 000 | 0.508 | 0.763 | 0.048 |
| 3 000 | 0.575 | 0.882 | 0.108 |
| ~5 000 | 0.606 | 0.903 | — |

The drift is ≈**0.16 per decade of corpus size**, reproduced independently on QQP and STS-B. At 3 000 sentences
the 95th percentile of "best match for unrelated text" is **0.88 — above the 0.78 confident cutoff**. The
threshold that holds FPR ≤5% moves from 0.66 (N=100) to 0.90 (N=3 000) on QQP. A single fixed cutoff therefore
means something materially different for a 3-reference check than for a 6 000-sentence academic corpus — and W4b
full text puts real checks squarely in the latter range.
**Decision:** The confidence cutoff scales with the number of source sentences actually compared:
`confident(N) = clamp(base + k·log10(N / pivot), base, ceiling)` with `k=0.06`, `pivot=500`, `ceiling=0.92`
(`PRISM_CONFIDENCE_*`, `PRISM_CONFIDENCE_SCALING=false` restores a fixed cutoff).
* **`k = 0.06` is deliberately well below the measured drift.** This counteracts part of the effect rather than
  modelling it; the measurement is of the paraphrase pillar in isolation (no verbatim, rerank or relevance
  budgeting) on two datasets. A calibrated hedge, not a law.
* **The risk direction is safe.** Raising the cutoff can only move a match `confident → review`. The reporting
  floor is unchanged and every match is still shown, so the failure mode is "we asked you to check something we
  were unsure of" — never a false clean (ADR-0017's standing guardrail).
* **It is visible, not silent.** The result carries `confident_threshold` (applied), `confident_threshold_base`
  and `corpus_sentences`; a warning states the raise; the report footer explains *why* in plain language.
* The rerank stage re-decides the band against the **same** applied cutoff, so the two can never disagree.
**Consequences:** Large-corpus checks now yield more `review` and fewer `confident` labels — intended. The
measurement also makes the retrieval-quality argument concrete: the honest way to recover that recall is a better
reranker (W5) or tighter retrieval, not a lower bar. **Caveat carried forward:** the probe's distractors are
*unrelated* sentences, whereas production sources were *retrieved by similarity* and are topically close — so the
real-world effect is likely **larger**, not smaller. Re-measure against the full matcher once rerank is default-on.

## ADR-0025 — Relevance, not size, is what inflates a match score; and ADR-0024's probe was contaminated
**Status:** Accepted (2026-09-06)
**Context:** ADR-0024 shipped a confidence cutoff that scales with the number of source sentences, and carried
one caveat forward on purpose: its distractors were *unrelated* sentences, while production sources are
**retrieved by similarity** and therefore topically close, so "the real effect is likely larger". This ADR
re-measures with that fixed — and, in doing so, found a second problem nobody had flagged: the probe's central
guarantee, *no true match is in the corpus*, was only ever enforced **pairwise**. A query's labelled partner was
excluded; an unlabelled duplicate of it sitting in some other pair was not.

**Method** (`eval/corpus_scale.py`, four new knobs on `eval/run_corpus.py`):
* `--distractors retrieved` — order the pool by **descending similarity to the manuscript** and take the top N,
  which is how the product assembles a corpus: a 3-reference check is the head of the relevance ranking, a
  6 000-sentence academic corpus is that same head plus a long tail.
* `--pool <datasets>` / `--pool-only` — draw distractors from *other* datasets, so a true paraphrase of a query
  cannot be in the corpus at all.
* `--drop-above X` — remove every corpus sentence within X of any query and **report how many**, bounding what
  contamination is worth on a same-dataset pool.
* `--examples N` — dump the highest-scoring flags. Every one is a false positive *by construction*, so a human
  reading them can see whether the construction is lying.

**Measured** (bi-encoder, 250 negative / 250 positive queries, `eval/results/corpus_*.json`):

*Mean top score for a query with **no** true match — QQP:*

| N | same-dataset (ADR-0024) | same-dataset, dedup ≥0.90 | **retrieved**, dedup ≥0.90 | cross-dataset | cross-dataset **retrieved** |
|---|---|---|---|---|---|
| 100 | 0.343 | 0.343 | 0.372 | 0.223 | 0.335 |
| 500 | 0.463 | 0.459 | 0.518 | 0.308 | 0.414 |
| 1 000 | 0.508 | 0.504 | 0.567 | 0.349 | 0.430 |
| 3 000 | 0.575 | 0.569 | 0.595 | 0.399 | 0.435 |
| ~5–6 000 | 0.606 | 0.596 | 0.596 | 0.432 | 0.435 |

*FPR at the 0.78 cutoff, dedup ≥0.90:*

| N | QQP random | QQP **retrieved** | STS-B random | STS-B **retrieved** |
|---|---|---|---|---|
| 100 | 0.000 | **0.100** | 0.012 | **0.080** |
| 500 | 0.024 | 0.116 | 0.048 | 0.080 |
| 1 000 | 0.040 | 0.116 | 0.068 | 0.080 |
| 3 000 | 0.088 | 0.116 | — | — |

**Three findings, in order of how much they change what we believe.**

1. **Relevance dominates size, and it is worth 10–30× the corpus.** Order the corpus by relevance and the FPR is
   essentially *flat in N*: 87% of QQP's eventual false-positive rate is already present at **N=100**, and on
   STS-B it is 100%. A retrieved corpus of 100 sentences behaves like a random corpus of 1 000–3 000. This is a
   within-construction comparison — both arms carry the same contamination — so it is the most robust result here.
   **ADR-0024 therefore scales the cutoff against the smaller half of the effect.**
2. **ADR-0024's headline numbers were overstated.** On a corpus that *cannot* contain a true match (cross-dataset
   pool), QQP's FPR is **0.000 at every threshold and every size** — the top score never exceeds 0.634. On the
   same-dataset pool, dropping the 58 sentences within 0.90 of a query moves FPR@0.78 at N=3 000 from 0.108 to
   **0.088** and the p95 from 0.882 to **0.837**. The `--examples` dump shows why: the top "false positives" were
   real paraphrases QQP simply never labelled ("What is the funniest joke you ever heard?" / "What is funniest
   joke you've ever heard?", 0.99), and STS-B and MRPC turn out to **share source sentences** (0.998 on a
   "Lord Falconer …" pair). The 0.90 cut is itself conservative — the dump still shows genuine duplicates at
   0.876–0.890 — so **0.088 remains an upper bound**, and the true value is somewhere in 0.000–0.088 that no
   public pair-labelled dataset can pin down.
3. **The residual false positives are boilerplate, not topic drift.** What survives de-duplication is
   template text with different facts in it: *"The broad Standard & Poor's 500 Index was up 8.79 points, or 0.96
   percent, at 929.06"* vs *"The broader Standard & Poor's 500 Index gave up 11.91 points, or 1.19 percent, at
   986.60"* — **0.877**, opposite direction, different numbers. That is the ESL/boilerplate trap PAWS exists to
   test, arriving through the corpus door.

**Decision — change the evidence, not the behaviour.**
* **`k=0.06`, `pivot=500`, `ceiling=0.92` stay exactly as they are.** Finding 1 argues for a *lower* pivot and
  finding 2 for a *higher* one, and the honest width of the interval (FPR@0.78 for a small retrieved corpus is
  somewhere between 0.000 and 0.100) is wider than any refit would move the knob. Refitting on that would be
  fitting to noise, and the project's rule is that a number is only real if it was measured.
* **Every claim ADR-0024 makes is restated at its bounded value** here, in `CHANGELOG.md`, and in the
  `confident_threshold_for` docstring the product actually ships. The surviving justification for scaling is the
  *drift* — ≈0.17 per decade on a contamination-free corpus, which reproduces ADR-0024's 0.16 — not the FPR table.
* **The probe's honesty knobs are permanent, not one-off:** `--examples` is how this was caught, and
  `eval/data/README.md` now documents the contamination so the next person does not re-derive it.

**Consequences:** No user-visible change; the shipped cutoff is unchanged. What changed is what we may claim.
The decisive measurement is no longer available from public pair data — it needs the **full pipeline against
really-retrieved sources**, which is a W6 task on the deployed box (take an OA paper, let the live retriever
assemble its corpus, and score passages known not to derive from it). Finding 3 is a product lead, not just an
eval one: numeric/boilerplate templates are worth a matcher-side signal, because no threshold separates them.

## ADR-0026 — Same shape, different figures: a numeric guard, and the sentence splitter that hid the problem
**Status:** Accepted (2026-09-06)
**Context:** ADR-0025 finding 3 said the false positives that survive de-duplication are not topical drift but
**template text with different facts in it** — two S&P-500 report sentences, opposite directions, different
numbers, cosine **0.877**. No cosine threshold separates those, because the sentences really are near-identical
in form. That calls for a second, orthogonal signal. Building one exposed something worse first.

### The bug the guard walked into
The matcher's sentence splitter was `[^.!?\n]+(?:[.!?]+|\n+|$)` — **every period ends a sentence**. So

    "The broad Standard & Poor's 500 Index was up 8.79 points, or 0.96 percent, at 929.06."

was split into `"The broad Standard & Poor's 500 Index was up 8."` plus three fragments, and the fragments fell
under `min_sentence_words` and were **dropped entirely**. The passage was not merely embedded as a truncated
stub — most of it was never compared against anything. This is a checker whose users write `p = 0.05`,
`Fig. 3`, `et al. 2019` and `J. R. R.`; the flaw sat in the middle of its core loop.

**Measured on the eval corpora:** the old rule over-split **19.9%** of MRPC sentences (news prose, full of
figures), 5.8% of STS-B and 4.2% of QQP. Academic prose with statistics in it is worse, not better.

**Decision — rules with named exceptions, not a library.** `split_sentences()` treats a period as a boundary
unless it is between digits (`8.79`), the dot of a listed abbreviation (`et al.`, `Fig.`, `approx.`), an initial
(`J. R. R.`), or followed by a lower-case letter (`www.example.com`). Newlines always break, because in a PDF the
line structure is the only sentence signal a heading or list item has. Offsets are preserved and the spans tile
the text exactly, so character-level localisation is unaffected. **No spaCy/nltk/pysbd**: ADR-0018 deleted the
last heavy NLP dependency, and a model download for sentence boundaries is not a trade this project makes — the
exceptions above are auditable, testable one by one, and cost nothing.

### The guard
`services/numeric_guard.py` compares the **multiset of numbers** in the passage and its source (digits plus small
number words, so "five" matches "5") and reports their Jaccard overlap. A confident paraphrase match whose
overlap is at or below a gate is moved to **`review`**.

**Measured** at the 0.78 cutoff, per dataset, over pairs where both sides state a number
(`eval/results/numeric_*.json`, `python -m eval.run_numeric mrpc stsb qqp paws`):

| dataset | coverage | negatives caught | positives softened | ratio |
|---|---|---|---|---|
| STS-B | 14.5% | **72.4%** | 2.0% | 36.9× |
| QQP | 9.5% | 30.2% | 9.6% | 3.15× |
| MRPC | 42.6% | 24.0% | 8.2% | 2.91× |
| PAWS | 47.2% | 0.2% | 0.0% | silent |

**The gate is 0.20 because that is where the ratio peaks** — independently on MRPC (2.91×) and QQP (3.15×), and on
STS-B's plateau. Above it the ratio falls on two of the three; below it, pairs whose only shared number belongs to
a **name** ("the S&P 500 Index", "a Boeing 747") read as agreeing when no fact is shared at all. PAWS is untouched
by design: its negatives are word-order swaps that keep every number, and a signal that pretends to solve PAWS
would be lying.

**Constraints, all enforced by tests:** paraphrase only — never verbatim (identical text has identical numbers)
and never translated (numerals and decimal separators legitimately differ); it moves exactly one band,
`confident → review`, and never touches the reporting floor; the match, its score and its source stay fully
visible; `PRISM_NUMERIC_GUARD=false` disables it and `PRISM_NUMERIC_GUARD_GATE` retunes it.

### Does this hand someone an evasion technique?
It has to be asked, because ADR-0014's boundary is absolute. Changing the figures in a copied sentence would move
it from `confident` to `review` — but the match is still **reported, with its source, at its real similarity**;
`review` means "read this yourself", not "cleared". The verbatim pillar is untouched, so copied wording still
lands as `confident` on its own. And the thing being described — altering the numbers in one's own manuscript — is
data fabrication, a graver problem than the one it would evade. The triage text says none of this to the user: it
explains why the band is what it is and asks them to compare the two passages. The existing CI test that forbids
evasion wording in guidance covers the new note.

**Consequences:** More `review`, less `confident`, on exactly the class of match that measurement says is least
trustworthy — the intended direction, and the same safe direction as ADR-0024. The splitter fix is the larger
change of the two: every check now compares whole sentences, so scores on numeric prose move (up or down) and the
ADR-0024/0025 corpus calibration was measured with the *old* splitter — a point for the W6 re-measurement to
carry. Coverage is honest and stated: the guard is silent on the 53–90% of pairs where one side states no number.

## ADR-0027 — Audit the lockfile in CI, and the 16 advisories that were already there
**Status:** Accepted (2026-09-06)
**Context:** The backlog carried "`pip-audit` step in CI once the lockfile has settled" as a small chore. It had
settled. Running it once, before writing any CI, turned the chore into a finding.

**Decision — audit the lockfile, not a fresh resolve.** `requirements.lock` is the exact set the production image
installs, so it is the set that can actually be exploited; a resolve done at CI time audits a *different*
dependency graph than the one shipped. `pip-audit --strict --no-deps --disable-pip -r requirements.lock` reads the
pinned versions directly: no resolver, no downloads, seconds rather than minutes. Two mechanical details, both
learned the hard way:
* `torch==2.14.0+cpu` is a local version identifier that exists only on the PyTorch index, so the audit step
  normalises `+cpu` away — the advisories for the CPU build are the advisories for the version it is built from.
* The lockfile header is now **plain ASCII**. It contained an em dash, and `pip-audit` reads requirements files
  with the platform's default codepage — on Windows that is cp1252, which cannot decode it, and the audit died
  with a `UnicodeDecodeError` rather than a security answer. A file that tooling must read is not the place for
  typography.

**What the first run found — 16 advisories across 4 packages, every one with a fix available:**

| package | pinned | advisories | fixed in |
|---|---|---|---|
| `python-multipart` | 0.0.9 | **7** | 0.0.31 |
| `starlette` | 0.38.6 | **7** | 1.3.1 |
| `requests` | 2.32.5 | 1 | 2.33.0 |
| `python-dotenv` | 1.0.1 | 1 | 1.2.2 |

The first two are not incidental: `python-multipart` parses **every file a user uploads to PRISM**, and
`starlette` is the ASGI core under FastAPI. This is the whole argument for the step existing — nobody had looked,
and looking took one command.

**The upgrade that clears them:** `fastapi 0.115.0 → 0.141.1` (it requires only `starlette>=0.46.0`, so starlette
moves 0.38.6 → **1.6.0**), `python-multipart 0.0.9 → 0.0.32`, `python-dotenv 1.0.1 → 1.2.3`,
`requests 2.32.5 → 2.34.2`. That last one forced one more: `arxiv 2.1.3` pins `requests~=2.32.0`, so `arxiv` moves
to **4.0.1** — two majors, but its API is unchanged at all three of our call sites
(`Client(page_size, delay_seconds, num_retries)`, `Search(query, max_results, sort_by)`,
`SortCriterion.Relevance`), which was checked by signature before the pin moved.

**Verified, not assumed:** ruff clean · 215 tests green on the new stack · the app starts under a real uvicorn and
`/health` answers · browser E2E 2/2 with 0 console errors (FastAPI's `TestClient` would not have caught an ASGI
regression across a starlette major) · `pip-audit` reports **no known vulnerabilities**.

**The step is blocking.** An advisory with no fix available is added inline as
`--ignore-vuln <ID>   # <date> <who looked> — why it cannot reach us`, so an exemption is a decision on the
record with a name against it. Deleting the step to go green is not a maintenance option.

**Consequences:** Dependency drift now surfaces on every push instead of at the first incident report, and the
same command is in `requirements-dev.txt` so it can be run locally before pushing. The cost is that an upstream
advisory can turn CI red on unrelated work — which is the point, and the ignore convention is the release valve.
