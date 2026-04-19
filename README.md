<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/spaCy-3.7-09A3D5?style=for-the-badge&logo=spacy&logoColor=white" alt="spaCy"/>
  <img src="https://img.shields.io/badge/HDBSCAN-Density_Clustering-FF6F00?style=for-the-badge" alt="HDBSCAN"/>
  <img src="https://img.shields.io/badge/GPT--4o-Reasoning-412991?style=for-the-badge&logo=openai&logoColor=white" alt="GPT-4o"/>
  <img src="https://img.shields.io/badge/DevClash-2026-E91E63?style=for-the-badge" alt="DevClash 2026"/>
</p>

<h1 align="center">P.R.I.S.M.</h1>
<h3 align="center">Plagiarism Recognition via Integrated Stylometric Mapping</h3>

<p align="center">
  <em>A forensic document analysis engine that detects <strong>stitched plagiarism</strong> in academic papers<br/>through mathematical stylometry, density-based clustering, and AI-powered reasoning.</em>
</p>

<p align="center">
  <strong><a href="https://p-r-i-s-m-psi.vercel.app/">🌐 Live Demo</a></strong> •
  <a href="#the-core-problem">Problem</a> •
  <a href="#our-approach">Approach</a> •
  <a href="#system-architecture">Architecture</a> •
  <a href="#algorithmic-innovations">Algorithms</a> •
  <a href="#deliverables">Deliverables</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#getting-started">Setup</a> •
  <a href="#api-reference">API</a>
</p>

---

## The Core Problem

Modern academic plagiarism has evolved far beyond copy-paste. Traditional detection tools like Turnitin perform **lexical matching** — they check whether a sentence has appeared in a known corpus. This approach fails catastrophically against a growing pattern called **stitched plagiarism**:

> A student assembles a paper by splicing paragraphs from multiple existing publications. Each section is paraphrased, machine-translated, or processed through AI paraphrasers (Quillbot, ChatGPT). No single sentence matches any known source verbatim. The fraud lies not in *what* was written, but in *how it was assembled*.

**Why existing tools fail:**

| Detection Method | What It Checks | Blind Spot |
|:---:|:---:|:---:|
| Turnitin / Moss | Exact string overlap against a corpus | Paraphrased or translated content scores 0% |
| GPTZero / ZeroGPT | Statistical perplexity for AI-generated text | Fails on human-written stitched content |
| Self-plagiarism checkers | Cross-referencing an author's own past work | Cannot detect *multi-author* splicing |

**P.R.I.S.M. asks a fundamentally different question:**

> *"Does this document read like it was written by one person?"*

Rather than comparing text against external corpora, P.R.I.S.M. analyzes **internal stylometric consistency** — the subconscious linguistic fingerprint that every author leaves behind. When a student stitches someone else's work into their own, the mathematical signature of the writing shifts at the boundary. P.R.I.S.M. detects, localizes, and explains those shifts.

---

## Our Approach

P.R.I.S.M. uses a **Hybrid Dual-Engine Architecture** that separates mathematical proof from AI explanation:

```
┌─────────────────────────────────────────────────────────────┐
│                    MATH provides the PROOF                  │
│            spaCy · HDBSCAN · Yule's K · Burstiness         │
│                                                             │
│        Deterministic · Reproducible · Zero API Cost         │
├─────────────────────────────────────────────────────────────┤
│                  AI provides the EXPLANATION                │
│            GPT-4o-mini · GPT-4o · Embeddings                │
│                                                             │
│        Natural Language · Prosecutable · Contextual         │
└─────────────────────────────────────────────────────────────┘
```

**Why this matters:** An AI-only approach is non-deterministic — you cannot accuse a student of academic misconduct because "the AI said so." P.R.I.S.M. ensures that every flag is backed by reproducible mathematical evidence. The AI layer only activates *after* the math has identified an anomaly, and its role is to explain *why* the mathematical shift occurred in human-readable terms.

---

## System Architecture

```
                              ┌─────────────┐
                              │  PDF Upload  │
                              └──────┬───────┘
                                     │
                    ╔════════════════╧════════════════╗
                    ║   STAGE 1: DUAL-PASS PDF PARSER ║
                    ║─────────────────────────────────║
                    ║  Pass A ─ unstructured           ║
                    ║    └─ NarrativeText extraction   ║
                    ║    └─ Multi-column aware         ║
                    ║  Pass B ─ PyMuPDF                ║
                    ║    └─ Bibliography bbox isolation║
                    ║    └─ Font-size heuristics       ║
                    ║  Fallback Chain:                 ║
                    ║    unstructured → PyMuPDF raw    ║
                    ║    → pdfplumber → 1000-char chunk║
                    ╚════════════════╤════════════════╝
                                     │
              ╔══════════════════════╧══════════════════════╗
              ║   STAGE 2: STYLOMETRIC FEATURE EXTRACTION   ║
              ║─────────────────────────────────────────────║
              ║  spaCy en_core_web_sm (zero API calls):     ║
              ║    1. avg_sentence_length  — complexity      ║
              ║    2. avg_word_length      — sophistication  ║
              ║    3. pronoun_ratio        — tone signature  ║
              ║    4. preposition_ratio    — syntax habits   ║
              ║    5. conjunction_ratio    — clause linking  ║
              ║    6. passive_voice_pct    — formality       ║
              ║    7. yules_k             — lexical richness ║
              ║    8. burstiness_score    — AI detection     ║
              ║  + PCA-reduced OpenAI semantic embeddings    ║
              ║  Output: N × 11 feature matrix              ║
              ╚══════════════════════╤══════════════════════╝
                                     │
              ╔══════════════════════╧══════════════════════╗
              ║   STAGE 3: HDBSCAN AUTHORSHIP CLUSTERING    ║
              ║─────────────────────────────────────────────║
              ║  StandardScaler → HDBSCAN (EOM selection)   ║
              ║    └─ Auto-detects author count (no K)      ║
              ║    └─ Cluster -1 = noise = FLAGGED          ║
              ║    └─ Boundary detection on transitions     ║
              ║    └─ Confidence scoring (probability +     ║
              ║       noise penalty + cluster bonus)        ║
              ║  Edge cases:                                ║
              ║    └─ Noise saturation (>90%) → override    ║
              ║    └─ Zero-variance features → bypass       ║
              ║    └─ Short papers (<5 ¶) → skip            ║
              ╚══════════════════════╤══════════════════════╝
                                     │
              ╔══════════════════════╧══════════════════════╗
              ║   STAGE 4: GPT STYLE REASONING              ║
              ║─────────────────────────────────────────────║
              ║  GPT-4o-mini (only on flagged boundaries):  ║
              ║    └─ Per-paragraph style profiling          ║
              ║    └─ Pairwise boundary explanation          ║
              ║  Safeguards:                                ║
              ║    └─ 30s per-call timeout + 120s batch      ║
              ║    └─ Exponential backoff on rate limits     ║
              ║    └─ Partial result delivery on failure     ║
              ╚══════════════════════╤══════════════════════╝
                                     │
              ╔══════════════════════╧══════════════════════╗
              ║   STAGE 5: CITATION FORENSICS               ║
              ║─────────────────────────────────────────────║
              ║  Deterministic regex: APA / MLA / Harvard   ║
              ║    └─ Parenthetical + narrative patterns     ║
              ║    └─ False positive filtering               ║
              ║  Temporal Analysis:                         ║
              ║    └─ Median citation year per paragraph     ║
              ║    └─ Core vs noise cluster comparison       ║
              ║    └─ Anomaly if |diff| > 10 years          ║
              ║  Citation Density Analysis:                 ║
              ║    └─ Citations per 100 words by cluster     ║
              ║  Crossref API Hallucination Detection:      ║
              ║    └─ Verifies reference existence           ║
              ╚══════════════════════╤══════════════════════╝
                                     │
              ╔══════════════════════╧══════════════════════╗
              ║   STAGE 6: SEMANTIC SOURCE TRACING          ║
              ║─────────────────────────────────────────────║
              ║  Dual-database search (anomalies only):     ║
              ║    └─ arXiv API (exponential backoff)        ║
              ║    └─ OpenAlex API (free, no auth)          ║
              ║  Multilingual MiniLM-L12-v2 embeddings:    ║
              ║    └─ 384-dim vectors, runs on CPU          ║
              ║    └─ Cosine similarity ≥ 0.50 = match     ║
              ║  Idea Triplet Extraction (anti-Quillbot):  ║
              ║    └─ Subject → Verb → Object frames        ║
              ║    └─ Overlap boosts similarity by 6%/trip  ║
              ╚══════════════════════╤══════════════════════╝
                                     │
              ╔══════════════════════╧══════════════════════╗
              ║   STAGE 7: FORENSIC REPORT SYNTHESIS        ║
              ║─────────────────────────────────────────────║
              ║  GPT-4o synthesizes all evidence streams:    ║
              ║    └─ HDBSCAN cluster analysis               ║
              ║    └─ GPT style reasoning summaries          ║
              ║    └─ Citation temporal anomalies            ║
              ║    └─ Source paper matches + similarity       ║
              ║  Output: Structured JSON report             ║
              ║    └─ Integrity Score (0.0 — 10.0)          ║
              ║    └─ Verdict: Clean / Suspicious / Flagged ║
              ║    └─ Executive Summary                      ║
              ║    └─ Evidence Breakdown by category         ║
              ║  Fallback: Rule-based scoring engine         ║
              ║    └─ 7-factor weighted penalty system       ║
              ║    └─ Works fully offline (no API needed)    ║
              ╚═════════════════════════════════════════════╝
```

---

## Algorithmic Innovations

### 1. Burstiness Score — AI Content Detection

Human writing exhibits natural variance in sentence length ("burstiness"). AI-generated text has a statistically flat sentence-length distribution. P.R.I.S.M. computes the **Coefficient of Variation** of sentence lengths per paragraph:

```
Burstiness = σ(sentence_lengths) / μ(sentence_lengths)
```

| Score | Interpretation |
|:---:|---|
| **> 0.30** | Normal human variance — natural writing |
| **< 0.30** | Artificially flat — high probability of AI generation |

When the average burstiness across multi-sentence paragraphs (≥ 2 sentences) falls below **0.30**, the system flags the document with a critical AI generation alert and applies a **6.0-point integrity deduction**.

### 2. Yule's Characteristic K — Length-Resistant Lexical Richness

Unlike the commonly used Type-Token Ratio (which deteriorates as text length increases), Yule's K provides a stable measure of vocabulary diversity:

```
K = 10000 × (M₂ - M₁) / M₁²

where:
  M₁ = total word count
  M₂ = Σ(frequency²) for each unique word
```

**Low K = rich, diverse vocabulary. High K = repetitive vocabulary.**

This metric is critical because paraphrasing tools change *which* words are used, but the underlying vocabulary diversity pattern (the author's fingerprint) is preserved.

### 3. Idea Triplet Extraction — Defeating AI Paraphrasers

AI paraphrasers (Quillbot, ChatGPT rewrites) swap vocabulary but maintain the **same logical claims**. P.R.I.S.M. extracts Subject → Verb → Object triplets from both the anomalous paragraph and potential source abstracts using spaCy dependency parsing:

```python
# Example triplets extracted from a paragraph about neural networks:
{"model_achieve_accuracy", "transformer_outperform_baseline", "attention_reduce_complexity"}
```

When triplet overlap is detected between a flagged paragraph and a source paper, the cosine similarity score is boosted by **+6% per matching triplet**, compensating for vocabulary-level obfuscation.

### 4. HDBSCAN over K-Means — Why It Matters

| Property | K-Means | HDBSCAN (our choice) |
|---|:---:|:---:|
| Requires specifying cluster count (K) | ✅ Must guess | ❌ Auto-detects |
| Assumes spherical clusters | ✅ | ❌ Arbitrary shapes |
| Handles noise naturally | ❌ | ✅ Cluster -1 = anomaly |
| Robust to varying cluster sizes | ❌ | ✅ |
| Stable with outliers | ❌ | ✅ |

HDBSCAN's native noise label (`-1`) maps directly to P.R.I.S.M.'s concept of "stylistic anomaly" — paragraphs that don't belong to any consistent authorial voice. This is the mathematical foundation behind every plagiarism flag.

### 5. Semantic Embedding Fusion — Hybrid Feature Space

P.R.I.S.M. constructs an **11-dimensional feature space** by combining:
- **8 deterministic structural features** (spaCy, zero cost)
- **3 PCA-reduced semantic embeddings** (OpenAI `text-embedding-3-small`, 1536 → 3 dims)

The semantic dimensions are **down-weighted by 80%** in the clustering step to prevent topic-based over-fragmentation — ensuring the algorithm clusters by *writing style*, not by *subject matter*.

### 6. Enterprise-Grade Fallback Chain

The entire system degrades gracefully rather than failing:

```
PDF Parsing:    unstructured → PyMuPDF → pdfplumber → raw chunking
AI Reasoning:   GPT-4o → GPT-4o-mini → rule-based scoring engine
Source Search:  arXiv + OpenAlex → offline (skip gracefully)
Embeddings:     OpenAI → paraphrase-multilingual-MiniLM-L12-v2 (local)
```

If OpenAI's API is down, the math layer, clustering, heatmap, and citation forensics **still run completely offline**. The system always produces actionable output.

---

## Deliverables

### Functional Deliverables

| # | Deliverable | Status | Description |
|:---:|---|:---:|---|
| 1 | **Dual-Pass PDF Parser** | ✅ | Multi-column aware text extraction with 4-tier fallback chain |
| 2 | **Stylometric Feature Engine** | ✅ | 11-dimensional content-independent feature extraction (8 structural + 3 semantic) |
| 3 | **HDBSCAN Authorship Clustering** | ✅ | Unsupervised author detection with automatic noise labeling and boundary detection |
| 4 | **GPT Style Reasoning** | ✅ | Natural language explanations for detected anomalies with timeout/retry safeguards |
| 5 | **Citation Forensics Engine** | ✅ | Deterministic regex extraction + temporal anomaly detection + Crossref hallucination verification |
| 6 | **Semantic Source Tracer** | ✅ | Dual-database (arXiv + OpenAlex) search with local embedding similarity and Idea Triplet anti-paraphraser |
| 7 | **Forensic Report Generator** | ✅ | GPT-4o synthesis with rule-based fallback producing integrity score (0–10) and structured evidence |
| 8 | **AI Content Detector** | ✅ | Burstiness-based sentence variance analysis to flag AI-generated text |
| 9 | **Interactive Dashboard** | ✅ | 6-panel SPA: Upload → Heatmap → Charts → Citations → Sources → Report |
| 10 | **RESTful API** | ✅ | 7 endpoints with auto-generated OpenAPI docs at `/docs` |

### Non-Functional Deliverables

| Requirement | Implementation |
|---|---|
| **Graceful degradation** | PipelineContext accumulates typed warnings; every stage can fail without crashing downstream |
| **Edge-case handling** | 15+ codified WarningCodes for empty PDFs, scanned documents, noise saturation, API timeouts, short papers |
| **Offline capability** | Math layer + clustering + citation forensics work with zero API calls |
| **Cost optimization** | HDBSCAN gates GPT calls — only anomalous paragraphs (~5%) are sent to the LLM |
| **Structured warnings** | Frontend receives machine-readable warning codes + human-readable messages for contextual UI alerts |

---

## Tech Stack

### Backend — Python / FastAPI

| Layer | Technology | Role |
|---|---|---|
| **Framework** | FastAPI 0.115 | Async endpoints, Pydantic validation, auto-generated OpenAPI docs |
| **PDF Parsing** | `unstructured` + PyMuPDF + pdfplumber | Dual-pass extraction with 4-tier fallback |
| **NLP Engine** | spaCy `en_core_web_sm` | Deterministic POS tagging, dependency parsing, sentence segmentation |
| **Clustering** | HDBSCAN + scikit-learn `StandardScaler` | Density-based unsupervised authorship clustering |
| **Local Embeddings** | `paraphrase-multilingual-MiniLM-L12-v2` | 384-dim vectors, CPU-optimized, zero API cost |
| **Semantic Embeddings** | OpenAI `text-embedding-3-small` | 1536-dim paragraph embeddings reduced to 3 via PCA |
| **AI Reasoning** | OpenAI GPT-4o-mini | Per-paragraph style profiling and boundary explanation |
| **AI Synthesis** | OpenAI GPT-4o | Final forensic report generation |
| **Source Search** | `arxiv` + OpenAlex API + `tenacity` | Exponential backoff retry for rate-limited searches |
| **Citation Verification** | Crossref API | Reference existence validation for hallucination detection |
| **Data Models** | Pydantic v2 | Typed response models, warning enums, pipeline context |

### Frontend — Vanilla Stack

| Layer | Technology | Role |
|---|---|---|
| **UI** | HTML5 / CSS3 / Vanilla JS | Zero build step, zero dependencies, instant deployment |
| **Typography** | Inter + JetBrains Mono (Google Fonts) | Premium design system with monospace data rendering |
| **Charts** | Chart.js 4.4 (CDN) | Feature trend lines, function word ratios, cluster distributions |
| **Design** | Programmatic HSL color generation | Dynamic cluster colors, gradient-based styling |

### Infrastructure

| Component | Platform |
|---|---|
| Backend Hosting | Render |
| Frontend Hosting | Vercel |
| Version Control | GitHub |

---

## Project Structure

```
P.R.I.S.M/
├── backend/
│   ├── main.py                          # FastAPI app — 7 endpoints, pipeline orchestration
│   ├── models.py                        # Pydantic models, PipelineContext, 15+ WarningCodes
│   ├── requirements.txt                 # Pinned Python dependencies
│   ├── .env                             # Environment variables (gitignored)
│   ├── services/
│   │   ├── pdf_parser.py                # Dual-pass PDF extraction, 4-tier fallback chain
│   │   ├── feature_engine.py            # spaCy feature extraction (11 metrics) + semantic embeddings
│   │   ├── clustering.py                # HDBSCAN clustering, boundary detection, confidence scoring
│   │   ├── gpt_analyzer.py              # GPT-4o-mini reasoning with timeout/retry/partial delivery
│   │   ├── citation_forensics.py        # Regex citation extraction, temporal analysis, Crossref verification
│   │   ├── source_tracer.py             # arXiv + OpenAlex search, MiniLM embeddings, Idea Triplets
│   │   └── report_generator.py          # GPT-4o synthesis + rule-based fallback scoring engine
│   └── prompts/
│       ├── style_profile.py             # Per-paragraph forensic style analysis prompt
│       ├── style_compare.py             # Pairwise boundary comparison prompt
│       ├── citation_reasoning.py        # Citation forensics reasoning prompt
│       └── report_synthesis.py          # Full report generation system prompt
├── frontend/
│   ├── index.html                       # Single-page application (6 panels)
│   ├── css/
│   │   └── styles.css                   # Complete design system (~35KB)
│   └── js/
│       ├── app.js                       # Navigation controller and state management
│       ├── upload.js                    # Drag-and-drop file upload + progress tracking
│       ├── heatmap.js                   # Authorship heatmap with cluster color coding
│       ├── charts.js                    # Chart.js feature trend and distribution charts
│       ├── citations.js                 # Citation forensics timeline visualization
│       ├── sources.js                   # Source match cards with similarity scores
│       └── report.js                    # Forensic report rendering with integrity gauge
├── tests/
│   ├── test_genuine.pdf                 # Single-author control paper
│   ├── test_stitched.pdf                # Multi-source stitched paper (positive case)
│   └── test_short.pdf                   # Edge case — very short document
├── .gitignore
├── .env.example
└── README.md
```

---

## Getting Started

### Prerequisites

- **Python 3.12+**
- **OpenAI API Key** with access to `gpt-4o-mini`, `gpt-4o`, and `text-embedding-3-small`

> **Note:** The system works without an API key in degraded mode — all mathematical analysis, clustering, citation forensics, and local source tracing run fully offline. Only the GPT reasoning and final report synthesis require an API key.

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/HarshalAndhale9657/P.R.I.S.M.git
cd P.R.I.S.M/backend

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Download required NLP models
python -m spacy download en_core_web_sm
python -m nltk.downloader punkt_tab

# Configure environment
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY

# Start the server
uvicorn main:app --reload --port 8000
```

The API documentation is auto-generated at **[http://localhost:8000/docs](http://localhost:8000/docs)**.

### Frontend Setup

```bash
# In a separate terminal
cd P.R.I.S.M/frontend
python -m http.server 3000
```

Open **[http://localhost:3000](http://localhost:3000)** in your browser.

---

## API Reference

| Method | Endpoint | Description |
|:---:|---|---|
| `GET` | `/` | Health check — returns service status |
| `POST` | `/api/upload` | Upload PDF, validate, return metadata (filename, size, page count) |
| `POST` | `/api/parse` | Stage 1 — Dual-pass PDF parsing, returns paragraphs + references |
| `POST` | `/api/features` | Stages 1–2 — Parse + extract 11-dimensional stylometric features |
| `POST` | `/api/cluster` | Stages 1–3 — Parse + features + HDBSCAN clustering |
| `POST` | `/api/reasoning` | Stages 1–4 — Full pipeline through GPT style reasoning |
| `POST` | `/api/analyze` | **Stages 1–7** — Complete forensic analysis pipeline |

### Example: Full Analysis

```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "file=@paper.pdf"
```

<details>
<summary><strong>Response Structure (click to expand)</strong></summary>

```json
{
  "filename": "paper.pdf",
  "status": "success",
  "paragraphs": [ ... ],
  "clustering": {
    "estimated_authors": 2,
    "anomaly_count": 3,
    "noise_percentage": 0.15,
    "boundaries": [ ... ],
    "confidence": 0.87,
    "cluster_sizes": { "0": 12, "1": 5, "-1": 3 }
  },
  "features": {
    "feature_names": [ "avg_sentence_length", "avg_word_length", ... ],
    "profiles": [ ... ]
  },
  "reasoning": {
    "available": true,
    "boundary_explanations": { ... },
    "anomaly_profiles": { ... }
  },
  "citations": {
    "total_citations_found": 47,
    "temporal_anomalies": [ ... ],
    "density_analysis": { ... },
    "bibliography": { "hallucination_count": 0 }
  },
  "sources": [
    {
      "similarity_score": 0.87,
      "source": {
        "title": "Attention Is All You Need",
        "origin": "arXiv",
        "url": "https://arxiv.org/..."
      }
    }
  ],
  "report": {
    "integrity_score": 4.2,
    "verdict": "Suspicious",
    "executive_summary": "...",
    "evidence_breakdown": { ... }
  },
  "warnings": [ ... ],
  "warning_count": 2
}
```

</details>

---

## AI Tools Disclosure

The following AI tools and models are used in this project:

| Tool / Model | Provider | Usage |
|---|---|---|
| GPT-4o-mini | OpenAI | Per-paragraph stylometric profiling and pairwise boundary comparison |
| GPT-4o | OpenAI | Final forensic report synthesis with multi-evidence weighing |
| text-embedding-3-small | OpenAI | 1536-dim paragraph embeddings for hybrid feature space (PCA → 3 dims) |
| paraphrase-multilingual-MiniLM-L12-v2 | Hugging Face | Local 384-dim embeddings for source tracing (zero API cost) |
| spaCy en_core_web_sm | Explosion AI | Deterministic POS tagging, dependency parsing, sentence segmentation |
| Crossref API | Crossref | Reference existence verification for hallucination detection |
| arXiv API | arXiv | Academic paper search for semantic source tracing |
| OpenAlex API | OpenAlex | Supplementary academic paper search (free, no auth required) |
| Gemini Code Assist | Google | Development assistance during hackathon |

---

## How It Works — Step by Step

1. **Upload** a PDF through the dashboard or POST to `/api/analyze`
2. **Dual-pass parsing** extracts body paragraphs and isolates the bibliography
3. **spaCy** computes 8 stylometric features per paragraph + 3 semantic embedding dimensions
4. **HDBSCAN** clusters paragraphs by writing style — anomalies land in Cluster -1
5. **GPT-4o-mini** explains *why* flagged boundaries exhibit a stylistic shift
6. **Regex engine** extracts citations, computes temporal anchors, flags chronological anomalies
7. **Crossref API** verifies that cited references actually exist (hallucination detection)
8. **Source tracer** searches arXiv + OpenAlex, embeds results with MiniLM, ranks by cosine similarity
9. **Idea Triplets** defeat AI paraphrasers by comparing logical structure, not vocabulary
10. **GPT-4o** synthesizes all evidence into a scored, prosecutable forensic report

---

## Contributors

- **Harshal Andhale** ([@HarshalAndhale9657](https://github.com/HarshalAndhale9657))
- **Chetana Phalke** ([@chetna196](https://github.com/chetna196))
- **Vedant Mohanrao Sable** ([@vedantsable56](https://github.com/vedantsable56))
- **Arya Achalkar** ([@aryaachalkar](https://github.com/aryaachalkar))
- **Aniket Krishna Ingale** ([@DevOpsDreamer](https://github.com/DevOpsDreamer))

---

## License

This project was built during **DevClash 2026** (April 18–19, 2026). All rights reserved by the authors.
