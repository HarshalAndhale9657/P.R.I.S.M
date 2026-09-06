# Progress Log

Running worklog — the **memory of *what happened when***. Newest first. One entry per working session.
(Decisions go in [`DECISIONS.md`](DECISIONS.md); shipped changes go in [`../CHANGELOG.md`](../CHANGELOG.md).)

---

## 2026-09-07 — The rest of W7 that needs no account: auth, ownership, quota (ADR-0030)

**Scope.** Everything in W7 that can be built and *proven* without a Supabase project: verify the token Supabase
would issue, tie jobs to the user who submitted them, and swap the per-IP limiter for a per-user quota. Built
against self-signed tokens; wiring to a real project is one environment variable.

**The three rules were written before the code**, and each has a test that would fail if it bent: a presented
token is always verified (a stale token is a 401 even when auth is optional — never a silent downgrade);
`auth_required` gates endpoints, not verification; ownership answers **404, never 403**, so a job id you do not
own is indistinguishable from one that never existed.

**Both Supabase token generations** — HS256 with the project secret, and RS256/ES256 via JWKS — through one
verifier. The JWKS path is tested with generated RSA keys and a stubbed fetch: keys cached, exactly one refresh on
an unknown `kid`, then failure; the header algorithm must match the key it names.

**Quota is a ledger, not a job count**, because jobs expire on a 30-minute TTL and a daily budget has to outlive
that. Same shape as the job store: memory always, Postgres in CI sharing the job store's pool, one contract suite.
It records *acceptance*, so a queued check that later fails still counted, and a 400 never does. Over the limit
is 402 with the numbers in headers and a plain sentence in the body.

**A small measurement of my own assumptions:** two tests failed on first run because they used tokens expired by
5–10 seconds and the verifier has a 30-second clock-skew leeway. The code was right; the tests learned.

**Verified:** 255 passed / 18 skipped locally · browser E2E 2/2 with `/health` reporting `auth: off` · lock
regenerated with PyJWT, ASCII header, `pip-audit` clean · Postgres halves run in this commit's CI.

**What W7 still needs from the owner:** a Supabase project (secret or JWKS URL), the sign-in UI against it, and a
number for the free quota. The backend side is code-complete.

---

## 2026-09-06 (cont.) — W7 begins where it can: durable job state (ADR-0029)

**Why this piece first.** Of everything left before launch, W7's storage half is the only part that needs no
account, no key and no box — the `JobStore` Protocol has been sitting there since ADR-0019 as a five-method seam
with one implementation behind it. So: a second implementation, and one contract suite that both must pass.

**`PostgresJobStore`.** Epoch floats in `DOUBLE PRECISION` so the TTL check is *literally the same expression* as
the in-memory store's; a column whitelist on `update()` because `**fields` interpolated into SQL is an injection
waiting for a typo; one idempotent `CREATE TABLE`; the same `ttl_seconds`/`max_jobs` bounds, because durability
buys restarts and replicas, not retention. `/health` now says which store it is.

**The contract runs against both.** Locally the Postgres half is *skipped, visibly* (11 skips in the summary);
in CI a `postgres:16` service container supplies it, and the job greps its own output and **fails if those tests
were skipped** — the way a "verified in CI" claim stays honest.

**Found on the way: the suite had a circular import hiding in it.** `import worker` failed cold —
`worker.runner` pulled `app.settings`, `app/__init__` eagerly pulled `factory`, `factory` pulled `worker`.
`tests/test_worker.py` fails on its own; it only ever passed because `test_check_api.py` sorts first and imports
`app`. Fixed at the structure: context vars to `utils/context.py`, `create_app` resolved lazily. Two small ASCII
lessons on top: an em dash in a pytest skip reason makes the final summary line vanish on a cp1252 console, and
`-q` stacked on `addopts = -q` suppresses it entirely — twenty minutes of "where did the summary go".

**Verified:** ruff clean · 231 passed / 11 skipped · worker tests pass alone · lock regenerated with psycopg,
ASCII header kept, `pip-audit` clean · the Postgres half's verification *is* this commit's CI run.

**Still open in W7:** Supabase JWT as a FastAPI dependency, per-user ownership on `GET /check/{id}`, quota → 402,
ephemeral deletion of raw text. All of it builds on this table.

---

## 2026-09-06 (cont.) — The same bug again, one door down (ADR-0028)

**The question ADR-0026 left.** The splitter bug was silent, sat in the core loop, and survived a green suite
because every fixture was tidy prose. That is a *pattern*, not an incident, so the next thing to do was point the
parser at input that looks like real work: the actual *Attention Is All You Need* PDF, 15 pages, instead of the
synthetic fixture in the repo.

**The PDF path passed** — 4 969 words, 81 reference entries correctly excluded, no ligature or soft-hyphen or
hyphenation artefacts, 247 sentences at a median of 17 words. (Its longest "sentence" is a results table, which is
a layout limitation rather than a bug, and stripping tables could hide real copying. Left alone, on the record.)

**The text path did not.** `_plaintext_blocks` splits on blank lines and never ran `_clean_block`, so single
newlines survived into the matcher — where a newline ends a sentence. A manuscript wrapped at 60–80 columns (a
`.txt` export, a LaTeX source, hand-authored Markdown) was compared **line by line**, and any line under
`min_sentence_words` was dropped without trace. PDFs were fine, because `_clean_block` collapses line breaks —
so the same manuscript behaved differently depending on the format it arrived in.

| one wrapped paragraph vs a genuine paraphrase of itself | units embedded | matches | best similarity |
|---|---|---|---|
| before | 5 fragments | **0** | 0.000 |
| after | 2 sentences | 2 | **0.875** |

Not a degradation. A miss.

**Fixed by undoing *wrapping*, not line structure:** a break is joined only when the previous line does not finish
a sentence and the next begins lower-case. Lists and headings keep their breaks; hyphenation across a wrapped line
is rejoined, as the PDF path already did. Collapsing every newline would have made the two paths identical in one
line and was rejected — in plain text a break can be real structure, in a PDF it is extraction noise. What must
match is that the *same prose* reads the same either way, and that is now a test. Tests 215 → **221**.

**The lesson, twice confirmed in one day:** both bugs were silent, both sat between the user's text and the
encoder, and both were invisible because every fixture was clean, unwrapped prose. Fixtures that look like real
manuscripts buy more than more assertions about tidy ones.

---

## 2026-09-06 (cont.) — A one-line chore that turned out to be a security finding (ADR-0027)

**The chore** was the smallest item left on the unblocked list: "`pip-audit` step in CI once the lockfile has
settled." Before writing any YAML I ran the command once, to see what it would say.

**It said 16 advisories in 4 packages**, every one with a fix already published:

| package | pinned | advisories | fixed in |
|---|---|---|---|
| `python-multipart` | 0.0.9 | **7** | 0.0.31 |
| `starlette` | 0.38.6 | **7** | 1.3.1 |
| `requests` | 2.32.5 | 1 | 2.33.0 |
| `python-dotenv` | 1.0.1 | 1 | 1.2.2 |

`python-multipart` parses **every file a user uploads to PRISM**, and `starlette` is the ASGI core under FastAPI.
Nobody had looked, and looking cost one command.

**Cleared them:** fastapi 0.115.0 → 0.141.1 (it needs only `starlette>=0.46.0`, so starlette goes 0.38.6 →
**1.6.0**), python-multipart → 0.0.32, python-dotenv → 1.2.3, requests → 2.34.2. That last one forced
`arxiv 2.1.3 → 4.0.1`, because arxiv 2.1.3 pinned `requests~=2.32.0` — two major versions, so I checked its API by
signature at all three call sites before moving the pin, rather than hoping the tests would notice.

**Verified rather than assumed**, because a starlette *major* is exactly the kind of upgrade a green unit suite
can hide: `TestClient` never runs a real ASGI server. ruff clean · 215 tests · the app boots under a real uvicorn
and `/health` answers · browser E2E 2/2 with 0 console errors · audit now reports **no known vulnerabilities**.

**The CI step audits the lockfile, not a fresh resolve** — the lock is the exact set the production image
installs, and a CI-time resolve would audit a different graph than the one shipped. `--no-deps --disable-pip`
reads the pins directly: no resolver, no downloads, seconds not minutes. It is **blocking**; an advisory with no
fix is added inline as `--ignore-vuln <ID>` with a date, a name and a reason, so an exemption is on the record.

**Two mechanical scars worth keeping:** `torch==2.14.0+cpu` is a local version identifier that exists only on the
PyTorch index, so the step normalises `+cpu` away. And the lockfile header had an em dash in it — `pip-audit`
reads requirements files with the platform's default codepage, so on Windows the audit died with a
`UnicodeDecodeError` instead of giving a security answer. The header is ASCII now: a file that tooling must read
is not the place for typography.

---

## 2026-09-06 (cont.) — Building a signal found a bug in the core loop (ADR-0026)

**The plan** was ADR-0025's finding 3: the false positives that survive de-duplication are template text with
different facts in it, so build the orthogonal signal — do the two sentences state the same numbers? Measure
first, ship only if it separates.

**What actually happened.** The first end-to-end run of the guard produced *no match at all* on the very pair that
motivated it. The sentence splitter was `[^.!?
]+(?:[.!?]+|
+|$)` — **every period ends a sentence** — so

    "The broad Standard & Poor's 500 Index was up 8.79 points, or 0.96 percent, at 929.06."

became `"The broad Standard & Poor's 500 Index was up 8."` and three fragments that fell under
`min_sentence_words` and were **dropped**. Not truncated for embedding: *never compared to anything*. This is a
checker for people who write `p = 0.05`, `Fig. 3`, `et al. 2019`, `J. R. R.` — and the flaw was in the core loop
the whole time, invisible because nothing in the suite used a decimal.

**Measured:** the old rule over-split **19.9%** of MRPC sentences, 5.8% of STS-B, 4.2% of QQP. Fixed with rules
and named exceptions — digits, a listed abbreviation, an initial, a following lower-case letter — not a library:
ADR-0018 deleted the last heavy NLP dependency and a model download for sentence boundaries is not a trade this
project makes. Offsets preserved, spans tile the text, 9 tests.

**Then the guard.** Multiset overlap of the numbers in passage and source; a confident paraphrase whose overlap is
at or below the gate becomes `review`.

| at the 0.78 cutoff | coverage | negatives caught | positives softened | ratio |
|---|---|---|---|---|
| STS-B | 14.5% | **72.4%** | 2.0% | 36.9× |
| QQP | 9.5% | 30.2% | 9.6% | 3.15× |
| MRPC | 42.6% | 24.0% | 8.2% | 2.91× |
| PAWS | 47.2% | 0.2% | 0.0% | silent — its negatives keep every number |

**The gate is 0.20 because the ratio peaks there**, independently on MRPC and QQP and on STS-B's plateau — a
sweep decided it, not taste. A detail worth recording: at first I set the gate to 0.0 ("share *no* number"), and
the motivating S&P pair then scored 0.14, not 0.0 — both sentences contain **500**, which is part of the index's
*name*, not a fact either states. The sweep independently put the optimum at 0.20; catching that pair is a
consequence of the measured gate, not the reason for it.

**Constraints, all tested:** paraphrase only (never verbatim, never translated), one band only
(`confident → review`), never below the reporting floor, source always visible, disableable and retunable. The
evasion question is answered explicitly in the ADR: the match is still reported with its source at its real score,
`review` means "read this", the verbatim pillar is untouched, and changing figures in your own manuscript is
fabrication — a graver problem than the one it would evade.

**Verified end to end**, not just in tests: through the live API the S&P passage comes back `paraphrase 0.879
review numeric_conflict=true` with the triage note, while the identical second sentence stays `verbatim 1.000
confident` — the guard leaves real copying alone. Browser E2E 2/2 with 0 console errors; benchmark gates still
pass; smoke passes. The UI and report stopped saying "below the confidence cutoff" for these matches, because it
is not true of them. Tests 188 → **215**.

**Carried forward:** ADR-0024/0025's corpus calibration was measured with the *old* splitter. The W6
re-measurement now has one more reason to happen on real, whole sentences.

---

## 2026-09-06 (cont.) — Re-measuring ADR-0024 honestly: relevance beats size, and the probe was lying (ADR-0025)

**The task on the list.** ADR-0024 shipped a corpus-size-scaled cutoff and wrote its own caveat into the TODO:
the probe's distractors were *unrelated*, while production sources are **retrieved by similarity**, so "the real
effect is likely larger". W6 needs a VPS, so this was the next unblocked item.

**What the fix exposed.** Ordering the corpus by relevance needed a `--examples` dump to sanity-check, and the
dump immediately showed the top "false positives" were not false at all: *"What is the funniest joke you ever
heard?"* against *"What is funniest joke you've ever heard?"* at **0.99**. QQP labels **pairs**, so excluding a
query's labelled partner from the corpus does nothing about an unlabelled duplicate of it in some *other* pair —
and a similarity ranking promotes exactly those to the top. STS-B and MRPC turned out to share source sentences
too (0.998 on a "Lord Falconer …" pair). **The guarantee the whole probe rests on — no true match is in the
corpus — was only ever enforced pairwise.** ADR-0024's headline was partly measuring its own dataset.

**So the probe grew three defences**, all of which stay: `--pool` / `--pool-only` (corpus drawn entirely from
*other* datasets, where a true paraphrase cannot exist), `--drop-above X` (remove corpus sentences within X of
any query, and *report the count*), and `--examples` itself.

**Measured** (250 negative / 250 positive queries, bi-encoder):

| FPR @0.78, dedup ≥0.90 | N=100 | N=500 | N=1 000 | N=3 000 |
|---|---|---|---|---|
| QQP, random corpus | 0.000 | 0.024 | 0.040 | 0.088 |
| QQP, **retrieved** corpus | **0.100** | 0.116 | 0.116 | 0.116 |
| STS-B, random corpus | 0.012 | 0.048 | 0.068 | — |
| STS-B, **retrieved** corpus | **0.080** | 0.080 | 0.080 | — |

1. **Relevance is worth 10–30× the corpus size.** Order the corpus the way retrieval does and the FPR is *flat in
   N* — 87% of it is already there at 100 sentences (100% on STS-B). ADR-0024 scales the cutoff against the
   smaller half of the effect. This is the robust result: both arms carry identical contamination.
2. **The old numbers were overstated.** On a corpus that cannot contain a true match, QQP's FPR is **0.000
   everywhere** (top score never exceeds 0.634). De-duplicating the same-dataset pool moves FPR@0.78 at N=3 000
   from 0.108 → **0.088** and p95 0.882 → **0.837**. The drift claim survives untouched: **≈0.17/decade**, versus
   the 0.16 originally published.
3. **What is left after de-duplication is boilerplate.** *"The broad Standard & Poor's 500 Index was up 8.79
   points, or 0.96 percent, at 929.06"* vs *"…gave up 11.91 points, or 1.19 percent, at 986.60"* — **0.877**,
   opposite direction, different numbers. Not topic drift: template text. That is a matcher lead, not an eval one.

**Shipped: nothing, deliberately.** `k`, `pivot` and `ceiling` are unchanged. Finding 1 argues for a lower pivot,
finding 2 for a higher one, and the honest interval (FPR@0.78 on a small retrieved corpus is somewhere between
0.000 and 0.100) is wider than any refit would move the knob — fitting to that would be fitting to noise. What
changed is **what we are allowed to claim**: the shipped `confident_threshold_for` docstring, the CHANGELOG and
the ADR now quote bounded values, and the old CHANGELOG entry carries an inline correction rather than being
rewritten. The surviving justification for the scaling is the drift, not the FPR table.

The measurement that would settle it is not available from public pair data. It needs the **full pipeline against
really-retrieved sources** — a W6 task on the box: let the live retriever assemble a corpus for a real OA paper,
then score passages known not to derive from it. Tests 180 → **188**. Lint clean.

---

## 2026-09-06 (cont.) — The number that changes a default: corpus-scale calibration (ADR-0024)

> **Corrected the same day by ADR-0025** — the FPR/p95 figures below are inflated by unlabelled duplicates in the
> probe's own corpus. Bounded: p95 at 3 000 = 0.837, FPR@0.78 = 0.088, and 0.000 where no true match can exist.
> The drift (≈0.16–0.17/decade) holds. Kept unedited as the record of what was believed at the time.

**The gap.** Every number PRISM has published is **pairwise** — one candidate against one source sentence. The
matcher takes the **max over every source sentence**, which is N chances to score high. ADR-0017 wrote down the
suspicion ("0.78 is a lower bound") and then nobody measured it. With W4b full text putting real checks at
2 000–6 000 source sentences, it stopped being academic.

**The measurement** (`eval/corpus_scale.py`, `python -m eval.run_corpus qqp stsb`): build a distractor corpus of N
sentences; query with sentences whose paraphrase is **absent**, so every flag is a false positive by construction;
sweep N. 250 negative / 250 positive queries.

| corpus | mean top score, no true match | p95 | FPR @0.78 (QQP) |
|---|---|---|---|
| 100 | 0.343 | 0.505 | 0.000 |
| 500 | 0.463 | 0.661 | 0.032 |
| 1 000 | 0.508 | 0.763 | 0.048 |
| 3 000 | 0.575 | 0.882 | 0.108 |
| ~5 000 | 0.606 | 0.903 | — |

**Drift ≈ 0.16 per decade of corpus size, and QQP and STS-B agree independently** (STS-B: 0.372 → 0.549 over the
same span). At 3 000 sentences the **p95 of "best match for unrelated text" is 0.88 — above our 0.78 confident
cutoff**, i.e. 5% of completely unrelated text would be labelled *confident*. The threshold holding FPR ≤5% moves
0.66 → 0.90 across the sweep. A single fixed cutoff cannot serve both a 3-reference check and a 6 000-sentence
academic corpus.

**Shipped:** `confident(N) = clamp(base + 0.06·log10(N/500), base, 0.92)`. `k=0.06` is **deliberately far below the
measured drift** — this counteracts part of the effect rather than pretending to model it, because the probe is
the paraphrase pillar alone on two datasets. Risk direction is the safe one: it can only move a match
`confident → review`; the reporting floor is untouched and nothing is hidden, so the failure mode is "we asked you
to check something we were unsure of", never a false clean. It is visible rather than silent — the result carries
the applied cutoff, the base, and `corpus_sentences`; a warning states the raise; the report footer explains why
in plain language. Rerank re-decides the band against the *same* applied cutoff.

**Caveat that makes this conservative:** the probe's distractors are *unrelated* sentences, while production
sources were **retrieved by similarity** and are topically close. The real effect is therefore likely **larger**,
not smaller. Re-measure against the full matcher once rerank is default-on — that is now the TODO, replacing the
vaguer "re-derive the cutoff" item.

Tests 165 → **180**. Lint clean.

---

## 2026-09-06 (cont.) — W8 triage + coach card, and the embedding cache (ADR-0022 · ADR-0023)

**W8 — triage is the product.** Detection alone tells an author *that* a passage matched, which is the anxious,
non-actionable output PRISM exists to replace. `services/triage.py` classifies every match into one of **8
remediation types with priorities**, from four auditable signals: quotation marks around the span, citation markers
in the containing paragraph (numeric / author-year / narrative / superscript), the ADR-0017 confidence band, and how
many sources share the same verbatim text. **Rules, not a model** — reproducible, explainable to the user, testable
per rule; an LLM making a judgement that shapes what someone changes in their manuscript would be unaccountable.
W9 will *phrase* these with gpt-4o-mini; the rules stay the backbone.

Each type ships plain-language *what* + *honest fix* text, and **a CI test asserts that text never suggests
evasion** ("lower the score", "beat the checker", "humanize") — the ADR-0014 boundary enforced by the build rather
than by good intentions. Labels describe the text, never the person ("Word-for-word, not cited"), and each card
lists the signals it used, so a wrong call is visibly wrong. UI: a prioritised **"What to fix"** panel, a badge per
match row, and a **coach card** that puts the fix above the evidence; the report gained the same. Verified in a real
browser (2/2 specs, 0 console errors) and visually — the screenshot is in `e2e/shots/`.

**ADR-0023 — the embedding cache, from a measurement rather than a hunch.** W4b's 50 s check prompted a direct
benchmark: **6 000 sentences take 77–93 s to embed** on this 12-thread CPU (batch 64 fastest; 128 and 256 *worse*).
Downloads were never the bottleneck. So: a process-wide LRU keyed by **(model, sha1(sentence))** — text, not source
identity, because the relevance budget picks a different subset per manuscript; source sentences only, because the
manuscript's own sentences are single-use.

| | |
|---|---|
| first check (1 800 source sentences, 2 papers) | **39.3 s** — 0 hits / 1 800 misses |
| re-check after editing the manuscript | **6.6 s** — 1 800 hits / 0 misses |
| | **6.0× faster, 32.8 s saved** |

That is exactly the product's core loop (W10's before/after re-check). **A cold first check is unchanged** — this
buys repeats, and the docs say so. Bounded in *entries* (default 50 000 ≈ 75 MB) so the ceiling does not move when
the model's dimensionality does; `PRISM_EMBEDDING_CACHE_ENTRIES=0` disables it; any failure in the cache path
degrades to a plain embed (tested); hit rate is on `/health` because an operator tuning the box should not guess.

**Bug found by the tests, worth remembering:** `EmbeddingCache` defines `__len__`, so an *empty* cache is falsy and
`cache = cache or get_cache()` silently discarded an injected cache and wrote to the global singleton. Six tests
failed with zeroed stats and no traceback, because the fail-soft `except` swallowed nothing — there was no
exception, just the wrong object. Fixed with `is None`. The fail-soft wrapper made a real bug *quieter*, which is
worth watching for elsewhere.

Tests 130 → **165**. Lint clean. Licence added the same day: **PolyForm Noncommercial 1.0.0** (verbatim SPDX text,
`NOTICE` with the Required Notice, contributions accepted under the same terms) — owner follow-ups (legal copyright
holder; consent from three past teammates for ~176 surviving boilerplate lines) are in TODO.

---

## 2026-09-06 (cont.) — W4b retrieval depth: Semantic Scholar + open-access full text (ADR-0021)

**Built:** `services/fulltext.py` (safe OA-PDF fetcher: https-only, private hosts refused before/after redirects,
15 MiB streaming cap, `%PDF` sniff, our parser's caps, 1 h cache of hits *and* misses) and the corpus refactor:
providers take a `ProviderContext` and return `Candidate`s (source + PDF links, unioned across providers on dedup);
a keyed **Semantic Scholar** provider (skipped without `PRISM_S2_API_KEY` — unauthenticated is 429); up to 8 OA
candidates per check chosen by lexical overlap with the document are downloaded concurrently and matched in **full
text**. `SourceDoc.kind ∈ {fulltext, abstract}` flows to `sources`/`per_source`, the UI ("abstract only" tag) and the
report's coverage sentence. Thread pools now propagate contextvars so fetch/provider log lines carry the job id.
Tests 105 → **130**.

**Live run (academic E2E spec, real OpenAlex + arXiv, this machine):**
| | |
|---|---|
| candidates | 14 (2 queries) → **2 upgraded to full text** |
| safety paths hit by real data | Wiley + Cochrane **403** (paywalled "OA" links) · arXiv `0901.0512v4` **39.6 MB declared > 15 MiB cap** · `hdl.handle.net` landing page **not a PDF** (`<!DOCTYP`) · Springer **read timeout 15 s** |
| wall time | **50.4 s** (was 10.4 s abstract-only): retrieval + fetches ≈ 16 s, then ≈ 28 s matching — two full papers push the source-sentence budget to its 6 000 cap, and embedding 6 000 sentences costs ≈ 25 s on this CPU |
| spec | PASS (match found, attributed, linked; 0 page errors) |

**Honest reading of the latency:** the feature works and refuses exactly what it should, but full text moves a check
from "seconds" to "most of a minute" on a laptop CPU, and the shared-vCPU VPS will be slower. The cost is bounded by
`max_source_sentences` (the embed cap), *not* by how many PDFs we fetch — so the levers are that cap and an
embedding cache keyed by source URL (a popular paper embedded once). Both are W6 decisions to be made from
measurements on the real box, not here. Defaults left at 8 docs / 6 000 sentences; both are settings.

---

## 2026-09-06 — Industry-grade pass: audit → re-architecture → gates in CI (ADR-0018 · 0019 · 0020)

**Trigger:** a full staff-level audit of the codebase against production standards (architecture, code quality,
security, testing, performance, data, observability, DevOps, docs, API/UX). Verdict: the *core* (matcher, pipeline,
modelhub, eval harness, ADR discipline) was sound; everything at the *edges* was not — and several documents said
things the code contradicted. Owner authorised a full implementation pass with my judgement on decisions.

**What the audit found that was embarrassing (all fixed today):**
- The UI said *"all offline, on your machine"* and *"Local engine · offline"* while uploading manuscripts to a
  Render server and holding them in RAM indefinitely. The README quoted the P=1.00/FPR=0.00 synthetic number that
  ADR-0017 bans, and linked a live demo that `SECURITY.md` said must not exist. `SECURITY.md` described bugs fixed
  weeks earlier as current. `PROJECT_BRIEF`/`TODO`/`CLAUDE.md` were two weeks stale.
- **45,099 tracked files** (33 MiB) of the PAN-2023 corpus — wrong task, banned by ADR-0016, and not ours to redistribute.
- The job queue was **unbounded**: each queued check could hold ~520 MB of upload; twenty `curl`s ≈ 10 GB on an 8 GB box.
- Seven legacy stylometry endpoints ran CPU-bound work synchronously inside `async` handlers, blocking every
  concurrent request, for an engine measured near-noise and no longer in the product.
- The legacy PDF parser **dropped every paragraph under 80 characters** — for a plagiarism checker, passages never
  checked. Its documented `unstructured` pass never ran (dependency absent).
- The matcher truncated large reference sets to the **first 6000 sentences in upload order** — later uploads were never compared.
- The Dockerfile was broken in two ways nobody could see because CI never built it (Python 3.11 vs 3.12; spaCy
  model 3.7.1 vs `spacy>=3.8`). The "real" quality gate (`eval.run_pairs --gate`) was not in CI and, at its
  provisional thresholds, would have failed every product-relevant dataset.

**Decisions taken (mine, under the owner's blanket authority; each recorded as an ADR):**
- **Delete the legacy engine** (ADR-0018) rather than flag it: −7,236 lines, seven dependencies, a compiler, and
  the whole blocking-handler class of bug. It lives in git history.
- **Re-architect the edges, keep the core** (ADR-0019): `app/` (settings · Pydantic contract · request-id · body
  guard · rate limit · health · factory) + `worker/` (bounded executor → 503, TTL store + cache, runner) +
  `ParseStage` with a purpose-built parser. Memory is now `max_pending_jobs × max_request_bytes` — arithmetic.
- **Gates as data, at the confident cutoff, from the measured baseline** (ADR-0020): `eval/gates.json`, run in CI on
  STS-B/MRPC/QQP. PAWS reported, not gated. Relevance-based (TF-IDF) source budgeting replaces first-N.
- **Not decided by me (owner's call, flagged in TODO):** the LICENSE; whether to rewrite history to purge PAN;
  confirming the old Vercel/Render demo is down.

**Verification (all on this machine, today):**
| check | result |
|---|---|
| `ruff check .` | clean (blocking in CI) |
| `pytest` | **105 passed** (was 57); coverage 87% → CI floor 80% |
| `scripts/eval_matcher.py` (smoke) | PASS |
| `eval.run_pairs stsb mrpc qqp --gate` | **all three gates PASS**, reproducing the 2026-08-30 baseline exactly (STS-B R=0.901/FPR=0.097 · MRPC R=0.785/FPR=0.442 · QQP R=0.856/FPR=0.257 @0.78) |
| Browser E2E (`e2e/run.mjs`) against live `/api/v1` | **2/2 offline specs PASS**, 0 console/page errors; **academic spec PASS** (14 OpenAlex+arXiv sources, attributed + linked) |
| Live backend log | `request_id`/`job_id` on every line; a check took 0.54 s (refs) / 10.4 s (academic, network-bound) |
| **CI, all five jobs** | **green** on `62d1b2cc` — Backend 130 s · Docker 380 s · Benchmark gate 176 s · Browser E2E 132 s · Frontend 10 s |
| Docker image | **built and smoke-tested in CI** (run 33991664613, `docker` job 380 s): image builds from the lockfile, container answers `/health/ready` 200 with the baked model, runs as non-root. Could not be built on this dev machine (Docker egress times out on PyPI/apt) — CI is the authority for the image. |

**Honest notes:** the first Docker build failed on `apt-get` because this machine's Docker egress blocks port 80
— which was a good reason to remove the apt layer entirely (Python health probe; smaller image). The first E2E run
failed only because Playwright's new version needed its browser binary; the specs themselves were green once installed.
The benchmark gates are *tripwires at today's measured level*, not targets — the FPR on same-topic negatives is still
high (MRPC 0.44 at the confident cutoff), which is exactly why the review band exists and why W4b/W5/rerank matter.

**History rewrite (owner decision, same day):** purged `pan23-multi-author-analysis/`, `research/datasets/pan/` and
`.gemini/` from *all* history with `git filter-repo` (pack 33.65 MiB → 2.77 MiB; 75 commits — two that only touched
those paths became empty and were dropped). Every SHA changed; ADR-0018's reference was updated. A full pre-rewrite
backup bundle is kept outside the repo (`D:\PRISM-UI\prism-pre-filter-20260906.bundle`). Anyone with an older clone
must re-clone; GitHub drops the unreachable objects on its next gc (support can force it). PAN data also deleted from disk.

**Still open (in priority order):** W4b retrieval depth (Semantic Scholar + OA full text) → W6 first deploy on the
real VPS via `deploy/README.md` and **measure rerank latency there** → re-derive the confident cutoff once rerank is
default-on → W5 GPU session (human) → W7 accounts + Postgres `JobStore` behind the Protocol that now exists.

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
3. **UI + report now render the band** (same day). Badge, muted/dashed highlight (never a severity colour),
   hatched "Needs review" bar, chip, plain-language note, and an explicit "Inconclusive — needs your review"
   callout in the detail pane; the downloadable report gets the same treatment plus a corrected method footer
   (states **both** cutoffs instead of the stale "≥ 0.66") and an explicit **coverage limitation** (uploads +
   OpenAlex/arXiv only — not the full web or paywalled journals; a clean result is not a guaranteed pass).
   Verified end-to-end: a 0.7593 reword → `review` (review_pct 68.97, confident_pct 0.0) where it would
   previously have been shown as a confirmed 76% match; verbatim stays `confident`. All 8 JS files pass `node --check`.

**W5 training kit prepared** (`backend/training/`): `finetune_cross_encoder.py` + README. It trains the one
sanctioned fine-tune (ADR-0016) on a free Colab/Kaggle T4 **and enforces the ship/no-ship gate itself** — FPR@0.66
must not rise, best-F1 must improve by ≥0.01, Brier must not worsen; exit 2 = "trained fine, didn't earn its place".
It imports the repo's own `eval/metrics.py`, so its numbers are directly comparable to `eval.run_pairs` (no
reimplementation drift), scores the pretrained baseline *in the same run* (apples-to-apples), and trains on **train**
splits while evaluating on the **validation** splits our published numbers came from (no leakage). 8 unit tests cover
the gate logic (`tests/test_w5_gate.py`), including that a raised FPR fails even when F1 improves and that an
unchanged result never ships. **Deviation from ADR-0016, stated plainly:** it does a **full fine-tune, not LoRA** —
the cross-encoder is roberta-base (~125M), which trains fine on a free T4; LoRA exists for much larger models and
would add a `peft` dependency for no benefit here.

**W4 rerank stage wired (opt-in).** `RerankStage` is now a real stage, not a skeleton: it runs the measured
cross-encoder over **borderline** semantic matches only (cosine in [0.60, 0.92]; verbatim is exact overlap and is
never reranked; capped at 200 pairs, highest-similarity first) — because a cross-encoder costs one forward pass per
pair on CPU. It **preserves the displayed bi-encoder `similarity`** (which the percentages and UI are built on) and
records `rerank_score`, using it only to re-decide the ADR-0017 `confidence` band; confidence aggregates are then
recomputed via a shared `confidence_breakdown()` helper so they can't go stale. Fails soft (warns, leaves matches
untouched) if the model can't load. **Opt-in via `PRISM_RERANK=1`** — deliberately off by default until the <60s
latency budget is measured on a real 20-page PDF, since flipping it silently would change response time for users.
6 unit tests with a fake cross-encoder cover promote/demote, the skip rules, the cap, fail-soft, and aggregate
recomputation.

**Rerank latency measured (dev machine, ~11-page / 5.2k-word doc, 6 sources):**
| | wall time | matches | reranked |
|---|---|---|---|
| rerank OFF | **2.82s** | 515 | — |
| rerank ON | **11.03s** | 515 | 126 |
**+8.2s for 126 pairs ≈ 65 ms/pair.** The `max_pairs=200` cap bounds rerank cost at ~13s *regardless of document
length*, so the check stays well inside the <60s budget on this hardware. (The confident→review shift in that run
is **not** a quality signal — the synthetic doc repeats filler that also appears in the sources, so nearly every
sentence matches. Timing is valid; that percentage is not.)
**Decision: keep it opt-in for now.** Two honest reasons: (1) this was measured on a dev machine, while production
is a shared-vCPU Hetzner CX32 that will be materially slower — flipping a latency-affecting default on untested
hardware is the kind of unmeasured assumption we've been avoiding; (2) it adds a ~500MB model to the deploy image.
**Flip it at W6 (deploy) after measuring on the actual VPS.**
Prioritisation note: candidates are reranked **highest-similarity first**, so when the cap bites the budget is spent
verifying the *strongest* claims — the ones currently labelled `confident`, where a wrong call is a false
accusation. A missed promotion (leaving something in `review`) is the far cheaper error.

**Still open:** measure rerank on the real VPS at W6 → then default it on; run the W5 notebook (needs a GPU session
— cannot be driven from this environment); re-derive the cutoff once rerank is default-on, accounting for the
**max-over-sources** upward bias (pairwise 0.78 is a lower bound).

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
