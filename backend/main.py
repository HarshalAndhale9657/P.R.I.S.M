"""
P.R.I.S.M. — FastAPI Backend
==============================
Main application with all API endpoints.
Comprehensive edge-case handling via PipelineContext threading.
"""

import os
import io
import re
import time
import uuid
import hashlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple

import fitz  # PyMuPDF

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
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
from services.plagiarism_matcher import PlagiarismMatcher, SourceDoc
from services.academic_corpus import search as academic_search
from pipeline import CheckContext, Document, default_check_stages, run_pipeline
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

# CORS — explicit allow-list (override in prod via PRISM_ALLOWED_ORIGINS, comma-separated).
# Wildcard + credentials is invalid/insecure, so we do not use it.
_DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("PRISM_ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
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
plagiarism_matcher = PlagiarismMatcher()

# ─── Originality-checker upload guards ────────────────────────────────────────
MAX_REFERENCE_FILES = 25
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB per file


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


def _enforce_size(content: bytes) -> None:
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large — maximum {MAX_FILE_BYTES // (1024 * 1024)} MB.",
        )


async def _read_pdf_bytes(file: UploadFile) -> bytes:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    _enforce_size(content)
    return content


def _server_error(context: str) -> HTTPException:
    """Log the active exception server-side and return a generic 500 (no detail leakage)."""
    logger.exception("[P.R.I.S.M.] %s", context)
    return HTTPException(status_code=500, detail=f"{context}.")


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {"status": "ok", "message": "P.R.I.S.M. Backend is running"}


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    _validate_pdf(file)

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        _enforce_size(content)
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
    except HTTPException:
        raise
    except Exception:
        logger.exception("[P.R.I.S.M.] /api/upload failed")
        raise HTTPException(status_code=500, detail="Failed to process the uploaded PDF.")


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
    except Exception:
        raise _server_error("PDF parsing failed")


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
    except Exception:
        raise _server_error("Feature extraction failed")


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
    except Exception:
        raise _server_error("Clustering failed")


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
    except Exception:
        raise _server_error("Reasoning analysis failed")


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
    except Exception:
        raise _server_error("Citation analysis failed")


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
    except Exception:
        raise _server_error("Analysis pipeline failed")


# ─── Originality Checker (Phase 1: source-attribution plagiarism) ─────────────

def _validate_doc(file: UploadFile) -> None:
    name = (file.filename or "").lower()
    if not (name.endswith(".pdf") or name.endswith(".txt")):
        if file.content_type not in ("application/pdf", "text/plain"):
            raise HTTPException(status_code=400, detail="Only PDF or TXT files are supported.")


def _paragraphs_from_plaintext(raw: str) -> List[dict]:
    out, idx = [], 0
    for chunk in re.split(r"\n\s*\n", raw):
        text = chunk.strip()
        if text:
            out.append({"index": idx, "text": text, "page": None})
            idx += 1
    return out


def _assemble_document(paragraphs: List[dict]):
    """Concatenate paragraphs into one text blob, recording char offsets per paragraph."""
    sep = "\n\n"
    parts: List[str] = []
    offsets: List[dict] = []
    pos = 0
    for p in paragraphs:
        text = (p.get("text") or "").strip()
        if not text:
            continue
        start = pos
        parts.append(text)
        pos += len(text)
        offsets.append({"index": p.get("index"), "page": p.get("page"), "start": start, "end": pos})
        parts.append(sep)
        pos += len(sep)
    return "".join(parts), offsets


def _extract_document(filename: str, content: bytes, ctx: PipelineContext):
    """Extract (doc_text, paragraph_offsets) from an uploaded PDF or TXT file."""
    name = (filename or "").lower()
    if name.endswith(".txt"):
        paragraphs = _paragraphs_from_plaintext(content.decode("utf-8", errors="replace"))
    else:
        parsed = pdf_parser.parse_safe(content, ctx)
        paragraphs = parsed.get("paragraphs", [])
        if not paragraphs and not name.endswith(".pdf"):
            paragraphs = _paragraphs_from_plaintext(content.decode("utf-8", errors="replace"))
    return _assemble_document(paragraphs)


# ─── Async job model for /api/check ──────────────────────────────────────────
# In-process job store + bounded worker pool (no external infra). Suitable for a
# single-process deployment; use Redis/a real queue to scale across workers.

class CheckError(Exception):
    """A user-safe error surfaced as a job error (not an internal detail)."""


_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()
_RESULT_CACHE: dict = {}                 # content_hash -> result dict (idempotency)
_MAX_JOBS = 200
_MAX_CACHE = 100
_check_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="prism-check")


def _new_job() -> str:
    job_id = uuid.uuid4().hex
    now = time.time()
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "queued", "created": now, "updated": now, "result": None, "error": None}
        if len(_JOBS) > _MAX_JOBS:  # evict oldest
            for k, _ in sorted(_JOBS.items(), key=lambda kv: kv[1]["created"])[: len(_JOBS) - _MAX_JOBS]:
                _JOBS.pop(k, None)
    return job_id


def _set_job(job_id: str, **fields) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(fields)
            job["updated"] = time.time()


def _get_job(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _content_hash(paper_bytes: bytes, refs: List[Tuple[str, bytes]], use_academic: bool) -> str:
    h = hashlib.sha256()
    h.update(paper_bytes)
    for _, raw in sorted(refs, key=lambda r: r[1]):
        h.update(b"\x00")
        h.update(raw)
    h.update(b"|academic=" + (b"1" if use_academic else b"0"))
    return h.hexdigest()


def _compute_check(paper_name: str, paper_bytes: bytes, refs: List[Tuple[str, bytes]],
                   use_academic: bool, base_warnings: List[str]) -> dict:
    """Heavy work (runs in a worker thread): extract → run the check pipeline → assemble.

    The pluggable pipeline (ADR-0015/0016) does retrieve → match → localize. The
    matcher and academic-search fn are passed in from the module globals at call
    time, so both stay the tests' monkeypatch seams.
    """
    warnings = list(base_warnings)

    doc_text, paragraphs = _extract_document(paper_name, paper_bytes, PipelineContext())
    if not doc_text.strip():
        raise CheckError("No readable text found in the document (it may be scanned or image-only).")

    sources: List[SourceDoc] = []
    for i, (name, raw) in enumerate(refs):
        ref_text, _ = _extract_document(name, raw, PipelineContext())
        if ref_text.strip():
            sources.append(SourceDoc(id=f"src-{i}", name=name, text=ref_text))
        else:
            warnings.append(f"Skipped '{name}': no readable text extracted.")

    ctx = CheckContext(
        document=Document(name=paper_name, text=doc_text, paragraphs=paragraphs),
        sources=sources,
        warnings=warnings,
    )
    stages = default_check_stages(plagiarism_matcher, academic_search, use_academic=use_academic)
    ctx = run_pipeline(ctx, stages)

    if not ctx.sources:
        raise CheckError("No usable sources to compare against (no readable references and no academic matches found).")

    return {
        "filename": paper_name,
        "status": "success",
        "document_text": doc_text,
        "paragraphs": paragraphs,
        "academic_used": ctx.artifacts.get("academic_used", False),
        "sources": [{"id": s.id, "name": s.name, "origin": s.origin, "url": s.url} for s in ctx.sources],
        "overall": ctx.artifacts["overall"],
        "per_source": ctx.artifacts["per_source"],
        "matches": ctx.artifacts["matches"],
        "paraphrase_enabled": ctx.artifacts.get("paraphrase_enabled"),
        "warnings": ctx.warnings,
    }


def _run_job(job_id: str, paper_name: str, paper_bytes: bytes, refs: List[Tuple[str, bytes]],
             use_academic: bool, base_warnings: List[str], content_hash: str) -> None:
    _set_job(job_id, status="running")
    try:
        cached = _RESULT_CACHE.get(content_hash)
        result = cached if cached is not None else _compute_check(
            paper_name, paper_bytes, refs, use_academic, base_warnings
        )
        if cached is None:
            with _JOBS_LOCK:
                _RESULT_CACHE[content_hash] = result
                if len(_RESULT_CACHE) > _MAX_CACHE:
                    _RESULT_CACHE.pop(next(iter(_RESULT_CACHE)), None)
        _set_job(job_id, status="done", result=result)
    except CheckError as ce:
        _set_job(job_id, status="error", error=str(ce))
    except Exception:
        logger.exception("[P.R.I.S.M.] Originality job failed")
        _set_job(job_id, status="error", error="Originality check failed. Please try again.")


@app.post("/api/check", status_code=202)
async def submit_check(
    file: UploadFile = File(...),
    references: List[UploadFile] = File(default=[]),
    use_academic: bool = Form(default=False),
):
    """
    Submit an originality check. Reads + validates uploads synchronously (fast),
    then runs matching + optional OpenAlex search in a background worker so the
    network call never blocks the request. Returns 202 + a job id; poll
    GET /api/check/{job_id} for status and the result.
    """
    _validate_doc(file)
    paper_bytes = await _read_pdf_bytes(file)  # 400 empty / 413 too large

    if not references and not use_academic:
        raise HTTPException(
            status_code=400,
            detail="Upload at least one reference source, or enable academic-database search.",
        )

    base_warnings: List[str] = []
    if len(references) > MAX_REFERENCE_FILES:
        base_warnings.append(f"Only the first {MAX_REFERENCE_FILES} of {len(references)} reference files were used.")

    refs: List[Tuple[str, bytes]] = []
    for i, ref in enumerate(references[:MAX_REFERENCE_FILES]):
        try:
            _validate_doc(ref)
        except HTTPException:
            base_warnings.append(f"Skipped '{ref.filename}': unsupported file type.")
            continue
        raw = await ref.read()
        if not raw:
            base_warnings.append(f"Skipped '{ref.filename}': empty file.")
            continue
        if len(raw) > MAX_FILE_BYTES:
            base_warnings.append(f"Skipped '{ref.filename}': exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB limit.")
            continue
        refs.append((ref.filename or f"Source {i + 1}", raw))

    content_hash = _content_hash(paper_bytes, refs, use_academic)
    job_id = _new_job()
    _check_executor.submit(
        _run_job, job_id, file.filename, paper_bytes, refs, use_academic, base_warnings, content_hash
    )
    return {"job_id": job_id, "status": "queued", "status_url": f"/api/check/{job_id}"}


@app.get("/api/check/{job_id}")
async def check_status(job_id: str):
    """Poll a submitted check. Returns status (queued|running|done|error) and, when done, the result."""
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job id.")
    payload = {"job_id": job_id, "status": job["status"]}
    if job["status"] == "done":
        payload["result"] = job["result"]
    elif job["status"] == "error":
        payload["error"] = job["error"]
    return payload


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