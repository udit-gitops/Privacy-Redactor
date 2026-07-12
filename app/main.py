import io
import zipfile
import xml.etree.ElementTree as ET
import pypdf
import fitz  # PyMuPDF
import pdfplumber
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
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
            # A block has structure: (x0, y0, x1, y1, "text", block_no, block_type)
            # We sort blocks top-to-bottom, then left-to-right to preserve reading flow
            blocks = page_fitz.get_text("blocks")
            page_text = ""
            for b in sorted(blocks, key=lambda block: (block[1], block[0])):
                block_text = b[4].strip()
                if block_text:
                    page_text += block_text + "\n\n"
            
            # 3. Append tables at the end of the page text if any were found
            if table_texts:
                page_text += "\n--- Extracted Table(s) ---\n" + "\n\n".join(table_texts) + "\n"
                
            extracted_text.append(page_text)
            
        doc.close()
        pdf_plumber.close()
        return "\n--- Page Break ---\n".join(extracted_text)
        
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

@app.post("/api/v1/redact")
async def redact_text(payload: RedactRequest, db: Session = Depends(get_db)):
    try:
        # Routes the text through Presidio and Groq pipeline
        result = services.process_text_redaction(payload.text)
        
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/redact-file")
async def redact_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        file_bytes = await file.read()
        filename = file.filename.lower()
        
        if filename.endswith(".pdf"):
            text = extract_text_from_pdf(file_bytes)
        elif filename.endswith(".docx"):
            text = extract_text_from_docx(file_bytes)
        elif filename.endswith(".txt"):
            text = extract_text_from_txt(file_bytes)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a PDF, DOCX, or TXT file.")
            
        if not text.strip():
            raise HTTPException(status_code=400, detail="The uploaded file contains no readable text.")
            
        # Routes the text through Presidio and Groq pipeline
        result = services.process_text_redaction(text)
        
        # Save logging telemetry to the database
        db_log = models.RedactionLog(
            input_characters=result["metrics"]["characters_processed"],
            entities_redacted=result["metrics"]["identities_masked"]
        )
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        
        return result
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))