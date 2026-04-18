import io
import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
