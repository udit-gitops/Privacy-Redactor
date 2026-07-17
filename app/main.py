import io
import os
import zipfile
import xml.etree.ElementTree as ET
import fitz          # PyMuPDF — text extraction + OCR fallback
import pdfplumber    # table extraction from PDFs
import pytesseract
from PIL import Image, ImageDraw
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import engine, get_db
from app import models, services

# Create DB tables on startup (only if database is configured)
if engine:
    try:
        models.Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"⚠️  Could not create database tables: {e}")

app = FastAPI(title="Privacy & Compliance Redactor API")

# Allow requests from frontend domains (local dev + production)
FRONTEND_URLS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://10.140.255.63:3000",
    "https://spectacular-commitment-production-123b.up.railway.app",
    "http://spectacular-commitment-production-123b.up.railway.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_URLS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Restricted to needed methods only
    allow_headers=["*"],
)

class RedactRequest(BaseModel):
    text: str

# Point Tesseract to the right binary (Windows needs an explicit path)
_tesseract_cmd = os.getenv("TESSERACT_CMD")
if _tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
elif os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:
    print("⚠️  WARNING: Tesseract OCR not found. Image/scanned PDF redaction will fail.")
    print("   Install Tesseract or set TESSERACT_CMD environment variable.")


# ── Health Check Endpoint ────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint — verify backend is running and accessible."""
    return {
        "status": "ok",
        "service": "Privacy & Compliance Redactor API",
        "database": "configured" if engine else "not configured (telemetry disabled)",
        "groq_ai": "enabled" if services.groq_client else "disabled"
    }


# ── DB helper ──────���────────────────────────────────────────────────────────

def save_log(db: Session, result: dict):
    """Save a single redaction event to the database for telemetry.
    Silently skipped if database is not configured.
    """
    if db is None:  # Database not configured
        return
    try:
        log = models.RedactionLog(
            input_characters=result["metrics"]["characters_processed"],
            entities_redacted=result["metrics"]["identities_masked"],
        )
        db.add(log)
        db.commit()
        db.refresh(log)
    except Exception as e:
        print(f"⚠️  Failed to save telemetry log: {e}")


# ── Text extraction helpers ──────────────────────────────────────────────────

def extract_text_from_image(file_bytes: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Tesseract OCR not found. Install Tesseract-OCR or set TESSERACT_CMD in your .env file."
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR failed: {e}")


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extracts text from PDFs using a three-layer approach:
      1. PyMuPDF (fitz) for layout-aware text blocks
      2. pdfplumber for table extraction (formatted as markdown-style rows)
      3. Tesseract OCR fallback for scanned/image-only pages
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pdf = pdfplumber.open(io.BytesIO(file_bytes))
        pages = []

        for i, page in enumerate(doc):
            plumber_page = pdf.pages[i]

            # Layer 1: layout-aware text blocks, sorted top-to-bottom, left-to-right
            blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
            page_text = "\n\n".join(b[4].strip() for b in blocks if b[4].strip())

            # Layer 2: OCR fallback for scanned pages (less than 50 chars = likely image)
            if len(page_text.strip()) < 50:
                pix = page.get_pixmap(dpi=150)
                page_text += "\n--- OCR ---\n" + extract_text_from_image(pix.tobytes("png"))

            # Layer 3: Tables from pdfplumber, formatted as markdown rows
            tables = plumber_page.extract_tables()
            if tables:
                table_text = []
                for table in tables:
                    rows = ["| " + " | ".join(str(c) if c else "" for c in row) + " |" for row in table if row]
                    table_text.append("\n".join(rows))
                page_text += "\n--- Tables ---\n" + "\n\n".join(table_text)

            pages.append(page_text)

        doc.close()
        pdf.close()
        return "\n--- Page Break ---\n".join(pages)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF parsing failed: {e}")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Extracts plain text from a .docx file by reading its internal XML.
    Note: python-docx library would do this in 3 lines if you add it to requirements.txt —
    but this approach has zero extra dependencies and is explainable in an interview.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as docx:
            root = ET.parse(docx.open("word/document.xml")).getroot()
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paragraphs = []
            for para in root.iter(f"{ns}p"):
                text = "".join(run.text for run in para.iter(f"{ns}t") if run.text)
                paragraphs.append(text)
            return "\n".join(paragraphs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DOCX parsing failed: {e}")


def extract_text_from_txt(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


# ── Visual redaction helpers ─────────────────────────────────────────────────

def redact_pdf_visual(file_bytes: bytes, entities: list) -> bytes:
    """Blacks out detected entity text in the actual PDF using PyMuPDF redaction annotations."""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            for ent in entities:
                text = ent.get("text", "").strip()
                if len(text) < 2:
                    continue
                for rect in page.search_for(text):
                    page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()
        out = doc.write()
        doc.close()
        return out
    except Exception as e:
        print("PDF visual redaction error:", e)
        return file_bytes


def redact_image_visual(file_bytes: bytes, entities: list) -> bytes:
    """Draws black rectangles over detected entity words in an image using Tesseract bounding boxes."""
    try:
        image = Image.open(io.BytesIO(file_bytes))
        draw = ImageDraw.Draw(image)
        ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        # Collect individual words from all entity texts
        terms = {word.lower() for ent in entities for word in ent.get("text", "").split() if len(word) > 1}

        for i, word in enumerate(ocr_data["text"]):
            if word.strip().lower() in terms:
                x, y, w, h = ocr_data["left"][i], ocr_data["top"][i], ocr_data["width"][i], ocr_data["height"][i]
                draw.rectangle([x, y, x + w, y + h], fill="black")

        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()
    except Exception as e:
        print("Image visual redaction error:", e)
        return file_bytes


# ── API Routes ──────────────────────────────────────────────────────────────

@app.post("/api/v1/redact")
async def redact_text(
    payload: RedactRequest,
    redact_style: str = Query("PLACEHOLDER"),  # ← FIX: Use Query() to capture from query params
    db: Session = Depends(get_db)
):
    try:
        result = services.process_text_redaction(payload.text, redact_style)
        save_log(db, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/redact-file")
async def redact_file(
    file: UploadFile = File(...),
    redact_style: str = Form("PLACEHOLDER"),       # Form field — comes from multipart/form-data
    return_redacted_document: str = Form("false"), # Form field — booleans come as strings in forms
    db: Session = Depends(get_db)
):
    try:
        file_bytes = await file.read()
        name = file.filename.lower()

        # Route to the right extractor based on file extension
        if name.endswith(".pdf"):
            text = extract_text_from_pdf(file_bytes)
        elif name.endswith(".docx"):
            text = extract_text_from_docx(file_bytes)
        elif name.endswith(".txt"):
            text = extract_text_from_txt(file_bytes)
        elif name.endswith((".png", ".jpg", ".jpeg", ".tiff")):
            text = extract_text_from_image(file_bytes)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, DOCX, TXT, PNG, JPG, JPEG, or TIFF.")

        if not text.strip():
            raise HTTPException(status_code=400, detail="No readable text found in the uploaded file.")

        result = services.process_text_redaction(text, redact_style)
        save_log(db, result)  # reused helper — no duplicate code

        # Form fields come as strings — "true"/"false", so compare explicitly
        if return_redacted_document.lower() == "true":
            if name.endswith(".pdf"):
                out_bytes = redact_pdf_visual(file_bytes, result["entities"])
                return StreamingResponse(io.BytesIO(out_bytes), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=redacted_{file.filename}"})
            elif name.endswith((".png", ".jpg", ".jpeg", ".tiff")):
                out_bytes = redact_image_visual(file_bytes, result["entities"])
                return StreamingResponse(io.BytesIO(out_bytes), media_type="image/png",
                    headers={"Content-Disposition": "attachment; filename=redacted_image.png"})
            elif name.endswith(".txt"):
                return StreamingResponse(io.BytesIO(result["secured_text"].encode()), media_type="text/plain",
                    headers={"Content-Disposition": f"attachment; filename=redacted_{file.filename}"})

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
