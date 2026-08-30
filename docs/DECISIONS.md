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
