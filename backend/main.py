import io
import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from services.pdf_parser import AcademicPDFParser
from services.feature_engine import FeatureEngine

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
