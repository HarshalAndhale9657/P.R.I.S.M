# 🔬 Academic Integrity Analyzer — System Design

> **PS2 | DevClash 2026 | Open Track**  
> Detects stitched plagiarism through stylometric analysis, citation forensics, and semantic source tracing

---

## 🏗️ Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                        ACADEMIC INTEGRITY ANALYZER — SYSTEM ARCHITECTURE                     ║
║                     Stitched Plagiarism Detection via AI-Powered Forensics                    ║
╠══════════════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                              ║
║  ┌─────────────────────────────────── ① INPUT LAYER ───────────────────────────────────────┐ ║
║  │                                                                                         │ ║
║  │   👤 User                    ⚙️ PDF Parser                   📦 Text Store              │ ║
║  │   ┌──────────────┐           ┌──────────────────┐           ┌──────────────────┐        │ ║
║  │   │  📄 Upload   │  ──POST──▶│  pdfplumber      │  ──────▶  │  paragraphs[]    │        │ ║
║  │   │  Research    │  /api/    │  + regex          │           │  references[]    │        │ ║
║  │   │  Paper PDF   │  upload   │                  │           │  sections[]      │        │ ║
║  │   │              │           │  • Text extract   │           │  metadata{}      │        │ ║
║  │   │  [Drag&Drop] │           │  • Para splitting │           │                  │        │ ║
║  │   │  [M3-Pixel]  │           │  • Ref extraction │           │  [In-Memory]     │        │ ║
║  │   └──────────────┘           │  [M2-Engine]      │           └────────┬─────────┘        │ ║
║  │                              └──────────────────┘                     │                  │ ║
║  └──────────────────────────────────────────────────────────────────────┼──────────────────┘ ║
║                                                                         │                    ║
║                              ┌──────────────────────────────────────────┼───┐                ║
║                              │                  │                       │   │                ║
║                              ▼                  ▼                       ▼   │                ║
║  ┌──────────────────── ② ANALYSIS ENGINE — THREE FORENSIC PILLARS ─────────────────────────┐ ║
║  │                                                                                         │ ║
║  │  ┌─── PILLAR 1 ──────────┐  ┌─── PILLAR 2 ──────────┐  ┌─── PILLAR 3 ──────────┐     │ ║
║  │  │ 🔬 STYLOMETRIC        │  │ 📚 CITATION            │  │ 🔍 SEMANTIC SOURCE     │     │ ║
║  │  │    ANALYZER            │  │    FORENSICS            │  │    TRACER              │     │ ║
║  │  │ ─────────────────────  │  │ ─────────────────────   │  │ ─────────────────────  │     │ ║
║  │  │ • Vocabulary richness  │  │ • Reference extraction  │  │ • Embed flagged text   │     │ ║
║  │  │ • Sentence structure   │  │ • Temporal analysis     │  │ • Query arxiv API      │     │ ║
║  │  │ • Passive voice %      │  │   (cite era mismatch)   │  │ • Cosine similarity    │     │ ║
║  │  │ • Formality score      │  │ • Thematic clustering   │  │ • Rank source papers   │     │ ║
║  │  │ • Technical density    │  │   (topic consistency)   │  │ • Evidence linking      │     │ ║
║  │  │ • Hedging frequency    │  │ • Cross-section scoring │  │   (section → paper)    │     │ ║
║  │  │ • Pairwise comparison  │  │ • Anomaly flagging      │  │                        │     │ ║
║  │  │   (consecutive pairs)  │  │                         │  │ ┌────────────────────┐ │     │ ║
║  │  │ • Author clustering    │  │ ┌─────────────────────┐ │  │ │ ☁️ arxiv API       │ │     │ ║
║  │  │                        │  │ │ ☁️ OpenAI GPT-4o    │ │  │ │ ☁️ Embeddings API  │ │     │ ║
║  │  │ ┌────────────────────┐ │  │ │    (forensics)      │ │  │ │  text-embedding-   │ │     │ ║
║  │  │ │ ☁️ OpenAI          │ │  │ └─────────────────────┘ │  │ │  3-small           │ │     │ ║
║  │  │ │  GPT-4o-mini       │ │  │                         │  │ └────────────────────┘ │     │ ║
║  │  │ │  (per-paragraph)   │ │  │ Owner: [M2-Engine]      │  │                        │     │ ║
║  │  │ │ ☁️ NLTK / spaCy   │ │  │ Priority: 🔴 P0 Core   │  │ Owner: [M4-Bridge]     │     │ ║
║  │  │ │  (tokenization)    │ │  │                         │  │ Priority: 🟡 P1        │     │ ║
║  │  │ └────────────────────┘ │  └─────────────────────────┘  └────────────────────────┘     │ ║
║  │  │                        │                                                              │ ║
║  │  │ Owner: [M1-Captain]    │         ║ style       ║ citation     ║ source                │ ║
║  │  │ Priority: 🔴 P0 Core  │         ║ profiles    ║ scores       ║ matches               │ ║
║  │  └────────────────────────┘         ▼             ▼              ▼                       │ ║
║  └─────────────────────────────────────────────────────────────────────────────────────────┘ ║
║                                                │                                             ║
║                                                ▼                                             ║
║  ┌──────────────────────────────── ③ AGGREGATION LAYER ───────────────────────────────────┐  ║
║  │                                                                                        │  ║
║  │                        🧠 FORENSIC REPORT GENERATOR                                    │  ║
║  │                        OpenAI GPT-4o · Structured JSON                                 │  ║
║  │                        Owner: [M1-Captain]                                             │  ║
║  │                                                                                        │  ║
║  │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │  ║
║  │   │  N Estimated  │  │  X/10        │  │  K Flagged    │  │  M Source     │              │  ║
║  │   │  Authors      │  │  Integrity   │  │  Sections     │  │  Matches      │              │  ║
║  │   │              │  │  Score        │  │              │  │  Found        │              │  ║
║  │   └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘              │  ║
║  │                                                                                        │  ║
║  └────────────────────────────────────────┬───────────────────────────────────────────────┘  ║
║                                           │                                                  ║
║                                           ▼                                                  ║
║  ┌──────────────────────── ④ OUTPUT LAYER — Frontend Dashboard ───────────────────────────┐  ║
║  │                                     Owner: [M3-Pixel]                                  │  ║
║  │                                                                                        │  ║
║  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌─────────┐ │  ║
║  │  │ 🗺️ Author- │ │ 📊 Style   │ │ 📚 Citation│ │ 🔗 Source  │ │ 📋 Full  │ │ 📥 Exp- │ │  ║
║  │  │ ship Heat- │ │ Similarity │ │ Analysis   │ │ Paper      │ │ Forensic │ │ ort     │ │  ║
║  │  │ map        │ │ Graph      │ │ View       │ │ Matches    │ │ Report   │ │ PDF/JSON│ │  ║
║  │  │            │ │            │ │            │ │            │ │          │ │         │ │  ║
║  │  │ Color-code │ │ Line chart │ │ Temporal & │ │ Flagged    │ │ Authors, │ │ Downloa-│ │  ║
║  │  │ paragraphs │ │ of para    │ │ thematic   │ │ section →  │ │ scores,  │ │ dable   │ │  ║
║  │  │ by inferred│ │ similarity │ │ consistency│ │ arxiv paper│ │ verdicts,│ │ for     │ │  ║
║  │  │ author     │ │ scores     │ │ breakdown  │ │ with % sim │ │ evidence │ │ records │ │  ║
║  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └──────────┘ └─────────┘ │  ║
║  └────────────────────────────────────────────────────────────────────────────────────────┘  ║
║                                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                              ║
║  ⚡ API ENDPOINTS (FastAPI · M4-Bridge)          ☁️ EXTERNAL SERVICES                        ║
║  ──────────────────────────────────────          ─────────────────────                        ║
║  POST  /api/upload         → Receive PDF         OpenAI GPT-4o-mini  → Style profiling       ║
║  POST  /api/analyze        → Run full pipeline   OpenAI GPT-4o       → Report generation     ║
║  GET   /api/report/{id}    → Fetch results       OpenAI Embeddings   → Semantic vectors      ║
║  POST  /api/search-sources → arxiv search        arxiv API           → Paper search           ║
║                                                  NLTK / spaCy        → Tokenization           ║
║                                                                                              ║
║  🛠️ TECH STACK                                   👥 TEAM OWNERSHIP                           ║
║  ──────────────                                  ─────────────────                             ║
║  Frontend:  HTML/CSS/JS + Chart.js               M1 (Captain): AI prompts, stylometry, report ║
║  Backend:   Python 3.12 + FastAPI                M2 (Engine):  PDF parser, citation forensics ║
║  AI:        OpenAI GPT-4 + Embeddings            M3 (Pixel):   Frontend, heatmap, dashboard   ║
║  PDF:       pdfplumber + PyPDF2                  M4 (Bridge):  FastAPI, arxiv, integration     ║
║  Deploy:    Railway/Render + Vercel              M5 (Shield):  Testing, deploy, README, video ║
║                                                                                              ║
║  💰 COST: ~$0.15 per paper analysis    ⏱️ LATENCY: ~30-60s end-to-end                       ║
║                                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
```

---

## High-Level Architecture

```mermaid
graph TB
    subgraph INPUT["① INPUT LAYER"]
        A["📄 PDF Upload<br/><i>Drag & drop research paper</i>"]
        B["⚙️ PDF Parser & Segmenter<br/><i>pdfplumber + regex</i>"]
        C["📦 Structured Text Store<br/><i>paragraphs[] · references[] · sections[]</i>"]
    end

    subgraph ENGINE["② ANALYSIS ENGINE — Three Forensic Pillars"]
        direction LR
        D["🔬 PILLAR 1<br/><b>Stylometric Analyzer</b><br/><i>GPT-4 + NLTK</i><br/>───────────<br/>• Vocabulary richness<br/>• Sentence structure<br/>• Passive voice %<br/>• Formality score<br/>• Pairwise similarity<br/>• Author clustering"]
        E["📚 PILLAR 2<br/><b>Citation Forensics</b><br/><i>GPT-4 + regex</i><br/>───────────<br/>• Reference extraction<br/>• Temporal consistency<br/>• Thematic clustering<br/>• Cross-section analysis<br/>• Anomaly flagging"]
        F["🔍 PILLAR 3<br/><b>Semantic Source Tracer</b><br/><i>Embeddings + arxiv API</i><br/>───────────<br/>• Embed flagged text<br/>• arxiv search<br/>• Cosine similarity<br/>• Source ranking<br/>• Evidence linking"]
    end

    subgraph AGG["③ AGGREGATION"]
        G["🧠 Forensic Report Generator<br/><i>GPT-4o</i><br/>───────────<br/>Estimated Authors · Integrity Score · Flagged Sections · Source Matches"]
    end

    subgraph OUTPUT["④ OUTPUT LAYER — Frontend Dashboard"]
        direction LR
        H["🗺️ Authorship<br/>Heatmap"]
        I["📊 Style Similarity<br/>Graph"]
        J["📚 Citation<br/>Analysis"]
        K["🔗 Source Paper<br/>Matches"]
        L["📋 Forensic<br/>Report"]
        M["📥 Export<br/>PDF/JSON"]
    end

    A -->|"upload"| B
    B -->|"extract & split"| C
    C -->|"paragraphs"| D
    C -->|"references"| E
    C -->|"flagged text"| F
    D -->|"style profiles"| G
    E -->|"citation scores"| G
    F -->|"source matches"| G
    G --> H
    G --> I
    G --> J
    G --> K
    G --> L
    G --> M

    style INPUT fill:#0d1117,stroke:#30363d,color:#f0f6fc
    style ENGINE fill:#0d1117,stroke:#30363d,color:#f0f6fc
    style AGG fill:#0d1117,stroke:#30363d,color:#f0f6fc
    style OUTPUT fill:#0d1117,stroke:#30363d,color:#f0f6fc
    style D fill:#1a1a2e,stroke:#8b5cf6,color:#f0f6fc
    style E fill:#1a1a2e,stroke:#f59e0b,color:#f0f6fc
    style F fill:#1a1a2e,stroke:#06b6d4,color:#f0f6fc
    style G fill:#1a1a2e,stroke:#ec4899,color:#f0f6fc
```

---

## Detailed Data Flow

```mermaid
sequenceDiagram
    participant U as 👤 User
    participant FE as 🖥️ Frontend
    participant API as ⚡ FastAPI Backend
    participant PDF as 📄 PDF Parser
    participant S as 🔬 Stylometric Analyzer
    participant C as 📚 Citation Forensics
    participant ST as 🔍 Source Tracer
    participant GPT as 🤖 OpenAI GPT-4
    participant AX as 📑 arxiv API

    U->>FE: Upload research paper PDF
    FE->>API: POST /api/upload (multipart file)
    API->>PDF: Extract text from PDF
    PDF-->>API: Raw text + metadata
    API->>API: Segment into paragraphs + extract references
    
    Note over API,GPT: ── PARALLEL ANALYSIS ──

    par Pillar 1: Stylometry
        API->>GPT: Analyze each paragraph style profile
        GPT-->>API: {vocab_richness, sentence_len, formality, ...}
        API->>GPT: Compare consecutive paragraph pairs
        GPT-->>API: {similarity_score: 0-100, differences}
        API->>API: Cluster paragraphs → estimate author count
    and Pillar 2: Citation Forensics
        API->>GPT: Analyze reference patterns per section
        GPT-->>API: {temporal_consistency, thematic_consistency, flags}
    end

    Note over API,AX: ── SEQUENTIAL: Source Tracing ──
    
    API->>GPT: Embed flagged paragraph text
    GPT-->>API: Vector embeddings
    API->>AX: Search arxiv with key phrases
    AX-->>API: Matching paper abstracts
    API->>API: Cosine similarity → rank sources

    Note over API,GPT: ── REPORT GENERATION ──

    API->>GPT: Generate unified forensic report
    GPT-->>API: Structured JSON report
    API-->>FE: Full analysis results
    FE-->>U: Display heatmap + report + sources
```

---

## Component Architecture

```mermaid
graph LR
    subgraph FRONTEND["🖥️ Frontend — HTML/CSS/JS"]
        F1["Upload Page<br/><i>Drag & drop PDF</i>"]
        F2["Authorship Heatmap<br/><i>Color-coded paragraphs</i>"]
        F3["Style Similarity Chart<br/><i>Chart.js line graph</i>"]
        F4["Citation Analysis View<br/><i>Consistency breakdown</i>"]
        F5["Source Matches Panel<br/><i>arxiv paper links</i>"]
        F6["Forensic Report<br/><i>Full structured output</i>"]
    end

    subgraph BACKEND["⚡ Backend — Python FastAPI"]
        B1["POST /api/upload<br/><i>Receive PDF file</i>"]
        B2["POST /api/analyze<br/><i>Run full pipeline</i>"]
        B3["GET /api/report/:id<br/><i>Fetch results</i>"]
        B4["POST /api/search-sources<br/><i>arxiv search</i>"]
    end

    subgraph SERVICES["🔧 Core Services"]
        S1["PDFService<br/><i>pdfplumber extraction</i>"]
        S2["SegmenterService<br/><i>Paragraph splitting</i>"]
        S3["StyleAnalyzer<br/><i>GPT-4 stylometry</i>"]
        S4["CitationAnalyzer<br/><i>Reference forensics</i>"]
        S5["SourceTracer<br/><i>Embedding + search</i>"]
        S6["ReportGenerator<br/><i>Aggregate findings</i>"]
    end

    subgraph EXTERNAL["☁️ External APIs"]
        E1["OpenAI GPT-4o-mini<br/><i>Style profiling</i>"]
        E2["OpenAI GPT-4o<br/><i>Report generation</i>"]
        E3["OpenAI Embeddings<br/><i>text-embedding-3-small</i>"]
        E4["arxiv API<br/><i>Paper search</i>"]
    end

    F1 --> B1
    F1 --> B2
    F2 --> B3
    F5 --> B4
    B1 --> S1
    B2 --> S1
    S1 --> S2
    S2 --> S3
    S2 --> S4
    S3 --> E1
    S4 --> E2
    S3 --> S6
    S4 --> S6
    S5 --> E3
    S5 --> E4
    S5 --> S6
    S6 --> E2
    B4 --> S5

    style FRONTEND fill:#0d1117,stroke:#10b981,color:#f0f6fc
    style BACKEND fill:#0d1117,stroke:#3b82f6,color:#f0f6fc
    style SERVICES fill:#0d1117,stroke:#8b5cf6,color:#f0f6fc
    style EXTERNAL fill:#0d1117,stroke:#f59e0b,color:#f0f6fc
```

---

## Tech Stack

```mermaid
mindmap
  root((Academic Integrity<br/>Analyzer))
    Frontend
      HTML5 / CSS3 / JS
      Chart.js — heatmap + graphs
      Fetch API — backend calls
    Backend
      Python 3.12
      FastAPI — REST API
      pdfplumber — PDF text extraction
      NLTK — sentence tokenization
    AI Layer
      OpenAI GPT-4o-mini — style profiling
      OpenAI GPT-4o — report generation  
      text-embedding-3-small — semantic search
    External
      arxiv API — paper search
      IEEE Xplore — source matching
    Deployment
      Railway / Render — backend
      Vercel — frontend
      GitHub — version control
```

---

## Team Ownership Map

```mermaid
graph TB
    subgraph M1["🎯 M1 — Captain / AI Architect"]
        M1A["Stylometric Analyzer"]
        M1B["Prompt Engineering"]
        M1C["Author Clustering"]
        M1D["Forensic Report Logic"]
        M1E["Judging Presentations"]
    end

    subgraph M2["⚙️ M2 — Engine / Backend Lead"]
        M2A["PDF Parser"]
        M2B["Paragraph Segmenter"]
        M2C["Citation Extractor"]
        M2D["Citation Forensics Engine"]
    end

    subgraph M3["🎨 M3 — Pixel / Frontend Lead"]
        M3A["Upload Page UI"]
        M3B["Authorship Heatmap"]
        M3C["Style Charts"]
        M3D["Report Dashboard"]
    end

    subgraph M4["🔗 M4 — Bridge / Integration"]
        M4A["FastAPI Endpoints"]
        M4B["OpenAI API Wrapper"]
        M4C["arxiv Search Integration"]
        M4D["Frontend ↔ Backend Connection"]
    end

    subgraph M5["🛡️ M5 — Shield / QA + DevOps"]
        M5A["Test PDF Creation"]
        M5B["End-to-End Testing"]
        M5C["Deployment"]
        M5D["README + Demo Video"]
    end

    style M1 fill:#1a1a2e,stroke:#8b5cf6,color:#f0f6fc
    style M2 fill:#1a1a2e,stroke:#3b82f6,color:#f0f6fc
    style M3 fill:#1a1a2e,stroke:#10b981,color:#f0f6fc
    style M4 fill:#1a1a2e,stroke:#f59e0b,color:#f0f6fc
    style M5 fill:#1a1a2e,stroke:#ef4444,color:#f0f6fc
```

---

## Project Structure

```
academic-integrity-analyzer/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── routers/
│   │   ├── upload.py            # POST /api/upload
│   │   ├── analyze.py           # POST /api/analyze
│   │   ├── report.py            # GET /api/report/:id
│   │   └── sources.py           # POST /api/search-sources
│   ├── services/
│   │   ├── pdf_service.py       # PDF parsing + text extraction
│   │   ├── segmenter.py         # Paragraph segmentation
│   │   ├── style_analyzer.py    # Stylometric analysis (GPT-4)
│   │   ├── citation_analyzer.py # Citation forensics
│   │   ├── source_tracer.py     # Semantic search + arxiv
│   │   └── report_generator.py  # Aggregate forensic report
│   ├── models/
│   │   ├── paragraph.py         # Paragraph data model
│   │   ├── analysis.py          # Analysis result models
│   │   └── report.py            # Forensic report model
│   ├── prompts/
│   │   ├── style_profile.txt    # GPT-4 style analysis prompt
│   │   ├── style_compare.txt    # Pairwise comparison prompt
│   │   ├── citation_analysis.txt # Citation forensics prompt
│   │   └── report_gen.txt       # Report generation prompt
│   └── requirements.txt
├── frontend/
│   ├── index.html               # Main page
│   ├── css/
│   │   └── styles.css           # Dark theme styling
│   └── js/
│       ├── app.js               # Main app logic
│       ├── upload.js            # File upload handler
│       ├── heatmap.js           # Authorship heatmap renderer
│       ├── charts.js            # Style similarity charts
│       └── report.js            # Report display logic
├── tests/
│   ├── test_genuine.pdf         # Single-author paper (should pass)
│   ├── test_stitched.pdf        # Multi-source stitched paper (should flag)
│   └── test_collaborative.pdf   # Legit multi-author (should show variation)
├── README.md
└── .gitignore
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **AI Model** | GPT-4o-mini for per-paragraph, GPT-4o for final report | Cost efficiency — bulk work uses cheaper model, synthesis uses smarter model |
| **PDF Parser** | pdfplumber over PyPDF2 | Better layout preservation, handles tables/columns correctly |
| **Clustering** | LLM-driven over k-means | Writing style is semantic — can't reduce to numeric features alone |
| **Source Search** | arxiv API + embeddings | Free, real-time, covers CS/ML papers. IEEE as stretch goal |
| **Frontend** | Vanilla HTML/CSS/JS | Zero build step, instant deploy, team knows it well |
| **Backend** | FastAPI | Native async, auto-docs, Python ecosystem for NLP |

---

## API Cost Per Analysis

| Step | API Call | Model | Est. Cost |
|------|---------|-------|-----------|
| Style per paragraph (×40) | 40 calls | gpt-4o-mini | ~$0.02 |
| Pairwise comparison (×39) | 39 calls | gpt-4o-mini | ~$0.02 |
| Citation forensics | 1 call | gpt-4o | ~$0.03 |
| Author estimation | 1 call | gpt-4o | ~$0.03 |
| Report generation | 1 call | gpt-4o | ~$0.05 |
| Embeddings (×10 flagged) | 10 calls | text-embedding-3-small | ~$0.001 |
| **TOTAL** | | | **~$0.15** |
