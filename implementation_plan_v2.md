# 🏗️ P.R.I.S.M. — Implementation Plan v2 (Hybrid)

> **P**lagiarism **R**ecognition via **I**ntegrated **S**tylometric **M**apping  
> Hybrid Architecture: Mathematical Proof (spaCy + HDBSCAN) + AI Reasoning (GPT-4o)

---

## 🛠️ Tech Stack — Final (Hybrid)

### Backend Core

| Component | Technology | Why |
|-----------|-----------|-----|
| **Framework** | **FastAPI** | Async, Pydantic validation, auto-docs at `/docs` |
| **PDF Parsing** | **`unstructured` + PyMuPDF** | `unstructured` handles multi-column reading order. PyMuPDF isolates bibliography via bounding box analysis. Dual-pass = zero text corruption. |
| **NLP Engine** | **spaCy (`en_core_web_sm`)** | Deterministic POS tagging, dependency parsing, sentence segmentation in milliseconds. Zero API calls. |
| **Clustering** | **HDBSCAN** | Auto-detects author count. Cluster -1 = noise = plagiarism flag. No need to specify K. Mathematically provable. |
| **Local Embeddings** | **all-MiniLM-L6-v2** (`sentence-transformers`) | 384-dim vectors, 14K sentences/sec on CPU, zero API cost. For source tracing similarity. |
| **AI Reasoning** | **OpenAI GPT-4o-mini** | Per-paragraph style explanation, pairwise reasoning. Fast + detailed. |
| **AI Report** | **OpenAI GPT-4o** | Final forensic report synthesis. Smartest model for conclusions. |
| **AI Embeddings** | **OpenAI text-embedding-3-small** | Backup/comparison embeddings alongside local model. |
| **Citation Regex** | **Deterministic regex** | APA/MLA/Harvard extraction. Faster + more reliable than LLM for structured patterns. |
| **Source Search** | **arxiv** Python package + **tenacity** | Free API with exponential backoff retry. No rate limit crashes. |
| **Feature Scaling** | **scikit-learn StandardScaler** | Normalize feature matrix before HDBSCAN clustering. |

### Frontend

| Component | Technology | Why |
|-----------|-----------|-----|
| **UI** | **Vanilla HTML + CSS + JS** | Zero build step. Zero config bugs. Instant deploy. |
| **Charts** | **Chart.js** (CDN) | Heatmaps, line charts, bar charts. No npm install. |
| **Dynamic Colors** | **Programmatic HSL generation** | Generate distinct colors per cluster dynamically. |

### Infrastructure

| Component | Technology |
|-----------|-----------|
| **Deploy Backend** | Render (free tier) |
| **Deploy Frontend** | Vercel |
| **VCS** | GitHub — `HarshalAndhale9657/P.R.I.S.M` |

---

## 🔬 Hybrid Analysis Pipeline

```
PDF Upload
    │
    ▼
┌─────────────────────────────────────┐
│  STAGE 1: DUAL-PASS PDF PARSING     │
│  ┌─────────────────────────────┐    │
│  │ Pass A: unstructured        │    │
│  │ → NarrativeText blocks      │    │
│  │ → Multi-column aware        │    │
│  │ → Filters tables/headers    │    │
│  └─────────────────────────────┘    │
│  ┌─────────────────────────────┐    │
│  │ Pass B: PyMuPDF             │    │
│  │ → Bibliography isolation    │    │
│  │ → Font/bounding box detect  │    │
│  └─────────────────────────────┘    │
│  Fallback: pdfplumber → raw chunk   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  STAGE 2: MATHEMATICAL ANALYSIS     │
│  (Deterministic — Zero AI)          │
│                                     │
│  spaCy NLP → Feature Extraction:    │
│  • Function word ratios (POS tags)  │
│  • Avg sentence length              │
│  • Avg word length                  │
│  • Passive voice frequency          │
│  • Yule's K lexical richness        │
│  • Pronoun/preposition/conj ratios  │
│                                     │
│  StandardScaler → HDBSCAN:          │
│  • Auto cluster count               │
│  • Cluster -1 = anomaly = flagged   │
│  • Noise paragraphs = stitched      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  STAGE 3: AI-POWERED REASONING      │
│  (GPT Enhancement Layer)            │
│                                     │
│  GPT-4o-mini per paragraph:         │
│  • Natural language style profile   │
│  • Explain WHY style differs        │
│  • Pairwise comparison reasoning    │
│                                     │
│  Merge: HDBSCAN clusters + GPT      │
│  reasoning = explainable evidence   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  STAGE 4: CITATION FORENSICS        │
│                                     │
│  Regex: Extract inline citations    │
│  → (Smith, 2019), (et al., 2005)    │
│                                     │
│  Temporal analysis:                 │
│  → Median year per paragraph        │
│  → Compare noise vs core cluster    │
│  → Flag if |diff| > 10 years       │
│                                     │
│  GPT-4o: Forensic reasoning         │
│  → Explain citation inconsistencies │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  STAGE 5: SEMANTIC SOURCE TRACING   │
│                                     │
│  For Cluster -1 paragraphs only:    │
│  1. spaCy noun chunk extraction     │
│  2. arxiv API query (top 3 chunks)  │
│  3. all-MiniLM-L6-v2 embed both    │
│  4. Cosine similarity ranking       │
│  5. If sim > 0.75 → source found   │
│                                     │
│  tenacity: exponential backoff      │
│  for arxiv 429 errors               │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  STAGE 6: FORENSIC REPORT           │
│                                     │
│  GPT-4o synthesizes everything:     │
│  • HDBSCAN cluster analysis         │
│  • GPT style reasoning              │
│  • Citation temporal anomalies      │
│  • Source paper matches              │
│  → Structured JSON forensic report  │
│  → Overall integrity score (0-10)   │
│  → Per-paragraph verdicts           │
└─────────────────────────────────────┘
```

---

## 📁 Project Structure

```
P.R.I.S.M/
├── backend/
│   ├── main.py                    # FastAPI app + all routes
│   ├── services/
│   │   ├── pdf_parser.py          # unstructured + PyMuPDF dual-pass
│   │   ├── feature_engine.py      # spaCy NLP feature extraction
│   │   ├── clustering.py          # HDBSCAN stylometric clustering
│   │   ├── gpt_analyzer.py        # GPT-4o-mini style reasoning
│   │   ├── citation_forensics.py  # Regex extraction + temporal analysis
│   │   ├── source_tracer.py       # all-MiniLM-L6-v2 + arxiv search
│   │   └── report_generator.py    # GPT-4o forensic report synthesis
│   ├── prompts/
│   │   ├── style_profile.py       # Style analysis prompt
│   │   ├── style_compare.py       # Pairwise comparison prompt
│   │   ├── citation_reasoning.py  # Citation forensics prompt
│   │   └── report_synthesis.py    # Report generation prompt
│   ├── models.py                  # Pydantic response models
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── index.html
│   ├── css/styles.css
│   └── js/
│       ├── app.js
│       ├── upload.js
│       ├── heatmap.js
│       ├── charts.js
│       └── report.js
├── tests/
│   ├── test_genuine.pdf
│   ├── test_stitched.pdf
│   └── test_short.pdf
├── README.md
├── .gitignore
└── .env.example
```

---

## 📦 requirements.txt

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-multipart==0.0.9

# PDF Parsing (Dual-Pass)
unstructured[pdf]==0.15.0
PyMuPDF==1.24.0

# NLP & Clustering (Deterministic Math Layer)
spacy==3.7.0
hdbscan==0.8.38
scikit-learn==1.5.0
numpy==1.26.4

# Local Embeddings (Source Tracing)
sentence-transformers==3.0.0

# AI Reasoning Layer
openai==1.50.0

# Citation & Source
nltk==3.9.1
arxiv==2.1.3
tenacity==8.5.0

# Utils
python-dotenv==1.0.1
```

**Post-install**:
```bash
python -m spacy download en_core_web_sm
python -m nltk.downloader punkt_tab
```

---

## 🔀 Commit-by-Commit Implementation

---

### COMMIT 1: Project Scaffolding
**Who**: M5 (Shield)  
**When**: Hour 0 (10:00–10:30 AM)

- Create GitHub repo structure
- `.gitignore`, `.env.example`, `requirements.txt`
- Empty file stubs for all modules
- `README.md` with project name + one-liner

```
git commit -m "feat: project scaffolding with hybrid dependencies"
```

---

### COMMIT 2: FastAPI Backend + Health Check + Upload
**Who**: M4 (Bridge)  
**When**: Hour 0–1 (10:00–11:00 AM)

Build `backend/main.py`:
- FastAPI app with CORS
- `GET /` health check
- `POST /api/upload` — accept PDF, save to memory
- Return file metadata (name, size, page count)

```
git commit -m "feat: FastAPI backend with PDF upload endpoint"
```

---

### COMMIT 3: Dual-Pass PDF Parser
**Who**: M2 (Engine)  
**When**: Hour 1–3 (11:00 AM–1:00 PM)

Build `backend/services/pdf_parser.py`:
```python
class AcademicPDFParser:
    def parse(self, pdf_bytes: bytes) -> dict:
        # Pass A: unstructured — narrative text blocks
        elements = partition_pdf(file=BytesIO(pdf_bytes), strategy="fast")
        paragraphs = [e for e in elements if isinstance(e, NarrativeText) and len(e.text) >= 80]
        
        # Pass B: PyMuPDF — bibliography isolation
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        references = self._extract_bibliography(doc)
        
        return {"paragraphs": paragraphs, "references": references}
    
    def _fallback_extraction(self, pdf_bytes):
        """If unstructured fails → PyMuPDF raw → 1000-char chunks"""
        ...
```

**Key**: 3-tier fallback chain (unstructured → PyMuPDF → pdfplumber → raw chunk)

```
git commit -m "feat: dual-pass PDF parser with unstructured + PyMuPDF"
```

---

### COMMIT 4: spaCy Feature Extraction Engine
**Who**: M1 (Captain)  
**When**: Hour 1–3 (11:00 AM–1:00 PM)

Build `backend/services/feature_engine.py`:
```python
nlp = spacy.load("en_core_web_sm", disable=["ner"])

class FeatureEngine:
    def extract_features(self, text: str) -> np.ndarray:
        doc = nlp(text)
        return np.array([
            avg_sentence_length,    # Structural
            avg_word_length,        # Structural
            pronoun_ratio,          # POS-based
            preposition_ratio,      # POS-based
            conjunction_ratio,      # POS-based
            passive_voice_pct,      # Syntactic
            yules_k,                # Lexical richness
        ])
    
    def _calculate_yules_k(self, words):
        """Yule's K = 10000 * (M2 - M1) / M1²"""
        ...
```

**7 deterministic features** extracted per paragraph, zero API calls.

```
git commit -m "feat: spaCy deterministic stylometric feature extraction"
```

---

### COMMIT 5: HDBSCAN Clustering
**Who**: M1 (Captain)  
**When**: Hour 3–4 (1:00–2:00 PM)

Build `backend/services/clustering.py`:
```python
class AuthorshipClustering:
    def __init__(self, min_cluster_size=3):
        self.scaler = StandardScaler()
        self.clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric='euclidean',
            cluster_selection_method='eom'
        )
    
    def cluster(self, feature_matrix: np.ndarray) -> dict:
        # Variance check — prevent zero-variance crash
        if np.all(np.var(feature_matrix, axis=0) < 1e-10):
            return {"clusters": [0]*len(feature_matrix), "estimated_authors": 1}
        
        scaled = self.scaler.fit_transform(feature_matrix)
        labels = self.clusterer.fit_predict(scaled)
        
        # Noise saturation check — if >80% is noise, override
        noise_pct = np.sum(labels == -1) / len(labels)
        if noise_pct > 0.8:
            labels = np.zeros_like(labels)
        
        return {
            "clusters": labels.tolist(),
            "estimated_authors": len(set(labels)) - (1 if -1 in labels else 0),
            "anomaly_indices": [i for i, l in enumerate(labels) if l == -1],
            "noise_percentage": noise_pct
        }
```

```
git commit -m "feat: HDBSCAN density-based authorship clustering"
```

---

### COMMIT 6: GPT Style Reasoning Layer
**Who**: M1 (Captain)  
**When**: Hour 4–5 (2:00–3:00 PM)

Build `backend/services/gpt_analyzer.py`:
- Per-paragraph: GPT-4o-mini explains writing style in natural language
- Pairwise: GPT-4o-mini compares consecutive paragraphs
- **Only runs on flagged paragraphs** (Cluster -1) + their neighbors — saves tokens

```python
async def explain_style_difference(para_a, para_b, cluster_a, cluster_b):
    """Only called when HDBSCAN detected a boundary. GPT explains WHY."""
    if cluster_a == cluster_b:
        return None  # Skip — same author per math
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": COMPARE_PROMPT.format(...)}],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)
```

```
git commit -m "feat: GPT-4o-mini style reasoning for flagged boundaries"
```

---

### COMMIT 7: Citation Forensics (Regex + Temporal)
**Who**: M2 (Engine)  
**When**: Hour 3–5 (1:00–3:00 PM)

Build `backend/services/citation_forensics.py`:
```python
# Battle-tested regex for APA/MLA/Harvard citations
CITATION_REGEX = r'\b(?!(?:Although|Also)\b)(?:[A-Z][A-Za-z\'`-]+)(?:,?\s(?:(?:and|&)\s(?:[A-Z][A-Za-z\'`-]+)|(?:et\sal\.?)))*\s*(?:,?\s*(?:19|20)\d{2}|\((?:19|20)\d{2}\))'

class CitationForensics:
    def extract_inline_citations(self, paragraphs):
        """Deterministic regex extraction — no LLM needed."""
        ...
    
    def calculate_temporal_anchors(self, paragraphs):
        """Median citation year per paragraph."""
        ...
    
    def detect_temporal_anomalies(self, paragraphs, clusters):
        """Compare noise cluster median year vs core cluster baseline.
        Flag if |difference| > 10 years."""
        ...
```

```
git commit -m "feat: deterministic citation extraction with temporal anomaly detection"
```

---

### COMMIT 8: Frontend — Upload Page + Dark Theme
**Who**: M3 (Pixel)  
**When**: Hour 1–3 (11:00 AM–1:00 PM)

- `index.html` — SPA layout with upload, results panels
- `css/styles.css` — Premium dark theme (#0d1117 base)
- `js/upload.js` — Drag-and-drop with progress bar
- `js/app.js` — State controller, panel navigation

```
git commit -m "feat: frontend upload page with premium dark theme"
```

---

### COMMIT 9: Frontend — Authorship Heatmap
**Who**: M3 (Pixel)  
**When**: Hour 3–5 (1:00–3:00 PM)

Build `frontend/js/heatmap.js`:
- Color-coded paragraph blocks per HDBSCAN cluster
- Cluster -1 = red border + 🚨 anomaly badge
- Click paragraph → show style features + GPT reasoning
- Dynamic HSL color generation (no hardcoded palette)
- YIQ contrast for text readability

```
git commit -m "feat: interactive authorship heatmap with dynamic cluster colors"
```

---

### COMMIT 10: Semantic Source Tracer
**Who**: M4 (Bridge)  
**When**: Hour 5–8 (3:00–6:00 PM)

Build `backend/services/source_tracer.py`:
```python
from sentence_transformers import SentenceTransformer
from tenacity import retry, wait_exponential, stop_after_attempt
import arxiv

model = SentenceTransformer('all-MiniLM-L6-v2')

class SourceTracer:
    def trace(self, anomalous_paragraphs):
        for para in anomalous_paragraphs:
            # 1. Extract noun chunks via spaCy
            keywords = extract_noun_chunks(para["text"])
            
            # 2. Query arxiv with top 3 keywords
            results = self._safe_arxiv_search(keywords)
            
            # 3. Embed paragraph + abstracts locally
            para_embedding = model.encode(para["text"])
            abstract_embeddings = model.encode([r.summary for r in results])
            
            # 4. Cosine similarity ranking
            similarities = cosine_similarity([para_embedding], abstract_embeddings)[0]
            
            # 5. Return matches above threshold
            ...
    
    @retry(wait=wait_exponential(multiplier=2, min=2, max=10), 
           stop=stop_after_attempt(4))
    def _safe_arxiv_search(self, keywords):
        """Exponential backoff for arxiv rate limits."""
        ...
```

```
git commit -m "feat: semantic source tracing with local embeddings + arxiv"
```

---

### COMMIT 11: Full Analysis Pipeline
**Who**: M4 (Bridge)  
**When**: Hour 7–9 (5:00–7:00 PM)

Wire everything into `POST /api/analyze`:
```python
@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    
    # Stage 1: Parse PDF
    parsed = pdf_parser.parse(pdf_bytes)
    
    # Stage 2: Extract features (spaCy)
    features = feature_engine.extract_all(parsed["paragraphs"])
    
    # Stage 3: Cluster (HDBSCAN)
    clusters = clustering.cluster(features)
    
    # Stage 4: GPT reasoning (flagged paragraphs only)
    gpt_analysis = await gpt_analyzer.analyze_boundaries(parsed["paragraphs"], clusters)
    
    # Stage 5: Citation forensics
    citations = citation_forensics.analyze(parsed["paragraphs"], parsed["references"], clusters)
    
    # Stage 6: Source tracing (anomalies only)
    sources = source_tracer.trace(clusters["anomaly_indices"], parsed["paragraphs"])
    
    return {
        "paragraphs": parsed["paragraphs"],
        "clusters": clusters,
        "gpt_analysis": gpt_analysis,
        "citations": citations,
        "sources": sources,
        "metadata": {"pages": parsed["page_count"], "total_paragraphs": len(parsed["paragraphs"])}
    }
```

```
git commit -m "feat: unified 6-stage analysis pipeline endpoint"
```

---

### COMMIT 12: Style Similarity Chart
**Who**: M3 (Pixel)  
**When**: Hour 5–6 (3:00–4:00 PM)

Build `frontend/js/charts.js`:
- Line chart: spaCy feature values across paragraphs
- Bar chart: function word ratios per paragraph
- Scatter: HDBSCAN cluster visualization
- Red threshold line + anomaly markers

```
git commit -m "feat: style similarity charts with feature visualization"
```

---

### COMMIT 13: Frontend — Citation Analysis View
**Who**: M3 (Pixel)  
**When**: Hour 6–7 (4:00–5:00 PM)

- Timeline visualization of citation years per paragraph
- Core cluster baseline vs noise cluster divergence
- Flagged temporal anomalies with red markers

```
git commit -m "feat: citation timeline visualization with temporal anomaly flags"
```

---

### COMMIT 14: Forensic Report Generator
**Who**: M1 (Captain)  
**When**: Hour 8–10 (6:00–8:00 PM)

Build `backend/services/report_generator.py`:
- GPT-4o synthesizes all pillar outputs into structured forensic report
- Includes: verdict, evidence per section, confidence scores
- Returns structured JSON

```
git commit -m "feat: GPT-4o forensic report generator with evidence synthesis"
```

---

### COMMIT 15: Frontend — Forensic Report View
**Who**: M3 (Pixel)  
**When**: Hour 9–10 (7:00–8:00 PM)

- Overall integrity score (big colored gauge)
- Per-paragraph verdict cards
- Evidence trail per flagged section
- Source match links
- Export as text/JSON

```
git commit -m "feat: forensic report dashboard with integrity score"
```

---

### COMMIT 16: Frontend — Source Matches Panel
**Who**: M3 (Pixel)  
**When**: Hour 10–11 (8:00–9:00 PM)

- For each flagged paragraph: top arxiv matches
- Paper title, authors, year, URL, similarity %
- Progress bars for match confidence

```
git commit -m "feat: source paper matches panel with arxiv links"
```

---

### COMMIT 17: Edge Case Handling
**Who**: M2 (Engine) + M5 (Shield)  
**When**: Hour 11–13 (9:00–11:00 PM)

Per blueprint Section 8 — handle:
- **PDF failure**: 3-tier fallback (unstructured → PyMuPDF → raw chunk) + `degraded_mode` flag
- **HDBSCAN saturation**: >80% noise → override all to Cluster 0
- **Zero-variance features**: Skip clustering, report single author
- **Empty/scanned PDF**: Clear error with "No text detected"
- **Short paper** (<5 paragraphs): Warning + skip clustering
- **arxiv 429**: tenacity handles retry
- **GPT timeout**: Partial results with warning

```
git commit -m "feat: comprehensive edge case handling with fallback chain"
```

---

### COMMIT 18: Loading States + Error UI
**Who**: M3 (Pixel)  
**When**: Hour 11–12 (9:00–10:00 PM)

- Step-by-step progress: "Parsing PDF... Extracting features... Clustering... Analyzing..."
- Skeleton loading for each panel
- Error/warning cards for degraded mode
- Retry button

```
git commit -m "feat: loading states, progress indicator, and error UI"
```

---

### COMMIT 19: Deployment
**Who**: M5 (Shield)  
**When**: Hour 12–14 (10:00 PM–12:00 AM)

- Backend → Render: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Frontend → Vercel: static deploy
- Environment variables configured
- `python -m spacy download en_core_web_sm` in build command

```
git commit -m "feat: deployment to Render + Vercel"
```

---

### COMMIT 20: README + AI Disclosure
**Who**: M5 (Shield)  
**When**: Hour 14–16 (12:00–2:00 AM)

- Full README with setup, architecture diagram, screenshots
- AI tools disclosure (GPT-4o-mini, GPT-4o, all-MiniLM-L6-v2)
- Demo video link

```
git commit -m "docs: README with architecture, setup guide, and AI disclosure"
```

---

### COMMIT 21: Final Polish
**Who**: ALL  
**When**: Hour 16–22 (2:00–8:00 AM)

- UI animations, hover effects
- Performance optimizations
- Additional test PDFs
- Bug fixes
- Code comments

```
git commit -m "polish: UI animations, performance, and final bug fixes"
```

---

## 📊 Timeline — Gantt View

```
HOUR  0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15-22
      │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │
M1    │   │C4─────────┤C5──┤C6──┤   │   │C14─────────┤   │   │   │POLISH
M2    │   │C3──────────────┤C7──────────┤   │   │C17─────────┤   │POLISH
M3    │   │C8──────────────┤C9──┤C12┤C13┤C15────┤C16─┤C18────┤   │POLISH
M4    │C2─────┤   │   │   │C10─────────────┤C11─────────┤   │   │POLISH
M5    │C1─┤   │   │   │   │   │   │   │   │   │   │C19─────┤C20──┤POLISH
      │   │   │   │   │   │   │   │   │   │   │   │   │   │   │   │
      ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼
     10AM     12PM     2PM      4PM  R1  6PM     8PM     10PM    12AM R2
```

---

## 🎯 Judging Round Deliverables

### Round 1 (Hour 7 — 5:00 PM): Commits 1–9 done
- ✅ System design diagram
- ✅ PDF upload + dual-pass parsing
- ✅ spaCy features + HDBSCAN clustering (math proof)
- ✅ GPT reasoning for flagged boundaries
- ✅ Authorship heatmap visible
- ✅ **Demo**: Upload paper → see colored paragraphs with anomaly flags

### Round 2 (Hour 14 — 12:00 AM): Commits 1–18 done
- ✅ All analysis pillars working
- ✅ Citation forensics with temporal anomalies
- ✅ Source tracing via arxiv
- ✅ Forensic report generated
- ✅ Full dashboard with all views
- ✅ Edge cases handled

### Round 3 (Hour 23 — 9:00 AM): Everything done
- ✅ Deployed and accessible
- ✅ Demo video + README
- ✅ AI tools disclosed
- ✅ Polish and optimizations

---

## ⚡ Quick Start

```bash
# Clone
git clone https://github.com/HarshalAndhale9657/P.R.I.S.M.git
cd P.R.I.S.M/backend

# Setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m nltk.downloader punkt_tab

# Env
cp .env.example .env
# Edit .env → add OPENAI_API_KEY

# Run
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd ../frontend
python -m http.server 3000
# Open http://localhost:3000
```

---

## 🏆 Why This Hybrid Approach Wins

| What Judges See | Pure Math (Blueprint) | Pure AI (Our v1) | **Hybrid (P.R.I.S.M. v2)** |
|----------------|----------------------|-------------------|---------------------------|
| Author detection | ✅ HDBSCAN clusters | ✅ GPT comparisons | ✅ **Both — math proof + AI explanation** |
| Explainability | ❌ Just cluster IDs | ✅ Natural language | ✅ **"Cluster -1 because Yule's K dropped 40% + GPT says tone shifted"** |
| Determinism | ✅ Same input = same output | ❌ GPT varies | ✅ **Math layer is deterministic, AI layer adds color** |
| Speed | ✅ Milliseconds | ❌ 30-60s API calls | ✅ **Math instant, GPT only on flagged sections** |
| Cost | ✅ $0 | ❌ $0.15/paper | 🟡 **~$0.05/paper (GPT only on anomalies)** |
| Crash resistance | ✅ No external deps | ❌ API failures | ✅ **Local model works even if OpenAI is down** |
| Judge wow factor | 🟡 Technically correct | 🟡 AI-powered | 🟢 **"We use mathematical proof AND AI reasoning"** |
