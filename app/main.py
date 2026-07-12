import io
import os
import zipfile
import xml.etree.ElementTree as ET
import pypdf
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image, ImageDraw
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import engine, get_db
from app import models, services

# Initialize database tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Privacy & Compliance Redactor API")

# Crucial Security & CORS Pre-flight Integration Handler
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://10.140.255.63:3000"],
    allow_credentials=True,
    allow_methods=["*"],  # Allows OPTIONS, POST, GET, etc.
    allow_headers=["*"],  # Allows custom metadata headers
)

# Request schema matching the frontend payload
class RedactRequest(BaseModel):
    text: str

# Configurable Tesseract path (if user needs to point to a specific directory on Windows)
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
else:
    # If on Windows, check default common Program Files path
    default_win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(default_win_path):
        pytesseract.pytesseract.tesseract_cmd = default_win_path

def extract_text_from_image(file_bytes: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image)
        return text
    except pytesseract.TesseractNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Tesseract OCR engine not found. Please install Tesseract-OCR on your machine or configure TESSERACT_CMD in your environment."
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR failed to parse image: {str(e)}")

def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        # Load PDF using PyMuPDF (fitz)
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        
        # Load PDF using pdfplumber (for table extraction)
        pdf_plumber = pdfplumber.open(io.BytesIO(file_bytes))
        
        extracted_text = []
        
        for page_idx in range(len(doc)):
            page_fitz = doc[page_idx]
            page_plumber = pdf_plumber.pages[page_idx]
            
            # 1. Extract tables using pdfplumber
            tables = page_plumber.extract_tables()
            table_texts = []
            for table in tables:
                if not table:
                    continue
                # Format table as Markdown-like string
                md_table = []
                for row in table:
                    # Clean None values
                    row_cleaned = [str(cell).strip() if cell is not None else "" for cell in row]
                    md_table.append("| " + " | ".join(row_cleaned) + " |")
                table_texts.append("\n".join(md_table))
            
            # 2. Extract column-aware text block layout using PyMuPDF (fitz)
            blocks = page_fitz.get_text("blocks")
            page_text = ""
            for b in sorted(blocks, key=lambda block: (block[1], block[0])):
                block_text = b[4].strip()
                if block_text:
                    page_text += block_text + "\n\n"
            
            # 3. OCR Fallback for scanned PDF pages
            # If standard text content is negligible (< 50 chars), render page to image and run OCR
            if len(page_text.strip()) < 50:
                pix = page_fitz.get_pixmap(dpi=150)
                img_data = pix.tobytes("png")
                ocr_text = extract_text_from_image(img_data)
                page_text += "\n--- Scanned Page OCR Extracted Text ---\n" + ocr_text + "\n"
            
            # 4. Append tables at the end of the page text if any were found
            if table_texts:
                page_text += "\n--- Extracted Table(s) ---\n" + "\n\n".join(table_texts) + "\n"
                
            extracted_text.append(page_text)
            
        doc.close()
        pdf_plumber.close()
        return "\n--- Page Break ---\n".join(extracted_text)
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse layout-aware PDF: {str(e)}")

def extract_text_from_docx(file_bytes: bytes) -> str:
    try:
        docx_file = io.BytesIO(file_bytes)
        with zipfile.ZipFile(docx_file) as docx:
            tree = ET.parse(docx.open("word/document.xml"))
            root = tree.getroot()
            text_runs = []
            for paragraph in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                p_text = []
                for run in paragraph.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                    if run.text:
                        p_text.append(run.text)
                text_runs.append("".join(p_text))
            return "\n".join(text_runs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse Word Document (.docx): {str(e)}")

def extract_text_from_txt(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return file_bytes.decode("latin-1")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to decode text file: {str(e)}")

def redact_pdf_visual(file_bytes: bytes, entities: list) -> bytes:
    try:
        # Load PDF using PyMuPDF (fitz)
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            for ent in entities:
                ent_text = ent.get("text", "").strip()
                if not ent_text or len(ent_text) < 2:
                    continue
                # Search for occurrences on the page
                rects = page.search_for(ent_text)
                for rect in rects:
                    # Add solid black redaction annotation
                    page.add_redact_annot(rect, fill=(0,0,0))
            page.apply_redactions()
        out_bytes = doc.write()
        doc.close()
        return out_bytes
    except Exception as e:
        print("Visual PDF redaction failed:", e)
        return file_bytes

def redact_image_visual(file_bytes: bytes, entities: list) -> bytes:
    try:
        image = Image.open(io.BytesIO(file_bytes))
        draw = ImageDraw.Draw(image)
        
        # Get OCR bounding box data
        ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        
        # Collect entity text terms
        terms = set()
        for ent in entities:
            ent_text = ent.get("text", "").strip()
            if ent_text:
                # Add individual words to redact to match Tesseract output
                for w in ent_text.split():
                    if len(w) > 1:
                        terms.add(w.lower())
                        
        n_boxes = len(ocr_data['text'])
        for i in range(n_boxes):
            word_text = ocr_data['text'][i].strip()
            if not word_text:
                continue
                
            # If word is in our target terms list, redact it
            if word_text.lower() in terms:
                x = ocr_data['left'][i]
                y = ocr_data['top'][i]
                w = ocr_data['width'][i]
                h = ocr_data['height'][i]
                draw.rectangle([x, y, x + w, y + h], fill="black")
                
        out_io = io.BytesIO()
        image.save(out_io, format="PNG")
        return out_io.getvalue()
    except Exception as e:
        print("Visual Image redaction failed:", e)
        return file_bytes

@app.post("/api/v1/redact")
async def redact_text(payload: RedactRequest, redact_style: str = "PLACEHOLDER", db: Session = Depends(get_db)):
    try:
        # Routes the text through Presidio and Groq pipeline
        result = services.process_text_redaction(payload.text, redact_style)
        
        # Save logging telemetry to the database
        db_log = models.RedactionLog(
            input_characters=result["metrics"]["characters_processed"],
            entities_redacted=result["metrics"]["identities_masked"]
        )
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        
        return result
    except Exception as e:
        # Prevent leaking database credentials or system paths in exception dumps
        print(f"[SECURITY] Exception during redact_text: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error occurred during text sanitization.")

@app.post("/api/v1/redact-file")
async def redact_file(
    file: UploadFile = File(...),
    redact_style: str = "PLACEHOLDER",
    return_redacted_document: bool = False,
    db: Session = Depends(get_db)
):
    try:
        # Prevent Denial of Service (DoS) by limiting file size to 50MB
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
        file_bytes = await file.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum allowed size is 50 MB.")
            
        filename = file.filename.lower()
        
        if filename.endswith(".pdf"):
            text = extract_text_from_pdf(file_bytes)
        elif filename.endswith(".docx"):
            text = extract_text_from_docx(file_bytes)
        elif filename.endswith(".txt"):
            text = extract_text_from_txt(file_bytes)
        elif filename.endswith((".png", ".jpg", ".jpeg", ".tiff")):
            text = extract_text_from_image(file_bytes)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a PDF, DOCX, TXT, PNG, JPG, JPEG, or TIFF file.")
            
        if not text.strip():
            raise HTTPException(status_code=400, detail="The uploaded file contains no readable text.")
            
        # Routes the text through Presidio and Groq pipeline
        result = services.process_text_redaction(text, redact_style)
        
        # Save logging telemetry to the database
        db_log = models.RedactionLog(
            input_characters=result["metrics"]["characters_processed"],
            entities_redacted=result["metrics"]["identities_masked"]
        )
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        
        if return_redacted_document:
            if filename.endswith(".pdf"):
                redacted_pdf_bytes = redact_pdf_visual(file_bytes, result["entities"])
                return StreamingResponse(
                    io.BytesIO(redacted_pdf_bytes),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=redacted_{file.filename}"}
                )
            elif filename.endswith((".png", ".jpg", ".jpeg", ".tiff")):
                redacted_img_bytes = redact_image_visual(file_bytes, result["entities"])
                return StreamingResponse(
                    io.BytesIO(redacted_img_bytes),
                    media_type="image/png",
                    headers={"Content-Disposition": f"attachment; filename=redacted_image.png"}
                )
            elif filename.endswith(".txt"):
                return StreamingResponse(
                    io.BytesIO(result["secured_text"].encode("utf-8")),
                    media_type="text/plain",
                    headers={"Content-Disposition": f"attachment; filename=redacted_{file.filename}"}
                )
            
        return result
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[SECURITY] Exception during redact_file: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error occurred during file sanitization.")