# P.R.I.S.M.

**Plagiarism Recognition via Integrated Stylometric Mapping**

P.R.I.S.M. is a forensic document analysis platform that detects *stitched plagiarism* in academic papers — a form of fraud where a student assembles a document by splicing sections written by different authors. Unlike traditional plagiarism detectors that rely on string matching, P.R.I.S.M. uses a hybrid pipeline of deterministic NLP feature extraction, density-based clustering, and large language model reasoning to identify authorship boundaries, citation anomalies, and probable source documents.

Built for **DevClash 2026** (Open Track).

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Solution Architecture](#solution-architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [AI Tools Disclosure](#ai-tools-disclosure)
- [License](#license)

---

## Problem Statement

Academic plagiarism has evolved beyond verbatim copying. A growing pattern involves students composing submissions by splicing sections from multiple existing papers, creating a superficially original document that evades traditional detection tools. No single section is copied word-for-word — the fraud lies in the assembly.

P.R.I.S.M. addresses this through three forensic pillars:

| Pillar | Method | Purpose |
|--------|--------|---------|
| **Stylometric Analysis** | spaCy feature extraction + HDBSCAN clustering + GPT reasoning | Detect distinct writing voices across paragraphs and estimate author count |
| **Citation Forensics** | Deterministic regex extraction + temporal/thematic consistency checks | Identify sections citing from incompatible knowledge domains or time periods |
| **Semantic Source Tracing** | Local embeddings (all-MiniLM-L6-v2) + arXiv API search | Trace flagged paragraphs back to probable source papers |

---

## Solution Architecture

```
PDF Upload
    |
    v
+---------------------------------------+
|  STAGE 1: DUAL-PASS PDF PARSING       |
|  Pass A: unstructured (NarrativeText)  |
|  Pass B: PyMuPDF (bibliography bbox)   |
|  Fallback: pdfplumber -> raw chunks    |
+-------------------+-------------------+
                    |
                    v
+---------------------------------------+
|  STAGE 2: DETERMINISTIC ANALYSIS      |
|  spaCy en_core_web_sm:                |
|    - Function word ratios (POS tags)   |
|    - Avg sentence / word length        |
|    - Passive voice frequency           |
|    - Yule's K lexical richness         |
|  StandardScaler -> HDBSCAN clustering  |
|    - Auto author count detection       |
|    - Cluster -1 = anomaly / flagged    |
+-------------------+-------------------+
                    |
                    v
+---------------------------------------+
|  STAGE 3: AI REASONING (GPT)         |
|  GPT-4o-mini per flagged paragraph:   |
|    - Natural language style profile    |
|    - Pairwise comparison reasoning     |
|  Merge: HDBSCAN clusters + GPT = evidence |
+-------------------+-------------------+
                    |
                    v
+---------------------------------------+
|  STAGE 4: CITATION FORENSICS          |
|  Regex: APA/MLA/Harvard extraction     |
|  Temporal: median year per paragraph   |
|  Flag if cluster year diff > 10 years  |
|  GPT-4o: forensic reasoning            |
+-------------------+-------------------+
                    |
                    v
+---------------------------------------+
|  STAGE 5: SEMANTIC SOURCE TRACING     |
|  Cluster -1 paragraphs only:          |
|  spaCy noun chunks -> arXiv query      |
|  all-MiniLM-L6-v2 embed both sides    |
|  Cosine similarity > 0.75 = match      |
+-------------------+-------------------+
                    |
                    v
+---------------------------------------+
|  STAGE 6: FORENSIC REPORT             |
|  GPT-4o synthesizes all findings:     |
|    - HDBSCAN cluster analysis          |
|    - GPT style reasoning               |
|    - Citation temporal anomalies       |
|    - Source paper matches              |
|  -> Structured JSON forensic report    |
|  -> Integrity score (0-10)             |
+---------------------------------------+
```

---

## Tech Stack

### Backend

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Framework | FastAPI | Async support, Pydantic validation, auto-generated docs at `/docs` |
| PDF Parsing | `unstructured` + PyMuPDF | Dual-pass: `unstructured` handles reading order; PyMuPDF isolates bibliography via bounding box analysis |
| NLP Engine | spaCy (`en_core_web_sm`) | Deterministic POS tagging, dependency parsing, sentence segmentation — zero API calls |
| Clustering | HDBSCAN | Density-based, auto-detects cluster count, noise label (-1) maps directly to plagiarism flags |
| Feature Scaling | scikit-learn `StandardScaler` | Normalizes feature matrix before clustering |
| Local Embeddings | `all-MiniLM-L6-v2` (sentence-transformers) | 384-dim vectors, 14K sentences/sec on CPU, zero API cost |
| AI Reasoning | OpenAI GPT-4o-mini | Per-paragraph style explanation and pairwise comparison |
| AI Report | OpenAI GPT-4o | Final forensic report synthesis |
| Source Search | `arxiv` Python package + `tenacity` | Free API with exponential backoff retry |

### Frontend

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| UI | HTML5 / CSS3 / Vanilla JS | Zero build step, zero configuration, instant deployment |
| Charts | Chart.js (CDN) | Line charts, bar charts, heatmap rendering — no npm required |
| Colors | Programmatic HSL generation | Distinct cluster colors generated dynamically |

### Infrastructure

| Component | Technology |
|-----------|-----------|
| Backend Hosting | Render (free tier) |
| Frontend Hosting | Vercel |
| Version Control | GitHub |

---

## Project Structure

```
P.R.I.S.M/
|-- backend/
|   |-- main.py                       # FastAPI application entry point
|   |-- models.py                     # Pydantic response models
|   |-- requirements.txt              # Python dependencies
|   |-- .env                          # Environment variables (gitignored)
|   |-- services/
|   |   |-- pdf_parser.py             # Dual-pass PDF text extraction
|   |   |-- feature_engine.py         # spaCy NLP feature extraction (7 metrics)
|   |   |-- clustering.py             # HDBSCAN authorship clustering
|   |   |-- gpt_analyzer.py           # GPT-4o-mini style reasoning
|   |   |-- citation_forensics.py     # Regex citation extraction + temporal analysis
|   |   |-- source_tracer.py          # Local embeddings + arXiv semantic search
|   |   |-- report_generator.py       # GPT-4o forensic report synthesis
|   |-- prompts/
|       |-- style_profile.py          # Per-paragraph style analysis prompt
|       |-- style_compare.py          # Pairwise comparison prompt
|       |-- citation_reasoning.py     # Citation forensics prompt
|       |-- report_synthesis.py       # Report generation prompt
|-- frontend/
|   |-- index.html                    # Single-page application
|   |-- css/
|   |   |-- styles.css                # Dark theme styling
|   |-- js/
|       |-- app.js                    # Main application controller
|       |-- upload.js                 # Drag-and-drop file upload
|       |-- heatmap.js                # Authorship heatmap renderer
|       |-- charts.js                 # Style similarity chart renderer
|       |-- report.js                 # Forensic report display
|-- tests/
|   |-- test_genuine.pdf              # Single-author paper (control)
|   |-- test_stitched.pdf             # Multi-source stitched paper (positive case)
|   |-- test_short.pdf                # Edge case: very short document
|-- .gitignore
|-- .env.example
|-- README.md
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- An OpenAI API key with access to `gpt-4o-mini`, `gpt-4o`, and `text-embedding-3-small`

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/HarshalAndhale9657/P.R.I.S.M.git
cd P.R.I.S.M/backend

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

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

The API documentation is auto-generated and available at `http://localhost:8000/docs`.

### Frontend Setup

```bash
# In a separate terminal
cd P.R.I.S.M/frontend
python -m http.server 3000
```

Open `http://localhost:3000` in your browser.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check — returns service status |
| `POST` | `/api/upload` | Upload a PDF file; returns metadata (filename, size, page count) |
| `POST` | `/api/analyze` | Full 6-stage analysis pipeline; returns paragraphs, clusters, GPT analysis, citations, source matches |

### Example: Upload a PDF

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@paper.pdf"
```

**Response:**
```json
{
  "filename": "paper.pdf",
  "size_bytes": 245760,
  "page_count": 12,
  "status": "success"
}
```

---

## AI Tools Disclosure

The following AI tools and models are used in this project:

| Tool / Model | Provider | Usage |
|-------------|----------|-------|
| GPT-4o-mini | OpenAI | Per-paragraph stylometric profiling and pairwise comparison reasoning |
| GPT-4o | OpenAI | Final forensic report synthesis and citation forensics reasoning |
| text-embedding-3-small | OpenAI | Backup/comparison embeddings for semantic search |
| all-MiniLM-L6-v2 | Hugging Face (sentence-transformers) | Primary local embeddings for arXiv source tracing |
| spaCy en_core_web_sm | Explosion AI | Deterministic NLP: POS tagging, dependency parsing, sentence segmentation |
| Gemini Code Assist | Google | Development assistance during hackathon |

---

## License

This project was built during DevClash 2026 (April 18-19, 2026). All rights reserved by the authors.
