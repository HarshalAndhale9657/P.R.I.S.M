# PRISM — Plan to Launch (solo, bootstrap, ~12 weeks)

> The authoritative launch plan. Product = the honest **publication-readiness / integrity coach** (ADR-0014).
> Constraints: solo founder (+AI), ~3-month timeline to first paying users, bootstrap/near-$0 (OpenAI credits
> used surgically), India-first. Synthesized from a 6-lens research pass (market, product, architecture, ML,
> legal, unit economics). **Hard boundary: no detection-evasion, ever.**

## TL;DR
The 12-week job: **(1)** genuinely **build + honestly benchmark the core detection** (it is NOT a proven moat yet —
the P=1.00/FPR=0.00 is a *self-authored 32-case* gate, and hard-paraphrase recall is 0/3); **(2)** layer a
deterministic **flag-triage** + LLM **honest coaching** (gpt-4o-mini) + accounts + metering + one payment rail;
**(3)** ship to **one** beachhead with a legally-forced buying trigger. **Launch = ~15–30 real paying users.**

> **⚙️ REVISED for core-ML-first (ADR-0015, refined by ADR-0016).** Owner chose to invest in the real ML within the
> 3-month timebox, **plagiarism/source-matching FIRST**: best **pretrained** models + a REAL third-party benchmark
> (public paraphrase sets — **PAWS/MRPC/STS-B/QQP**, **no PAN**) + better retrieval + a **cross-encoder reranker**
> that is *selectively* fine-tuned on free Colab/Kaggle GPU **only if it beats pretrained** on that benchmark, all in
> a **re-architected pluggable pipeline** (`parse → retrieve → match → rerank → ai_risk → triage → coach → report`).
> The **AI-text detector is deferred** behind this (still honesty-gated when built; v1's AI story = disclosure coach).
> This front-loads ML/benchmark/refactor and compresses SaaS plumbing. Trade-off vs. the original "drop torch → €5
> box": heavier models mean we **keep PyTorch** and size up to a ~€8 8GB VPS — still bootstrap-cheap. Sections
> **3 (scope), 4 (stack), 5 (detection), 9 (milestones)** reflect this; market/pricing/GTM/economics are unchanged.

## 1. Beachhead market (pick ONE)
**India / South-Asia PhD candidates (Eng/CS/Life-Sci, ESL, yrs 2–4) submitting a thesis chapter or IEEE
conference paper in the next 2–8 weeks**, under the **UGC Anti-Plagiarism Regulations (2018)**: ≤10% safe;
10–40% → forced revision; 40–60% → 1-yr debarment; >60% → registration cancelled (many unis stricter, 5–7%).
Why: a **legally-mandated, dated, career-ending** pass/fail number *forces* the purchase; huge, English-writing,
price-sensitive, UPI-payable; and **nobody sells them an honest, source-attributed, coaching pre-check under $20**.
*Not chosen:* global grad students (diffuse, free institutional Turnitin) and institutional B2B (6–18-mo sales
cycle — that's the year-2 expansion, seeded now only via a soft Lab tier).

## 2. Positioning & wedge
**"See what your journal's integrity check will see — and fix it honestly — before you submit."** A pre-submission
**coach**, not an accuse-o-meter and not a beat-the-checker trick. Everyone else either **gate-keeps** and won't
sell to the author (iThenticate/Turnitin), **sells evasion** that gets students debarred (Quillbot/humanizers), or
**sells AI-detection universities have disabled** (Originality/GPTZero, high ESL false positives). PRISM is the only
**honest, source-attributed, self-serve pre-check that coaches the fix and publishes its false-positive rate** — the
**anti-Quillbot**. Lead with the measured numbers (honestly labelled) + the **AI-disclosure** framing (IEEE requires
AI use *disclosed*, not zero AI → we help comply, never hide). **Never** imply a guaranteed pass or IEEE/Turnitin affiliation.

## 3. v1 scope (what ships) vs cut-to-later
**Ships in v1 (core-ML first):** re-architected **pluggable pipeline** + **real third-party benchmark** (public
paraphrase/similarity sets — **PAWS/MRPC/STS-B/QQP**, +PAWS-X) as the CI source of truth · **improved detection**
(stronger ONNX bi-encoder + **cross-encoder reranker** — pretrained, *selectively* fine-tuned on those sets only if it beats pretrained) · **expanded retrieval** (OpenAlex + arXiv + Semantic Scholar + OA full-text) ·
**AI detector — honesty-gated** (calibrated Low/Elevated/High + Inconclusive; ships only if it clears the ESL-FP bar,
else disclosure-coach fallback) · **deterministic flag-triage** · **LLM honest coaching** per flag (gpt-4o-mini,
JSON, cached; source shown, **no auto-rewrite**) · **AI-USE-DISCLOSURE coach** · submission-risk **report** + re-check ·
**accounts** (Supabase) · **metering** · **payments** (Razorpay) · **ephemeral-by-default** privacy · legal minimum.

**Cut to later:** web-search corpus layer (metered paid tier post-revenue) · **from-scratch training** and any
fine-tune beyond the one paraphrase cross-encoder (pretrained-first per ADR-0016) · the **AI-text detector**
(deferred behind plagiarism-first; still honesty-gated when built) · batch/history · Redis/queue (keep in-process worker, persist job state to Postgres) ·
teams/SSO/LTI/SOC2 · international payment rails (add after India proven) · the legacy authorship engine.
> If the AI detector fails its ESL honesty gate, it drops to disclosure-coach-only and that time buffers the schedule.

## 4. Tech stack (named, with rough $/mo)
| Layer | Choice | $/mo |
|---|---|---|
| Bi-encoder (retrieval) | **`bge-base`/`gte-base` via ONNX** (fastembed) behind `local_embeddings.embed()` — stronger than MiniLM, still CPU | $0 |
| Cross-encoder rerank + AI models | pretrained **cross-encoder** + small perplexity LM + open AI-detector (**PyTorch on CPU**; rerank only top-k so it stays cheap) | $0 |
| Backend hosting | **Hetzner CX32 VPS** (4 vCPU/8GB) — sized up from CX22 for the heavier models; Docker + Caddy; FastAPI + worker + Postgres | ~$8 (€8.5) |
| Frontend | **Cloudflare Pages** (free static, no build step) + orange-cloud the API | $0 |
| Auth + DB + storage | **Supabase** (Google OAuth + magic-link + Postgres); FastAPI verifies the JWT — don't hand-roll auth | $0 → $25 at revenue |
| Payments | **Razorpay** (UPI/cards/netbanking, India-native, ~2%), hosted checkout + webhook | %-only |
| LLM (coaching prose only) | **OpenAI gpt-4o-mini**, JSON mode, ≤3 calls/check, content-hash cached — **never** for AI-detection/embeddings | ~$0–20 (credits) |
| Observability/CI | Sentry free + UptimeRobot free + existing GitHub Actions (pytest + eval gate) + SSH deploy | $0 |

**Total infra ~$5/mo pre-launch → ~$30–35/mo at first paying users.**

## 5. Core-ML plan (pretrained-first, plagiarism-first, honestly benchmarked) — ADR-0016
**Principle:** measure honestly first, then lift quality with the best pretrained models; **fine-tune only where it
provably wins** (v1: at most the paraphrase cross-encoder, on free Colab/Kaggle GPU — inference stays CPU/ONNX).
**Focus is plagiarism / source-matching first; the AI detector is deferred.** Everything gated by a real,
third-party benchmark — public paraphrase/similarity sets, **not** my self-authored set and **not** PAN.

**5.1 Re-architecture (pluggable pipeline).** Restructure into clean stages with interfaces so each can be swapped
+ evaluated independently: `parse → retrieve → match (bi-encoder + verbatim) → rerank (cross-encoder) → ai_risk →
triage → coach → report`, plus a first-class `eval/` harness (runs any stage over a dataset) and a `models/` layer
(download/cache/version). The existing matcher/corpus become stage implementations behind these seams.

**5.2 Real benchmark (source of truth — do this FIRST).** Replace the self-graded 32-case eval with **ready-made
public labelled data** run through the ACTUAL pipeline: **PAWS** (hard paraphrase / non-paraphrase pairs — high
lexical overlap, the exact trap for our matcher), **MRPC** (paraphrase), **STS-B** (graded semantic similarity →
threshold calibration), **QQP** (duplicate questions), and **PAWS-X** for multilingual/translated. Report
precision/recall/**FPR per stratum** (incl. a high-overlap-but-not-paraphrase stratum ≈ real ESL/boilerplate risk),
and freeze as the CI gate. Keep the synthetic 32-case set only as a fast smoke test. **No PAN.** *This establishes
the honest baseline before any tuning.* (Human-vs-AI sets RAID/HC3/M4 are reserved for the later AI-detector phase.)

**5.3 Detection lift (pretrained-first, selective fine-tune).** Upgrade the bi-encoder from `all-MiniLM-L6-v2` to a
stronger open model (`bge-base-en-v1.5` / `gte-base` / `all-mpnet-base-v2`; multilingual variant for translated) via
ONNX — **no training**. Add a **cross-encoder reranker** (start pretrained: `ms-marco-MiniLM` / a paraphrase
cross-encoder) over the top-k candidates to catch the **hard paraphrases** the bi-encoder misses (current recall
0.77). **Only then** consider a **light fine-tune of that cross-encoder on PAWS/MRPC** (free Colab/Kaggle GPU, LoRA);
**export to ONNX and ship it only if it beats the pretrained cross-encoder on the §5.2 benchmark** without raising
FPR (esp. high-overlap negatives). Recalibrate thresholds on the real benchmark throughout.

**5.4 Retrieval / corpus (mirror the gate, in budget).** uploads + OpenAlex + arXiv now → add **Semantic Scholar**
(free key) + **Unpaywall/arXiv/PMC OA full-text** fetch for near-$0 recall (full text, not just abstracts) → a
metered **web-search** layer later (paid). Crossref = reference-metadata only. **Always label coverage** on the
report ("checked against …; NOT the full web/subscription journals — a clean result is not a guaranteed iThenticate pass").

**5.5 AI detector (DEFERRED behind plagiarism-first — ADR-0016).** Not in the first core-ML push. When built (later
phase, on RAID/HC3/M4 public human-vs-AI sets): a calibrated **Low / Elevated / High + hard Inconclusive** signal
(never a "% AI") fusing perplexity (small LM) + burstiness (reuse `feature_engine`) + an open pretrained detector,
with per-feature "why". **Ship it only if it clears a strict ESL-false-positive bar** on real ESL human text —
otherwise the AI-USE-**disclosure** coach is the whole offering. OpenAI is **never** asked "is this AI?". Until then,
v1's AI story is the disclosure coach only. This is the honesty landmine that killed Originality/GPTZero — gate is non-negotiable.

**5.6 Triage & honesty guards.** Deterministic auditable rules over spans + citation regex → remediation type;
boilerplate/IDF suppression is the #1 false-positive defense, wired to the FPR harness. A **CI honesty gate** fails
the build on any "X% AI"/"guaranteed pass" string; a **matcher post-filter** rejects any LLM coaching output
overlapping the flagged source (coaching can never become evasion).

## 6. Pricing
| Tier | Price | Quota |
|---|---|---|
| **Free / Preview** | ₹0 | 1 check/day ≤1,500 words; shows the scary highlights + attribution, **locks** the report + coaching (create urgency, gate the payoff) |
| **Pay-per-report (hero)** | **₹149 (~$1.79)** / $2.99 intl | 1 manuscript ≤10k words: full report + triage + honest-fix coaching + AI-disclosure + unlimited re-checks 30 days. (5-pack ₹599.) Undercuts Enago $18 ~10×. |
| **Pro** | ₹749/mo (~$9) / $12 intl | 15 manuscripts/mo, batch, history, self-plagiarism across your own prior papers |
| **Lab / Advisor** (soft B2B seed) | ₹2,999/mo (~$36) | 5 seats, shared history — price only, no admin console yet |

## 7. Unit economics
Cost per ~6,000-word check: embeddings **$0** (local ONNX) + gpt-4o-mini coaching **~$0.005–0.01** → fully-loaded COGS
**~$0.02–0.03**. Hero ₹149 report ≈ **99% gross margin**; Pro ≈ **93–96%**. Free-tier worst case bounded <$0.01/user by
the word/day caps + cache. **Break-even ~5–10 paying users**; ~30–40 → ~$400–600/mo; ~70–130 → ~$1–1.5k/mo part-time
salary. **3-month target = willingness-to-pay validation (~15–30 payers), not salary.** Cost controls **before any OpenAI
call**: max-words/check, cap flags coached (top ~30), batch ≤3 calls w/ max_tokens, per-account monthly $ ceiling,
org-wide budget alert, content-hash cache.

## 8. GTM (8 weeks, cheapest/highest-intent first, all solo)
1. **SEO** from day 1 (compounding): "check paper before IEEE submission", "get under UGC 10% before your thesis",
   "iThenticate too expensive alternative", "how to disclose AI use in an IEEE paper" — each ends in a free Preview.
2. **Reddit** wks 1–4, value-first (r/PhD, r/GradSchool, r/AskAcademia) — help first, mention as one honest option.
3. **India Telegram/WhatsApp thesis groups** wks 2–6 — where the beachhead lives; 5-pack referral; highest conversion/hour.
4. **YouTube/Shorts** wks 2–8: "How I got my thesis under UGC 10% honestly (without Quillbot)".
5. **University writing centres + PhD coordinators** wks 3–8: free Pro codes; seeds word-of-mouth + future B2B.
6. **X/LinkedIn** ongoing: post the measured FP-rate + "honest vs humanizer"; ride the AI-detector-reliability debate.
7. **Product Hunt** wk 12 with testimonials in hand. Keep 3+ channels always live.

## 9. 12-week milestones (core-ML front-loaded, ADR-0015)
> Weeks 1–5 buy the **honest core** (re-architecture → real benchmark → detection lift → AI-detector go/no-go);
> weeks 6–12 wrap it in the (compressed) SaaS + coach + payments. The benchmark in W2 is the gate everything else defends.
- **W1 — Re-architecture skeleton:** split into pluggable stages `parse → retrieve → match → rerank → ai_risk → triage → coach → report` behind interfaces; first-class `eval/` harness (run any stage over a dataset) + `models/` layer (download/cache/version); existing matcher/corpus become stage impls. Keep all 22 tests green.
- **W2 — Real benchmark = the gate (do first):** ingest **public paraphrase/similarity sets — PAWS, MRPC, STS-B, QQP (+ PAWS-X)**; run the ACTUAL pipeline; report P/R/**FPR per stratum** (incl. a high-overlap-but-not-paraphrase stratum ≈ ESL/boilerplate risk); **freeze as CI gate**, keep the 32-case synthetic set as a fast smoke. **No PAN.** This is the honest baseline.
- **W3 — Detection lift (bi-encoder, no training):** swap MiniLM → stronger ONNX embedder (`bge-base`/`gte-base`; multilingual for translated) behind `local_embeddings.embed()`; recalibrate thresholds on the real benchmark; **ship only if recall ↑ with FPR flat** (esp. high-overlap negatives); torch fallback until green.
- **W4 — Cross-encoder rerank + retrieval:** pretrained cross-encoder over top-k candidates to catch **hard paraphrases** (current recall 0.77); add **Semantic Scholar** + **Unpaywall/arXiv/PMC OA full-text** (real full text, not just abstracts); re-eval, keep gate green.
- **W5 — Selective cross-encoder fine-tune (go/no-go):** light fine-tune of the reranker on **PAWS/MRPC** (free Colab/Kaggle GPU, LoRA) → export to ONNX; **ship it only if it beats the pretrained cross-encoder on the W2 benchmark** without raising FPR — else keep pretrained and bank the week. *(AI detector is deferred behind this — ADR-0016.)*
- **W6 — Go live:** gate heavy/legacy deps out of the image; deploy backend (**Hetzner CX32** 8GB + Docker + Caddy) + frontend (Cloudflare Pages); /health on UptimeRobot; Sentry; smoke the full pipeline on a real 20-page PDF.
- **W7 — Accounts + metering + privacy (compressed):** Supabase (OAuth + magic-link + Postgres), FastAPI JWT verify, user/check/usage tables, **persist job state to Postgres**, auth + row-level ownership on `/api/check`; per-user checks/words counter → 402 + upgrade CTA; per-account OpenAI-$ ceiling; **ephemeral-by-default** (delete raw text + embeddings after report).
- **W8 — Triage + AI-disclosure coach:** deterministic triage rules → type + priority; boilerplate/IDF suppression wired to the FPR harness; static AI-use disclosure panel; unit tests per rule.
- **W9 — Honest coaching (spend credits here):** gpt-4o-mini per-type JSON `{what_it_is, why_flagged, honest_fix, do_not}`; ≤3 calls, cached; hard prompt contract (explain + point to source, never rewrite-to-lower); **matcher post-filter**; coach-card UI (side-by-side source, no auto-rewrite).
- **W10 — Report + re-check:** extend the HTML report (triage summary, similarity vs guidance band, AI-risk band if shipped, fix checklist, AI-disclosure, "reduces risk not guaranteed pass" + coverage footer); before/after re-check via cache.
- **W11 — Payments + legal:** Razorpay hosted checkout ₹149 hero + ₹749 Pro (test first) → webhook flips plan + 5-pack, verify UPI on a real device; Privacy/ToS/AUP (advisory-only, no-guaranteed-pass, no-affiliation, no-evasion); OpenAI **Zero-Data-Retention**, send only flagged spans + source snippets; **CI honesty gate**; delete-my-data.
- **W12 — Polish + LAUNCH:** empty states, 60-sec demo, pricing page, E2E on a 20-page PDF; SEO live + indexed; YouTube; seed Reddit/Telegram/WhatsApp + writing centres; Product Hunt. Confirm round-trip: upload → <60s → coach → re-check → export → **card charged + webhook upgrades**.
> **Buffer sources if W1–5 overrun:** the W5 fine-tune is optional (keep pretrained cross-encoder → frees W5); cross-encoder itself is optional if the bi-encoder alone clears recall; the AI detector is already deferred (disclosure-coach only); W7 is deliberately compressed. Slip order if needed: fine-tune → OA full-text → rerank.

## 10. KPIs
Activation (signup→first check) ≥60% · free→paid 3–6% · fix-acceptance rate (source viewed/marked resolved) · paid
checks/week (north star) · cost/check <$0.05 & GM ≥85% · per-account OpenAI $ vs ceiling · **first 15–30 payers in 12 wks** ·
reactivation around submission season · low refund/chargeback · **CI: FPR=0.00 incl. ESL + boilerplate strata**.

## 11. Top risks → mitigations
- **Corpus gap** (we can't see paywalled/student DBs → our % ≠ DrillBit's) → frame "mirrors/reduces, not guaranteed"; label coverage every report; add free OA full-text; never claim comprehensiveness.
- **Positioning drift into "beat the detector"** (top *legal* risk — essay-mill liability, payment bans) → no-evasion in product + ToS + AUP + every line of copy; keep ADR-0014 public.
- **Shipping a bad AI-text detector** (ESL false-positive backlash — this killed Originality/GPTZero) → **deferred behind plagiarism-first** (ADR-0016); when built, **gate on a real ESL-human set** (RAID/HC3/M4 for train/eval), ship only if it clears the strict ESL-FP bar, else disclosure-coach only. Never a "% AI"; hard Inconclusive band. v1 ships without it.
- **Detection "lift" that doesn't lift (or raises FPR)** → every model/rerank/threshold/fine-tune change is judged on the **real public-dataset benchmark** (PAWS/MRPC/STS-B/QQP), not the synthetic set; ship a change only if recall ↑ with FPR flat (esp. high-overlap negatives); keep the prior model as fallback until green.
- **Heavier models blow the box / latency** → cross-encoder reranks only top-k; CX32 8GB headroom; measure per-check RAM + wall-time in W6; drop rerank or shrink the embedder if <60s is at risk.
- **OpenAI runaway spend** → server-side caps before any call (words, flags, ≤3 calls, per-account $, org budget alert, cache).
- **Single-VPS SPOF / cold start** → Hetzner (no spin-down) + UptimeRobot + Postgres-durable jobs + Dockerized (flee to Render/Fly same-day) + daily snapshot.
- **Storing unpublished manuscripts** (trust/GDPR/DPDP) → ephemeral-by-default; OpenAI ZDR + send only spans; sub-processor list + delete path; headline "we don't retain/train on your manuscript".
- **Coaching LLM hallucination / drift to evasion** → constrain to the detected match + shown source; author-in-loop; matcher post-filter; label AI-written guidance.
- **Single-channel concentration** → keep 3+ channels; lean on compounding SEO + evergreen YouTube.

## 12. Definition of launch
A beachhead author can, unassisted on a real URL: sign in → upload a real manuscript (+refs) → get detection <~60s
(verbatim+paraphrase+translated w/ attribution) → see each flag **triaged** → open a per-flag **honest-fix coach card
with the source shown** (no auto-rewrite anywhere) → read **AI-use disclosure** guidance → export a **submission-risk
report** with the honest footer → **re-check** before/after → **pay ₹149 via Razorpay UPI** (webhook upgrades account).
Backed by: a **real third-party benchmark** as the green CI gate (incl. ESL + boilerplate strata + honesty gate),
published Privacy/ToS/AUP, ephemeral manuscripts, and **~15–30 real paying users**. The **AI-risk band ships only if
it clears its ESL honesty gate** (else disclosure-coach only — not a launch blocker). *Not required:* web corpus, batch, teams, intl payments.

## 13. The single most important thing
The **per-flag honest remediation experience** — *"here's exactly what this is, why the gate flags it, and the honest
fix, with the source shown"* — at a quality/tone an anxious ESL author can act on **alone**, never crossing into evasion
(no auto-rewrite, source always visible, matcher-verified the coaching doesn't launder copied text). Detection/corpus/
AI-risk are table stakes or deferrable — **triage + honest coaching IS the product and the moat.**
