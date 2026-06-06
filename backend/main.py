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

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import List, Optional

from services.pdf_parser import AcademicPDFParser
from services.feature_engine import FeatureEngine
from services.hdbscan_detector import AuthorshipClustering
from services.gpt_analyzer import GPTAnalyzer
from services.citation_forensics import CitationForensics
from services.report_generator import ReportGenerator
from services.source_tracer import SourceTracer
from models import PipelineContext, WarningCode, WarningSeverity

# ─── Logging Setup ───────────────────────────────────────────────────────────
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


# ─── Benchmark Request Models ─────────────────────────────────────────────────

class EvaluationRecord(BaseModel):
    paragraph_id: str
    ground_truth_anomaly: bool = Field(..., description="Human-labelled ground truth")
    predicted_anomaly: bool = Field(..., description="Model prediction")
    tracer_fired: bool = Field(False, description="Whether source tracer returned a match")
    tracer_match_confirmed: Optional[bool] = Field(
        None,
        description="Human confirmation that the tracer match was a genuine source. "
                    "None = unreviewed, True = confirmed, False = hallucination."
    )


class BenchmarkRequest(BaseModel):
    records: List[EvaluationRecord] = Field(..., min_items=1)
    label: Optional[str] = Field(None, description="Optional run label / experiment name")


# ─── Helper: PDF Validation ─────────────────────────────────────────────────

def _validate_pdf(file: UploadFile):
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")


async def _read_pdf_bytes(file: UploadFile) -> bytes:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    return content


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {"status": "ok", "message": "P.R.I.S.M. Backend is running"}


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    _validate_pdf(file)

    try:
        content = await file.read()
        file_size = len(content)

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

        parsed = pdf_parser.parse(content, ctx)

        if not parsed["paragraphs"]:
            raise HTTPException(
                status_code=422,
                detail="No text detected — the PDF may be scanned or image-only.",
            )

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

        parsed = pdf_parser.parse(content, ctx)

        if not parsed["paragraphs"]:
            raise HTTPException(
                status_code=422,
                detail="No text detected — the PDF may be scanned or image-only.",
            )

        features = feature_engine.extract_all(parsed["paragraphs"], ctx)

        valid_count = features["valid_paragraphs"]
        
       
        ctx.total_samples = valid_count 

        if valid_count < 3:
            ctx.degraded_mode = True
            cluster_result = {
                "estimated_authors": 1,
                "anomaly_count": 0,
                "noise_percentage": 0.0,
                "boundaries": [],
                "cluster_sizes": {0: valid_count},
                "confidence": 1.0,
                "noise_override": True,
                "too_short": True
            }
            
            for p in parsed["paragraphs"]:
                p["cluster_id"] = 0
        else:
            
            cluster_result = clustering_engine.cluster(features["feature_matrix"], ctx)
    

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

        parsed = pdf_parser.parse(content, ctx)
        if not parsed["paragraphs"]:
            raise HTTPException(status_code=422, detail="No text detected.")

        features = feature_engine.extract_all(parsed["paragraphs"], ctx)
        cluster_result = clustering_engine.cluster(features["feature_matrix"], ctx)
        enriched_paragraphs = clustering_engine.get_cluster_summary(parsed["paragraphs"], cluster_result)
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

        parsed = pdf_parser.parse(content, ctx)
        if not parsed["paragraphs"]:
            raise HTTPException(status_code=422, detail="No text detected.")

        features = feature_engine.extract_all(parsed["paragraphs"], ctx)
        cluster_result = clustering_engine.cluster(features["feature_matrix"], ctx)
        enriched_paragraphs = clustering_engine.get_cluster_summary(parsed["paragraphs"], cluster_result)
        reasoning = await gpt_analyzer.analyze_boundaries(parsed["paragraphs"], cluster_result, ctx)
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
            ][:1]
            sources = await run_in_threadpool(source_tracer.trace, anomalous_paragraphs, ctx)
        except Exception as e:
            logger.error(f"[P.R.I.S.M.] Source tracing crashed: {e}")
            ctx.add_warning(
                WarningCode.SOURCE_EMBEDDING_FAILED, WarningSeverity.WARNING, "source_tracer",
                f"Source tracing failed unexpectedly: {str(e)[:200]}",
            )
            sources = []

        # ── Stage 7: Generate Final Report ───────────────────────────────────
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


@app.post("/api/v1/benchmark")
async def benchmark(request: BenchmarkRequest):
    """
    Offline evaluation endpoint.

    Accepts a list of labelled evaluation records and returns a classification
    report for the anomaly detector plus a hallucination rate for the source
    tracer component.

    Each record must supply:
      - ground_truth_anomaly  : human label
      - predicted_anomaly     : model output
      - tracer_fired          : whether SourceTracer returned a match
      - tracer_match_confirmed: True / False / None (unreviewed)

    Returns accuracy, precision, recall, F1, a full confusion matrix, and the
    tracer hallucination rate computed over all reviewed tracer activations.
    """
    records = request.records
    n = len(records)

    tp = sum(1 for r in records if r.ground_truth_anomaly and r.predicted_anomaly)
    tn = sum(1 for r in records if not r.ground_truth_anomaly and not r.predicted_anomaly)
    fp = sum(1 for r in records if not r.ground_truth_anomaly and r.predicted_anomaly)
    fn = sum(1 for r in records if r.ground_truth_anomaly and not r.predicted_anomaly)

    accuracy = (tp + tn) / n if n else 0.0

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    # Tracer hallucination rate — only over records where the tracer fired
    # and a human reviewer has provided a confirmed/rejected verdict.
    reviewed_activations = [
        r for r in records
        if r.tracer_fired and r.tracer_match_confirmed is not None
    ]
    hallucination_count = sum(
        1 for r in reviewed_activations if r.tracer_match_confirmed is False
    )
    tracer_total_fired = sum(1 for r in records if r.tracer_fired)
    tracer_hallucination_rate = (
        hallucination_count / len(reviewed_activations)
        if reviewed_activations
        else None
    )

    logger.info(
        f"[P.R.I.S.M.] Benchmark '{request.label or 'unlabelled'}' — "
        f"n={n} | acc={accuracy:.3f} | P={precision:.3f} | R={recall:.3f} | F1={f1:.3f} | "
        f"tracer_hallucination_rate={tracer_hallucination_rate}"
    )

    return {
        "label": request.label,
        "n_records": n,
        "classification": {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "confusion_matrix": {
                "true_positive": tp,
                "true_negative": tn,
                "false_positive": fp,
                "false_negative": fn,
            },
        },
        "source_tracer": {
            "total_fired": tracer_total_fired,
            "reviewed_activations": len(reviewed_activations),
            "hallucination_count": hallucination_count,
            "hallucination_rate": (
                round(tracer_hallucination_rate, 4)
                if tracer_hallucination_rate is not None
                else None
            ),
            "note": (
                "hallucination_rate is null — no reviewed tracer activations in this batch"
                if tracer_hallucination_rate is None
                else None
            ),
        },
    }