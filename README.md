# P.R.I.S.M. — Academic Integrity Analyzer

> **P**lagiarism **R**ecognition via **I**ntegrated **S**tylometric **M**apping

A hybrid analysis pipeline combining mathematical proof (spaCy + HDBSCAN) and AI reasoning (GPT-4o) to detect "stitched" plagiarism in academic papers. Built for DevClash 2026.

## 🚀 Overview

Traditional plagiarism tools look for exact string matches. P.R.I.S.M. detects when a student splices together sections from multiple papers, even if heavily edited. It does this via a three-pillar system:
1. **Stylometric Analysis**: Identifies distinct "voices" throughout the document.
2. **Citation Forensics**: Highlights temporal or thematic breaks in the bibliography.
3. **Semantic Source Tracing**: Traces flagged anomalies back to possible source papers using local embeddings and arXiv.

## 🛠️ Hybrid Architecture
- **Parser:** unstructured + PyMuPDF
- **NLP & Math Layer:** spaCy, HDBSCAN, scikit-learn
- **AI Reasoning:** OpenAI GPT-4o-mini & GPT-4o
- **Embeddings:** all-MiniLM-L6-v2 + text-embedding-3-small
- **Backend Core:** FastAPI
- **Frontend Dashboard:** Vanilla HTML/CSS/JS with Chart.js

For detailed setup instructions and API information, please see the internal implementation guides.
