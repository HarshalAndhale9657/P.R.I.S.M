# 🎤 P.R.I.S.M. — Round 1 Judge Q&A Cheat Sheet

> Keep answers **concise (30-60 seconds max)**. If asked to elaborate, go deeper.

---

## 🏗️ ARCHITECTURE & SYSTEM DESIGN

---

### Q1: "Walk me through your architecture in 60 seconds."

> **A:** P.R.I.S.M. uses a **6-stage pipeline**:
> 1. A PDF comes in and gets **dual-pass parsed** — `unstructured` handles multi-column reading order, PyMuPDF isolates the bibliography.
> 2. Each paragraph goes through **spaCy** which extracts 7 content-independent linguistic features — things like function word ratios, passive voice frequency, and Yule's K lexical richness.
> 3. Those features form a matrix that's fed into **HDBSCAN**, a density-based clustering algorithm that automatically detects how many authors contributed — without us telling it how many to look for. Any paragraph it can't cluster gets flagged as **Cluster -1** — a stylistic anomaly.
> 4. **GPT-4o-mini** then explains *why* those flagged sections differ in natural language.
> 5. We run **citation forensics** using regex to detect temporal inconsistencies — like a 2024 paper suddenly citing only 1990s literature.
> 6. Flagged paragraphs get embedded locally using **all-MiniLM-L6-v2** and compared against **arxiv** papers via cosine similarity to find the original source.
> The result is a **forensic report** with provable math + human-readable AI reasoning.

---

### Q2: "Why did you use a hybrid approach instead of just using GPT for everything?"

> **A:** Three reasons:
> 1. **Determinism** — GPT gives different outputs for the same input. HDBSCAN gives the *exact same clusters* every time. In forensics, consistency is everything.
> 2. **Provability** — When a judge or professor asks "how did you detect this?", we can show the mathematical feature matrix and clustering — not just "GPT said so."
> 3. **Efficiency** — We only call GPT on paragraphs that HDBSCAN already flagged. Instead of 80 API calls analyzing every paragraph, we make maybe 5-8 calls only on anomalies. Math is free, AI is targeted.

---

### Q3: "What happens if the PDF has a multi-column layout? Most parsers fail at that."

> **A:** Exactly why we don't use pdfplumber or PyPDF2. We use the **`unstructured`** library which understands spatial layout coordinates. It doesn't just read text left-to-right — it identifies column boundaries and reads each column sequentially in the correct logical order. We also have a **3-tier fallback**: if `unstructured` fails, we fall back to PyMuPDF raw extraction, and if that fails too, we brute-force chunk the text by character count. The frontend shows a "degraded mode" warning so the user knows.

---

### Q4: "Explain your data flow — what format does data take at each stage?"

> **A:**
> - **Input**: Raw PDF binary bytes
> - **After parsing**: Array of `{block_id, text, page_number}` objects + separate references array
> - **After spaCy**: N×7 numerical feature matrix (floats) — each row = one paragraph, each column = one linguistic feature
> - **After HDBSCAN**: Same paragraphs enriched with `cluster_id` (integer, -1 = anomaly)
> - **After GPT**: Paragraphs enriched with `style_explanation` and `comparison_reasoning` (strings)
> - **After citations**: Paragraphs enriched with `median_citation_year` and `temporal_anomaly` (boolean)
> - **After source tracing**: Flagged paragraphs enriched with `source_matches: [{title, url, similarity}]`
> - **Final output**: Full JSON payload → rendered in frontend dashboard

---

### Q5: "Why FastAPI and not Flask or Django?"

> **A:** FastAPI gives us three things Flask doesn't:
> 1. **Native async** — our pipeline has blocking NLP operations and API calls. We use `asyncio.to_thread()` to run spaCy and HDBSCAN without blocking the event loop.
> 2. **Pydantic validation** — every JSON response is strictly typed. The frontend always gets exactly what it expects. No `undefined` crashes.
> 3. **Auto-generated docs** at `/docs` — during live demo, judges can see and test every endpoint directly. Free Swagger UI.

---

## 🔬 TECHNICAL DEEP DIVES

---

### Q6: "How does HDBSCAN work? Why not K-Means?"

> **A:** K-Means has three fatal flaws for our use case:
> 1. You must specify K (number of authors) beforehand — which we don't know.
> 2. It forces every paragraph into a cluster, even genuinely anomalous ones.
> 3. It assumes spherical cluster shapes.
>
> **HDBSCAN** works differently — it treats clusters as **dense regions separated by sparse gaps**. It builds a hierarchy of density levels and automatically finds the most stable clusters. The key innovation: paragraphs that don't fit any cluster get labeled as **noise (Cluster -1)**. In our context, noise = "this paragraph's writing style doesn't match anyone else's" = high probability of being stitched from another source.

---

### Q7: "What are the 7 stylometric features you extract? Why these specifically?"

> **A:** We extract features that are **content-independent** — they don't change based on what the paragraph is about, only based on *who wrote it*:
> 1. **Average sentence length** — some authors write long sentences, others short
> 2. **Average word length** — indicates vocabulary complexity
> 3. **Pronoun ratio** — how often they use "I", "we", "they"
> 4. **Preposition ratio** — "of", "in", "for" — highly subconscious
> 5. **Conjunction ratio** — "and", "but", "however"
> 6. **Passive voice percentage** — academic writing varies hugely here
> 7. **Yule's K lexical richness** — measures vocabulary diversity, resistant to text length fluctuation
>
> We specifically avoid content words like nouns and adjectives because those change by topic, not by author.

---

### Q8: "What is Yule's K and why is it better than Type-Token Ratio?"

> **A:** Type-Token Ratio (unique words ÷ total words) is unreliable because it decreases as text gets longer — longer paragraph = artificially lower score. **Yule's K** corrects for this. It's defined as:
>
> `K = 10000 × (M2 - M1) / M1²`
>
> where M1 is total word count and M2 is the sum of squared word frequencies. It gives a stable richness score regardless of paragraph length, making it fair to compare a 50-word paragraph against a 200-word one.

---

### Q9: "How do you handle citation forensics? What's the temporal analysis?"

> **A:** We use **deterministic regex** — not GPT — to extract inline citations like `(Smith, 2019)` or `(et al., 2005)`. For each paragraph, we calculate the **median citation year**. Then we compare: what's the median year for the main author's cluster (Cluster 0) versus the median year for noise paragraphs (Cluster -1)? If a noise paragraph cites papers from 15+ years earlier than the rest of the paper, that's a **chronological anomaly** — strong evidence of stitching from an older source.

---

### Q10: "How does your source tracing work?"

> **A:**
> 1. We take each flagged paragraph and use spaCy to extract **noun chunks** (key phrases like "neural network optimization").
> 2. We query the **arxiv API** with the top 3 noun chunks.
> 3. We embed the flagged paragraph AND each arxiv abstract using **all-MiniLM-L6-v2** into 384-dimensional vectors — locally, no API calls.
> 4. We compute **cosine similarity** between the vectors.
> 5. If similarity > 0.75, we report it as a probable source with a direct link to the arxiv paper.
> 
> We use the **tenacity** library for exponential backoff so arxiv rate limits don't crash us.

---

### Q11: "Why local embeddings (all-MiniLM-L6-v2) instead of OpenAI embeddings?"

> **A:** For source tracing we need to embed potentially 50+ arxiv abstracts for each flagged paragraph. Using OpenAI embeddings would mean dozens of API calls with latency and rate limit risk. **all-MiniLM-L6-v2** runs locally at **14,000 sentences per second** on a standard CPU, costs $0, and produces 384-dimensional vectors with comparable semantic accuracy. It's also deterministic — same input, same vector, every time. We eliminate an entire point of failure from the pipeline.

---

## 🎯 UNIQUENESS & DIFFERENTIATION

---

### Q12: "How is this different from Turnitin or other plagiarism checkers?"

> **A:** Turnitin and traditional tools do **lexical matching** — they compare your text against a database looking for exact or near-exact overlaps. They completely fail against **stitched plagiarism** where the plagiarist paraphrases, translates, or splices content intelligently.
>
> P.R.I.S.M. doesn't look at *what* you wrote — it looks at *how* you write. Writing style is like a fingerprint — your sentence structure, function word usage, and vocabulary diversity are subconscious. When a paragraph from a different author is spliced in, these stylometric features shift measurably. We detect the shift mathematically, prove it with clustering, and explain it with AI.

---

### Q13: "What's your competitive edge over teams using pure GPT approaches?"

> **A:** Pure GPT approaches have three weaknesses:
> 1. **Non-deterministic** — run the same analysis twice, get different results. Not acceptable in forensics.
> 2. **Expensive** — analyzing every paragraph costs ~$0.15-0.30 per document.
> 3. **Unexplainable** — "GPT says it's plagiarized" isn't evidence.
>
> Our **hybrid approach** gives us the best of both worlds: **mathematical proof** from HDBSCAN that's deterministic and explainable, plus **natural language reasoning** from GPT that makes it human-readable. No other team will have both.

---

### Q14: "What makes P.R.I.S.M. novel? What's your 'wow factor'?"

> **A:** Three things:
> 1. **Dual-engine detection**: Math (HDBSCAN) catches the anomaly, AI (GPT) explains it. No existing tool does both.
> 2. **Zero-knowledge author count**: HDBSCAN determines how many authors contributed without us specifying. It discovers the truth from the data itself.
> 3. **Forensic evidence chain**: We don't just say "this is suspicious." We show: this paragraph has different function word ratios (math proof) → style shifted at this boundary (GPT reasoning) → it cites 1990s papers while the rest cites 2020s (temporal anomaly) → here's the arxiv paper it was copied from (source match at 87% similarity). **That's a prosecutable evidence chain.**

---

## ⚠️ EDGE CASES & ROBUSTNESS

---

### Q15: "What happens if I upload a completely genuine, single-author paper?"

> **A:** That's the happy path. HDBSCAN will put all paragraphs into **Cluster 0** — one author. Citation years will be consistent. No paragraphs flagged. The frontend renders the entire document in a single color with an integrity score of 10/10. We explicitly handle this: if HDBSCAN assigns >80% of paragraphs to noise, we know the algorithm is overfitting, so we override to Cluster 0. **Correctly verifying a clean paper is just as important as detecting a dirty one.**

---

### Q16: "What if the PDF is scanned/image-based with no selectable text?"

> **A:** Our `unstructured` library has a `"hi_res"` strategy that can trigger OCR via Tesseract. However, in a hackathon demo context, we detect this case explicitly — if parsing yields zero narrative blocks, we return a clear error: "This PDF contains no extractable text. It may be a scanned document." The frontend shows a friendly error card, not a crash.

---

### Q17: "What if OpenAI's API goes down during your demo?"

> **A:** This is exactly why we built the hybrid architecture. The **entire math layer** — PDF parsing, spaCy features, HDBSCAN clustering, citation regex, local embeddings, arxiv search — runs **100% locally** with zero API dependencies. If OpenAI goes down, we still show:
> - Authorship heatmap with cluster colors
> - Feature charts
> - Citation timeline
> - Source matches from arxiv
>
> The only thing we lose is the natural language GPT reasoning. We degrade gracefully — we set a `gpt_available: false` flag and the frontend shows "AI reasoning unavailable" cards. **The core forensic analysis still works.**

---

### Q18: "How do you handle very short papers — like 2-3 paragraphs?"

> **A:** HDBSCAN needs a minimum number of points to form clusters — our default `min_cluster_size` is 3. If the paper has fewer than 6 paragraphs (2 × min_cluster_size), we skip clustering entirely and return a warning: "Document too short for reliable multi-author detection." We still run citation forensics and source tracing — those work on any length.

---

## 💻 TECH STACK & IMPLEMENTATION

---

### Q19: "What's in your requirements.txt?"

> **A:** Core dependencies:
> - `FastAPI` + `uvicorn` — API server
> - `unstructured[pdf]` + `PyMuPDF` — dual-pass PDF parsing
> - `spaCy` (`en_core_web_sm`) — NLP feature extraction
> - `hdbscan` + `scikit-learn` — clustering + scaling
> - `sentence-transformers` (`all-MiniLM-L6-v2`) — local embeddings
> - `openai` — GPT-4o-mini, GPT-4o
> - `arxiv` + `tenacity` — source search with retry
> - `nltk` — sentence tokenization

---

### Q20: "How is your team structured? Who does what?"

> **A:**
> - **M1 (Captain)**: spaCy feature engine, HDBSCAN clustering, GPT prompts, forensic report generator
> - **M2 (Engine)**: PDF parser (dual-pass), citation regex, edge case handling
> - **M3 (Pixel)**: All frontend — upload UI, authorship heatmap, charts, dashboard, report view
> - **M4 (Bridge)**: FastAPI endpoints, source tracer (arxiv + embeddings), pipeline wiring
> - **M5 (Shield)**: Test PDFs, deployment (Render + Vercel), README, demo video

---

### Q21: "What AI tools are you using and how?"

> **A:** We use three OpenAI models:
> 1. **GPT-4o-mini** — style profiling and pairwise comparison at flagged boundaries. Fast, cheap, precise.
> 2. **GPT-4o** — final forensic report synthesis. Needs the smartest model to weigh all evidence and produce a verdict.
> 3. **all-MiniLM-L6-v2** — local, open-source embedding model for semantic source tracing. No OpenAI dependency.
>
> **Key design decision**: GPT never does the detection — math does. GPT only explains and synthesizes. This means our core analysis works even without AI.

---

## 📊 METRICS & SCORING

---

### Q22: "How do you quantify your integrity score?"

> **A:** The integrity score (0-10) is a weighted composite:
> - **40%** — HDBSCAN cluster analysis (% of paragraphs in noise cluster)
> - **25%** — Citation temporal consistency (deviation from baseline year)
> - **20%** — Stylometric feature variance (how much features shift across paragraphs)
> - **15%** — Source match severity (highest cosine similarity to an arxiv paper)
>
> 10/10 = completely clean. Below 5 = high suspicion. Below 3 = strong evidence of stitching. GPT-4o generates the final reasoning to explain the score.

---

### Q23: "What's your expected latency? How fast does analysis run?"

> **A:**
> - PDF parsing: **<2 seconds**
> - spaCy feature extraction (40 paragraphs): **<1 second**
> - HDBSCAN clustering: **<0.5 seconds**
> - GPT reasoning (5-8 flagged boundaries): **~5-10 seconds**
> - Citation forensics (regex): **<0.5 seconds**
> - Source tracing (arxiv + embeddings): **~10-15 seconds**
> - Report generation (GPT-4o): **~3-5 seconds**
> - **Total: ~20-30 seconds end-to-end**

---

### Q24: "How did you test this? What test data did you use?"

> **A:** We prepared three test PDFs:
> 1. **Genuine paper** — single author, clean writing. Should score 9-10/10.
> 2. **Stitched paper** — we manually combined paragraphs from 3 different arxiv papers into one document. Should score 2-4/10 with flagged sections and source matches.
> 3. **Short paper** — only 3 paragraphs. Tests the graceful degradation path.
