import io
import os
import zipfile
import xml.etree.ElementTree as ET
import asyncio
import fitz  # PyMuPDF — text extraction + OCR fallback
import pdfplumber  # table extraction from PDFs
import pytesseract
from PIL import Image, ImageDraw
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import engine, get_db
from app import models, services

try:
    models.Base.metadata.create_all(bind=engine)
except Exception as e:
    print(
        f"WARNING: DB table creation failed ({e.__class__.__name__}). App will run without DB logging."
    )

# ── Rate limiter — prevents API abuse ─────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Privacy & Compliance Redactor API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────────────────
# Max upload size: 10MB (prevents memory overload on Railway free tier)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Tesseract: auto-detect path (works on Linux/Docker and Windows)
_tesseract_cmd = os.getenv("TESSERACT_CMD") or (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    else None
)
if _tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd


# Tesseract language: Hindi + English for Indian documents (hin+eng)
# Falls back to English only if Hindi pack not installed
def _get_ocr_lang() -> str:
    try:
        langs = pytesseract.get_languages()
        return "hin+eng" if "hin" in langs else "eng"
    except Exception:
        return "eng"


OCR_LANG = _get_ocr_lang()


class RedactRequest(BaseModel):
    text: str


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Railway and uptime monitors ping this to keep the container warm."""
    return {"status": "ok", "ocr_lang": OCR_LANG}


# ── DB helper ─────────────────────────────────────────────────────────────────


def save_log(db: Session, result: dict):
    """Save redaction event to DB for telemetry."""
    try:
        log = models.RedactionLog(
            input_characters=result["metrics"]["characters_processed"],
            entities_redacted=result["metrics"]["identities_masked"],
        )
        db.add(log)
        db.commit()
        db.refresh(log)
    except Exception as e:
        # DB logging failure should never crash the main redaction flow
        print(f"DB log warning: {e}")
        db.rollback()


# ── Text extraction helpers ───────────────────────────────────────────────────


def extract_text_from_image(file_bytes: bytes) -> str:
    """OCR an image using Tesseract. Supports Hindi + English for Indian documents."""
    try:
        image = Image.open(io.BytesIO(file_bytes))
        # Upscale small images for better OCR accuracy
        w, h = image.size
        if w < 1000:
            image = image.resize((w * 2, h * 2), Image.LANCZOS)
        return pytesseract.image_to_string(image, lang=OCR_LANG)
    except pytesseract.TesseractNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Tesseract OCR engine not found on this server. Contact the administrator.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR failed: {e}")


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Three-layer PDF extraction:
    1. PyMuPDF (fitz) — layout-aware text blocks
    2. OCR fallback — for scanned/image-only pages
    3. pdfplumber — table extraction
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pdf = pdfplumber.open(io.BytesIO(file_bytes))
        pages = []

        for i, page in enumerate(doc):
            plumber_page = pdf.pages[i]
            blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
            page_text = "\n\n".join(b[4].strip() for b in blocks if b[4].strip())

            # Scanned page — run OCR at higher DPI for better accuracy
            if len(page_text.strip()) < 50:
                pix = page.get_pixmap(dpi=200)
                page_text += "\n--- OCR ---\n" + extract_text_from_image(
                    pix.tobytes("png")
                )

            tables = plumber_page.extract_tables()
            if tables:
                table_text = []
                for table in tables:
                    rows = [
                        "| " + " | ".join(str(c) if c else "" for c in row) + " |"
                        for row in table
                        if row
                    ]
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
    """Extracts plain text from .docx by reading its internal XML (no extra dependencies)."""
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


# ── Visual redaction ──────────────────────────────────────────────────────────


def redact_pdf_visual(file_bytes: bytes, entities: list) -> bytes:
    """Black-box redaction directly on PDF using PyMuPDF annotations."""
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
    """Draw black rectangles over detected entities using Tesseract bounding boxes."""
    try:
        image = Image.open(io.BytesIO(file_bytes))
        draw = ImageDraw.Draw(image)
        ocr_data = pytesseract.image_to_data(
            image, lang=OCR_LANG, output_type=pytesseract.Output.DICT
        )
        terms = {
            word.lower()
            for ent in entities
            for word in ent.get("text", "").split()
            if len(word) > 1
        }
        for i, word in enumerate(ocr_data["text"]):
            if word.strip().lower() in terms:
                x, y, w, h = (
                    ocr_data["left"][i],
                    ocr_data["top"][i],
                    ocr_data["width"][i],
                    ocr_data["height"][i],
                )
                draw.rectangle([x, y, x + w, y + h], fill="black")
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()
    except Exception as e:
        print("Image visual redaction error:", e)
        return file_bytes


# ── API Routes ────────────────────────────────────────────────────────────────


@app.post("/api/v1/redact")
@limiter.limit("30/minute")  # 30 text redactions per minute per IP
async def redact_text(
    request: Request,
    payload: RedactRequest,
    redact_style: str = "PLACEHOLDER",
    db: Session = Depends(get_db),
):
    if len(payload.text) > 100_000:
        raise HTTPException(
            status_code=400, detail="Text too large. Maximum 100,000 characters."
        )
    try:
        # Run CPU-heavy redaction in a thread so FastAPI stays responsive
        result = await asyncio.get_event_loop().run_in_executor(
            None, services.process_text_redaction, payload.text, redact_style
        )
        save_log(db, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/redact-file")
@limiter.limit("10/minute")  # File processing is heavier — lower limit
async def redact_file(
    request: Request,
    file: UploadFile = File(...),
    redact_style: str = Form("PLACEHOLDER"),
    return_redacted_document: str = Form("false"),
    db: Session = Depends(get_db),
):
    # Validate file size before reading into memory
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.",
        )

    name = file.filename.lower()

    try:
        if name.endswith(".pdf"):
            text = extract_text_from_pdf(file_bytes)
        elif name.endswith(".docx"):
            text = extract_text_from_docx(file_bytes)
        elif name.endswith(".txt"):
            text = extract_text_from_txt(file_bytes)
        elif name.endswith((".png", ".jpg", ".jpeg", ".tiff")):
            text = extract_text_from_image(file_bytes)
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Use PDF, DOCX, TXT, PNG, JPG, JPEG, or TIFF.",
            )

        if not text.strip():
            raise HTTPException(
                status_code=400, detail="No readable text found in the uploaded file."
            )

        # Run CPU-heavy redaction in a thread so FastAPI event loop stays free
        result = await asyncio.get_event_loop().run_in_executor(
            None, services.process_text_redaction, text, redact_style
        )
        save_log(db, result)

        if return_redacted_document.lower() == "true":
            if name.endswith(".pdf"):
                out_bytes = redact_pdf_visual(file_bytes, result["entities"])
                return StreamingResponse(
                    io.BytesIO(out_bytes),
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f"attachment; filename=redacted_{file.filename}"
                    },
                )
            elif name.endswith((".png", ".jpg", ".jpeg", ".tiff")):
                out_bytes = redact_image_visual(file_bytes, result["entities"])
                return StreamingResponse(
                    io.BytesIO(out_bytes),
                    media_type="image/png",
                    headers={
                        "Content-Disposition": "attachment; filename=redacted_image.png"
                    },
                )
            elif name.endswith(".txt"):
                return StreamingResponse(
                    io.BytesIO(result["secured_text"].encode()),
                    media_type="text/plain",
                    headers={
                        "Content-Disposition": f"attachment; filename=redacted_{file.filename}"
                    },
                )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
