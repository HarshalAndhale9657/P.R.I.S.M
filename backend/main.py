import io
import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from services.pdf_parser import AcademicPDFParser
from services.feature_engine import FeatureEngine
from services.clustering import AuthorshipClustering
from services.gpt_analyzer import GPTAnalyzer
from services.citation_forensics import CitationForensics

app = FastAPI(
    title="P.R.I.S.M. Backend API",
    description="Academic Integrity Analyzer API",
    version="1.0.0"
)

# Allow CORS for frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service instances
pdf_parser = AcademicPDFParser()
feature_engine = FeatureEngine()
clustering_engine = AuthorshipClustering(min_cluster_size=3, min_samples=2)
gpt_analyzer = GPTAnalyzer()
citation_forensics = CitationForensics(temporal_threshold=10)

@app.get("/")
async def health_check():
    """Health check endpoint to verify backend is running."""
    return {"status": "ok", "message": "P.R.I.S.M. Backend is running"}

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Receives a PDF, validates it, and returns basic metadata."""
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    try:
        content = await file.read()
        file_size = len(content)
        
        # Read the PDF from memory using PyMuPDF to get page count
        doc = fitz.open(stream=content, filetype="pdf")
        page_count = len(doc)
        doc.close()
        
        return {
            "filename": file.filename,
            "size_bytes": file_size,
            "page_count": page_count,
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {str(e)}")

@app.post("/api/parse")
async def parse_pdf(file: UploadFile = File(...)):
    """
    Parse a PDF using the dual-pass AcademicPDFParser.
    Returns extracted paragraphs, bibliography entries, and extraction metadata.
    """
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    try:
        content = await file.read()

        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        result = pdf_parser.parse(content)

        if not result["paragraphs"]:
            raise HTTPException(
                status_code=422,
                detail="No text detected — the PDF may be scanned or image-only.",
            )

        return {
            "filename": file.filename,
            "size_bytes": len(content),
            "page_count": result["page_count"],
            "total_paragraphs": len(result["paragraphs"]),
            "total_references": len(result["references"]),
            "extraction_method": result["extraction_method"],
            "degraded_mode": result["degraded_mode"],
            "paragraphs": result["paragraphs"],
            "references": result["references"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF parsing failed: {str(e)}")


@app.post("/api/features")
async def extract_features(file: UploadFile = File(...)):
    """
    Full pipeline: Parse PDF → Extract spaCy stylometric features.
    Returns paragraphs with their 7-dimensional feature profiles.
    """
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    try:
        content = await file.read()

        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        # Stage 1: Parse PDF
        parsed = pdf_parser.parse(content)

        if not parsed["paragraphs"]:
            raise HTTPException(
                status_code=422,
                detail="No text detected — the PDF may be scanned or image-only.",
            )

        # Stage 2: Extract stylometric features
        features = feature_engine.extract_all(parsed["paragraphs"])

        return {
            "filename": file.filename,
            "page_count": parsed["page_count"],
            "extraction_method": parsed["extraction_method"],
            "degraded_mode": parsed["degraded_mode"],
            "total_paragraphs": features["total_paragraphs"],
            "valid_paragraphs": features["valid_paragraphs"],
            "feature_names": features["feature_names"],
            "profiles": features["profiles"],
            "paragraphs": parsed["paragraphs"],
            "references": parsed["references"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Feature extraction failed: {str(e)}")


@app.post("/api/cluster")
async def cluster_paragraphs(file: UploadFile = File(...)):
    """
    Full pipeline: Parse PDF → Extract Features → HDBSCAN Clustering.
    Returns paragraphs enriched with cluster IDs and authorship analysis.
    """
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    try:
        content = await file.read()

        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        # Stage 1: Parse PDF
        parsed = pdf_parser.parse(content)

        if not parsed["paragraphs"]:
            raise HTTPException(
                status_code=422,
                detail="No text detected — the PDF may be scanned or image-only.",
            )

        # Stage 2: Extract stylometric features
        features = feature_engine.extract_all(parsed["paragraphs"])

        # Stage 3: HDBSCAN clustering
        cluster_result = clustering_engine.cluster(features["feature_matrix"])

        # Enrich paragraphs with cluster info
        enriched_paragraphs = clustering_engine.get_cluster_summary(
            parsed["paragraphs"], cluster_result
        )

        return {
            "filename": file.filename,
            "page_count": parsed["page_count"],
            "extraction_method": parsed["extraction_method"],
            "degraded_mode": parsed["degraded_mode"],
            "total_paragraphs": features["total_paragraphs"],
            "valid_paragraphs": features["valid_paragraphs"],
            "estimated_authors": cluster_result["estimated_authors"],
            "anomaly_count": cluster_result["anomaly_count"],
            "noise_percentage": cluster_result["noise_percentage"],
            "boundaries": cluster_result["boundaries"],
            "cluster_sizes": cluster_result["cluster_sizes"],
            "confidence": cluster_result["confidence"],
            "noise_override": cluster_result["noise_override"],
            "feature_names": features["feature_names"],
            "profiles": features["profiles"],
            "paragraphs": enriched_paragraphs,
            "references": parsed["references"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clustering failed: {str(e)}")


@app.post("/api/reasoning")
async def analyze_reasoning(file: UploadFile = File(...)):
    """
    Stage 1-4 Pipeline: Parse → Features → Cluster → GPT Reasoning.
    Returns clustered paragraphs with natural language GPT-4o-mini explanations for anomalous boundaries.
    """
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        # Stage 1: Parse PDF
        parsed = pdf_parser.parse(content)
        if not parsed["paragraphs"]:
            raise HTTPException(status_code=422, detail="No text detected.")

        # Stage 2: Extract stylometric features
        features = feature_engine.extract_all(parsed["paragraphs"])

        # Stage 3: HDBSCAN clustering
        cluster_result = clustering_engine.cluster(features["feature_matrix"])
        enriched_paragraphs = clustering_engine.get_cluster_summary(parsed["paragraphs"], cluster_result)

        # Stage 4: GPT Reasoning on flagged boundaries
        reasoning = await gpt_analyzer.analyze_boundaries(parsed["paragraphs"], cluster_result)

        return {
            "filename": file.filename,
            "clustering": {
                "estimated_authors": cluster_result["estimated_authors"],
                "anomaly_count": cluster_result["anomaly_count"],
                "noise_percentage": cluster_result["noise_percentage"],
                "confidence": cluster_result["confidence"],
            },
            "reasoning": reasoning,
            "paragraphs": enriched_paragraphs,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reasoning analysis failed: {str(e)}")


@app.post("/api/citations")
async def analyze_citations(file: UploadFile = File(...)):
    """
    Stage 1-5 Pipeline: Parse → Features → Cluster → GPT Reasoning → Citation Forensics.
    Returns clustered paragraphs with citation extraction and temporal anomaly detection.
    """
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        # Stage 1: Parse PDF
        parsed = pdf_parser.parse(content)
        if not parsed["paragraphs"]:
            raise HTTPException(status_code=422, detail="No text detected.")

        # Stage 2: Extract stylometric features
        features = feature_engine.extract_all(parsed["paragraphs"])

        # Stage 3: HDBSCAN clustering
        cluster_result = clustering_engine.cluster(features["feature_matrix"])
        enriched_paragraphs = clustering_engine.get_cluster_summary(parsed["paragraphs"], cluster_result)

        # Stage 4: GPT Reasoning on flagged boundaries
        reasoning = await gpt_analyzer.analyze_boundaries(parsed["paragraphs"], cluster_result)

        # Stage 5: Citation Forensics
        citations = citation_forensics.analyze(
            parsed["paragraphs"], parsed["references"], cluster_result
        )

        return {
            "filename": file.filename,
            "clustering": {
                "estimated_authors": cluster_result["estimated_authors"],
                "anomaly_count": cluster_result["anomaly_count"],
                "noise_percentage": cluster_result["noise_percentage"],
                "confidence": cluster_result["confidence"],
            },
            "reasoning": reasoning,
            "citations": citations,
            "paragraphs": enriched_paragraphs,
            "references": parsed["references"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Citation analysis failed: {str(e)}")
