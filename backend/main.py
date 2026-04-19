"""
P.R.I.S.M. — FastAPI Backend
==============================
Main application with all API endpoints.
Comprehensive edge-case handling via PipelineContext threading.
"""

import os
import io
import logging
import fitz  # PyMuPDF

# Load environment variables BEFORE any service imports
# Services like GPTAnalyzer and ReportGenerator read OPENAI_API_KEY on init
from dotenv import load_dotenv
load_dotenv()  # Loads from backend/.env or parent .env
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

from services.pdf_parser import AcademicPDFParser
from services.feature_engine import FeatureEngine
from services.clustering import AuthorshipClustering
from services.gpt_analyzer import GPTAnalyzer
from services.citation_forensics import CitationForensics
from services.report_generator import ReportGenerator
from services.source_tracer import SourceTracer
from models import PipelineContext, WarningCode, WarningSeverity# ─── Logging Setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("prism")

# ─── App Initialization ─────────────────────────────────────────────────────
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
clustering_engine = AuthorshipClustering(min_cluster_size=2, min_samples=2)
gpt_analyzer = GPTAnalyzer()
citation_forensics = CitationForensics(temporal_threshold=10)
source_tracer = SourceTracer(similarity_threshold=0.50)
report_generator = ReportGenerator()
# ─── Helper: PDF Validation ─────────────────────────────────────────────────

def _validate_pdf(file: UploadFile):
    """Validate that an uploaded file is a PDF."""
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")


async def _read_pdf_bytes(file: UploadFile) -> bytes:
    """Read and validate PDF bytes from upload."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    return content


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.get("/")
async def health_check():
    """Health check endpoint to verify backend is running."""
    return {"status": "ok", "message": "P.R.I.S.M. Backend is running"}


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Receives a PDF, validates it, and returns basic metadata."""
    _validate_pdf(file)

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
    _validate_pdf(file)

    try:
        content = await _read_pdf_bytes(file)
        ctx = PipelineContext()

        result = pdf_parser.parse(content, ctx)

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
            **ctx.to_dict(),
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
    _validate_pdf(file)

    try:
        content = await _read_pdf_bytes(file)
        ctx = PipelineContext()

        # Stage 1: Parse PDF
        parsed = pdf_parser.parse(content, ctx)

        if not parsed["paragraphs"]:
            raise HTTPException(
                status_code=422,
                detail="No text detected — the PDF may be scanned or image-only.",
            )

        # Stage 2: Extract stylometric features
        features = feature_engine.extract_all(parsed["paragraphs"], ctx)

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
            **ctx.to_dict(),
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
    _validate_pdf(file)

    try:
        content = await _read_pdf_bytes(file)
        ctx = PipelineContext()

        # Stage 1: Parse PDF
        parsed = pdf_parser.parse(content, ctx)

        if not parsed["paragraphs"]:
            raise HTTPException(
                status_code=422,
                detail="No text detected — the PDF may be scanned or image-only.",
            )

        # Stage 2: Extract stylometric features
        features = feature_engine.extract_all(parsed["paragraphs"], ctx)

        # Stage 3: HDBSCAN clustering
        cluster_result = clustering_engine.cluster(features["feature_matrix"], ctx)

        # Enrich paragraphs with cluster info
        enriched_paragraphs = clustering_engine.get_cluster_summary(
            parsed["paragraphs"], cluster_result
        )

        return {
            "filename": file.filename,
            "page_count": parsed["page_count"],
            "extraction_method": parsed["extraction_method"],
            "degraded_mode": parsed["degraded_mode"] or ctx.degraded_mode,
            "total_paragraphs": features["total_paragraphs"],
            "valid_paragraphs": features["valid_paragraphs"],
            "estimated_authors": cluster_result["estimated_authors"],
            "anomaly_count": cluster_result["anomaly_count"],
            "noise_percentage": cluster_result["noise_percentage"],
            "boundaries": cluster_result["boundaries"],
            "cluster_sizes": cluster_result["cluster_sizes"],
            "confidence": cluster_result["confidence"],
            "noise_override": cluster_result["noise_override"],
            "too_short": cluster_result["too_short"],
            "feature_names": features["feature_names"],
            "profiles": features["profiles"],
            "paragraphs": enriched_paragraphs,
            "references": parsed["references"],
            **ctx.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clustering failed: {str(e)}")


@app.post("/api/reasoning")
async def analyze_reasoning(file: UploadFile = File(...)):
    """
    Stage 1-4 Pipeline: Parse → Features → Cluster → GPT Reasoning.
    Returns clustered paragraphs with natural language GPT-4o-mini
    explanations for anomalous boundaries.
    """
    _validate_pdf(file)

    try:
        content = await _read_pdf_bytes(file)
        ctx = PipelineContext()

        # Stage 1: Parse PDF
        parsed = pdf_parser.parse(content, ctx)
        if not parsed["paragraphs"]:
            raise HTTPException(status_code=422, detail="No text detected.")

        # Stage 2: Extract stylometric features
        features = feature_engine.extract_all(parsed["paragraphs"], ctx)

        # Stage 3: HDBSCAN clustering
        cluster_result = clustering_engine.cluster(features["feature_matrix"], ctx)
        enriched_paragraphs = clustering_engine.get_cluster_summary(parsed["paragraphs"], cluster_result)

        # Stage 4: GPT Reasoning on flagged boundaries
        reasoning = await gpt_analyzer.analyze_boundaries(parsed["paragraphs"], cluster_result, ctx)

        return {
            "filename": file.filename,
            "clustering": {
                "estimated_authors": cluster_result["estimated_authors"],
                "anomaly_count": cluster_result["anomaly_count"],
                "noise_percentage": cluster_result["noise_percentage"],
                "confidence": cluster_result["confidence"],
                "too_short": cluster_result["too_short"],
                "noise_override": cluster_result["noise_override"],
            },
            "reasoning": reasoning,
            "paragraphs": enriched_paragraphs,
            **ctx.to_dict(),
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
    _validate_pdf(file)

    try:
        content = await _read_pdf_bytes(file)
        ctx = PipelineContext()

        # Stage 1: Parse PDF
        parsed = pdf_parser.parse(content, ctx)
        if not parsed["paragraphs"]:
            raise HTTPException(status_code=422, detail="No text detected.")

        # Stage 2: Extract stylometric features
        features = feature_engine.extract_all(parsed["paragraphs"], ctx)

        # Stage 3: HDBSCAN clustering
        cluster_result = clustering_engine.cluster(features["feature_matrix"], ctx)
        enriched_paragraphs = clustering_engine.get_cluster_summary(parsed["paragraphs"], cluster_result)

        # Stage 4: GPT Reasoning on flagged boundaries
        reasoning = await gpt_analyzer.analyze_boundaries(parsed["paragraphs"], cluster_result, ctx)

        # Stage 5: Citation Forensics
        citations = citation_forensics.analyze(
            parsed["paragraphs"], parsed["references"], cluster_result, ctx
        )

        return {
            "filename": file.filename,
            "clustering": {
                "estimated_authors": cluster_result["estimated_authors"],
                "anomaly_count": cluster_result["anomaly_count"],
                "noise_percentage": cluster_result["noise_percentage"],
                "confidence": cluster_result["confidence"],
                "too_short": cluster_result["too_short"],
                "noise_override": cluster_result["noise_override"],
            },
            "reasoning": reasoning,
            "citations": citations,
            "paragraphs": enriched_paragraphs,
            "references": parsed["references"],
            **ctx.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Citation analysis failed: {str(e)}")

@app.post("/api/analyze")
async def full_analysis(file: UploadFile = File(...)):
    """
    Full Stage 1-7 analysis pipeline with comprehensive edge-case handling.
    """
    _validate_pdf(file)

    try:
        content = await _read_pdf_bytes(file)
        ctx = PipelineContext()

        # ── Stage 1: Parse PDF ───────────────────────────────────────────────
        parsed = await run_in_threadpool(pdf_parser.parse_safe, content, ctx)

        if not parsed["paragraphs"]:
            # Return a valid response with warnings instead of HTTP 422
            return {
                "filename": file.filename,
                "status": "error",
                "error": "No text could be extracted from this PDF.",
                "page_count": parsed.get("page_count", 0),
                "extraction_method": parsed.get("extraction_method", "none"),
                "paragraphs": [],
                "clustering": None,
                "reasoning": None,
                "citations": None,
                "sources": None,
                "report": None,
                "metadata": {
                    "pages": parsed.get("page_count", 0),
                    "total_paragraphs": 0,
                },
                **ctx.to_dict(),
            }

        # ── Stage 2: Extract features (spaCy) ───────────────────────────────
        features = await run_in_threadpool(feature_engine.extract_all, parsed["paragraphs"], ctx)

        # ── Stage 3: Cluster (HDBSCAN) ──────────────────────────────────────
        cluster_result = await run_in_threadpool(clustering_engine.cluster, features["feature_matrix"], ctx)
        enriched_paragraphs = await run_in_threadpool(
            clustering_engine.get_cluster_summary, parsed["paragraphs"], cluster_result
        )

        # ── Stage 4: GPT reasoning (flagged paragraphs only) ────────────────
        try:
            reasoning = await gpt_analyzer.analyze_boundaries(
                parsed["paragraphs"], cluster_result, ctx
            )
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] GPT reasoning crashed: {e}")
            ctx.add_warning(
                WarningCode.GPT_TIMEOUT, WarningSeverity.ERROR, "gpt_analyzer",
                f"GPT reasoning failed unexpectedly: {str(e)[:200]}",
            )
            reasoning = {
                "available": False,
                "error": str(e),
                "boundary_explanations": {},
                "anomaly_profiles": {},
            }

        # ── Stage 5: Citation forensics ──────────────────────────────────────
        try:
            citations = citation_forensics.analyze(
                parsed["paragraphs"], parsed["references"], cluster_result, ctx
            )
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Citation forensics crashed: {e}")
            citations = {
                "per_paragraph": [],
                "total_citations_found": 0,
                "error": str(e),
            }

        # ── Stage 6: Source tracing (anomalies only) ─────────────────────────
        try:
            anomalous_paragraphs = [
                p for p in enriched_paragraphs if p.get("is_anomaly")
            ]
            sources = await run_in_threadpool(source_tracer.trace, anomalous_paragraphs, ctx)
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Source tracing crashed: {e}")
            ctx.add_warning(
                WarningCode.SOURCE_EMBEDDING_FAILED, WarningSeverity.WARNING, "source_tracer",
                f"Source tracing failed unexpectedly: {str(e)[:200]}",
            )
            sources = []

        # ── Stage 7: Generate Final Report ───────────────────────────────
        analysis_data = {
            "clustering": cluster_result,
            "reasoning": reasoning,
            "citations": citations,
            "sources": sources
        }
        report = await report_generator.generate_report(analysis_data)

        return {
            "filename": file.filename,
            "status": "success",
            "paragraphs": enriched_paragraphs,
            "clustering": {
                "clusters": cluster_result["clusters"],
                "estimated_authors": cluster_result["estimated_authors"],
                "anomaly_indices": cluster_result["anomaly_indices"],
                "anomaly_count": cluster_result["anomaly_count"],
                "boundaries": cluster_result["boundaries"],
                "boundary_count": cluster_result["boundary_count"],
                "noise_percentage": cluster_result["noise_percentage"],
                "cluster_sizes": cluster_result["cluster_sizes"],
                "confidence": cluster_result["confidence"],
                "noise_override": cluster_result["noise_override"],
                "too_short": cluster_result["too_short"],
            },
            "features": {
                "feature_names": features["feature_names"],
                "profiles": features["profiles"],
                "total_paragraphs": features["total_paragraphs"],
                "valid_paragraphs": features["valid_paragraphs"],
            },
            "reasoning": reasoning,
            "citations": citations,
            "sources": sources,
            "references": parsed["references"],
            "report": report,
            "metadata": {
                "pages": parsed["page_count"],
                "total_paragraphs": len(parsed["paragraphs"]),
                "extraction_method": parsed["extraction_method"],
                "degraded_mode": parsed["degraded_mode"] or ctx.degraded_mode,
            },
            **ctx.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[P.R.I.S.M.] Full analysis pipeline crashed")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis pipeline failed: {str(e)}",
        )
