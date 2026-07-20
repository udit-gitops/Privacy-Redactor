# Privacy Redact

> **Protect sensitive information before it reaches AI.**

Privacy Redact is a full-stack application that automatically detects and redacts Personally Identifiable Information (PII) from text, PDFs, Word documents, and images before they are shared with Large Language Models (LLMs).

It combines Microsoft's Presidio with custom-built Indian recognizers and contextual AI verification to identify sensitive information while reducing false positives.

🌐 **Live Demo:** https://spectacular-commitment-production-123b.up.railway.app

---

## Why I Built This

The idea for Privacy Redact came during a journey back to college while I was thinking about how quickly companies are adopting AI tools in their everyday workflows.

As more organizations use LLMs for summarization, analysis, and automation, accidentally sharing customer information or confidential documents becomes a real privacy concern.

I wanted to build a practical solution that automatically detects and redacts sensitive information before it reaches an AI model.

What started as a simple backend API eventually grew into my biggest personal project so far and introduced me to backend engineering, AI infrastructure, and system design.

---

## Features

- Detects common PII such as names, email addresses, phone numbers, financial information and organisations.
- Supports Indian-specific entities including Aadhaar, PAN, Passport, IFSC, UPI IDs, GSTIN, vehicle registration numbers and more.
- Works with **Text, PDF, DOCX, Images and Scanned Documents**.
- OCR support using Tesseract for scanned files.
- Generates downloadable PDFs with sensitive information physically redacted.
- Supports multiple redaction styles.
- Audit logging with PostgreSQL.
- Dockerized for deployment.
- Fully deployed on Railway.

---

## Supported Entities

### Indian PII

| Entity | Example |
|---------|---------|
| Aadhaar | `1234 5678 9012` |
| PAN | `ABCDE1234F` |
| Passport | `P1234567` |
| Driving License | `RJ14 20230012345` |
| Vehicle Registration | `RJ20CA1234` |
| IFSC Code | `SBIN0001234` |
| UPI ID | `udit@oksbi` |
| GSTIN | `27ABCDE1234F1Z5` |
| Voter ID | `ABC1234567` |
| Bank Account | `1234567890123456` |
| Credit Card | `4111 1111 1111 1111` |
| PIN Code | `324005` |

### Standard PII

- Names
- Email Addresses
- Phone Numbers
- Dates
- Locations
- Organisations
- IP Addresses
- Money Amounts
- Employee IDs
- Student IDs

---

## Screenshots

### Dashboard

<img width="1535" height="692" alt="image" src="https://github.com/user-attachments/assets/d954743d-a99d-4fc1-aa5d-abdb0fa16ac1" />


### Text Redaction

<img width="1024" height="601" alt="image" src="https://github.com/user-attachments/assets/2584a026-8ab4-4794-90db-7c3815c33e9b" />


### PDF Redaction

<img width="1002" height="627" alt="image" src="https://github.com/user-attachments/assets/268a3ab3-5d7b-49c5-9e4c-f4c3fc7a6c11" />


---

## Architecture

```
                Input
(Text / PDF / DOCX / Image)
                     │
                     ▼
          Microsoft Presidio
       (Rule-based Detection)
                     │
                     ▼
      Custom Indian Recognizers
                     │
                     ▼
       Groq (Llama 3.1)
(Contextual Verification Layer)
                     │
                     ▼
        Conflict Resolution
                     │
                     ▼
     Redacted Output / PDF
```

Privacy Redact follows a hybrid detection pipeline.

Rule-based detection handles structured entities quickly, while the AI verification layer helps resolve ambiguous cases where context matters. This combination improves accuracy while keeping the API fast and reliable.

## Tech Stack

| Layer | Technology |
|--------|------------|
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.11 |
| PII Detection | Microsoft Presidio + Custom Indian Recognizers |
| AI Context Layer | Groq (Llama 3.1 8B Instant) |
| PDF Processing | PyMuPDF, pdfplumber |
| OCR | Tesseract OCR (English + Hindi) |
| Database | PostgreSQL + SQLAlchemy |
| Containerization | Docker |
| Deployment | Railway |

---

## Local Setup

### Prerequisites

Before getting started, make sure you have:

- Python 3.11+
- Node.js 18+
- Git
- Docker (optional)
- Tesseract OCR *(only required for OCR support)*
- A free Groq API Key

---

### Clone the Repository

```bash
git clone https://github.com/udit-gitops/Privacy-Redactor.git
cd Privacy-Redactor
```

---

## Backend Setup

### Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it

Windows

```bash
.venv\Scripts\activate
```

macOS / Linux

```bash
source .venv/bin/activate
```

---

### Install Dependencies

```bash
pip install -r requirements.txt
```

---

### Download the spaCy Model

```bash
python -m spacy download en_core_web_lg
```

---

### Configure Environment Variables

Create a `.env` file in the project root.

```env
GROQ_API_KEY=your_api_key_here

DATABASE_URL=your_postgres_database_url

ALLOWED_ORIGINS=http://localhost:3000

MAX_FILE_SIZE_MB=10

MIN_CONFIDENCE_THRESHOLD=0.6

TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

> `DATABASE_URL` is optional during local development. The application automatically falls back to SQLite if it isn't provided.

---

### Start the Backend

```bash
uvicorn app.main:app --reload
```

Backend

```
http://127.0.0.1:8000
```

Swagger Documentation

```
http://127.0.0.1:8000/docs
```

---

## Frontend Setup

```bash
cd privacy_redactor_frontend
```

Install packages

```bash
npm install
```

Create a `.env.local`

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Start the frontend

```bash
npm run dev
```

Application

```
http://localhost:3000
```

---

## Docker

The project also supports Docker for a consistent development and deployment environment.

Build the image

```bash
docker build -t privacy-redact .
```

Run the container

```bash
docker run -p 8000:8000 privacy-redact
```

---

## Deployment

The application is currently deployed on **Railway**.

Live Demo

https://spectacular-commitment-production-123b.up.railway.app

The deployed version includes:

- FastAPI Backend
- Next.js Frontend
- PostgreSQL Database
- Docker Container
- Railway Deployment
  ## API Reference

### `POST /api/v1/redact`

Redacts sensitive information from plain text.

**Request**

```json
{
  "text": "Udit earns ₹85,000 at Apple Inc."
}
```

**Response**

```json
{
  "secured_text": "<PERSON> earns <MONEY> at Apple Inc.",
  "entities": [
    {
      "text": "Udit",
      "type": "PERSON",
      "score": 0.95
    }
  ]
}
```

Supports multiple redaction styles:

- PLACEHOLDER *(Default)*
- REDACTED
- MASK
- HIDDEN

---

### `POST /api/v1/redact-file`

Upload a document for redaction.

Supported formats:

- PDF
- DOCX
- TXT
- PNG
- JPG
- JPEG
- TIFF

Optional parameters:

- `redact_style`
- `return_redacted_document`

---

### `GET /health`

Simple health check endpoint.

```json
{
  "status": "ok",
  "ocr_lang": "hin+eng"
}
```

---

## Project Structure

```
Privacy-Redactor
│
├── app/
│   ├── main.py
│   ├── services.py
│   ├── models.py
│   ├── database.py
│   └── recognizers/
│
├── privacy_redactor_frontend/
│
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Future Improvements

Although the project is fully functional, there are several features I'd love to add in future versions.

- Authentication & User Accounts
- API Key Management
- Batch File Processing
- Dashboard with Redaction History
- Analytics & Usage Metrics
- Additional OCR Language Support
- Kubernetes Deployment
- CI/CD Pipeline

---

## Challenges & Learnings

This project started as a simple backend API.

Somewhere along the way, it became the biggest personal project I've built so far.

As new features were added, the project quickly grew in size. More libraries meant more configurations, more debugging, and more deployment issues to solve.

One challenge I particularly enjoyed working on was extending Microsoft Presidio with custom recognizers for Indian documents. Existing recognizers handled many standard entities well, but I wanted the application to work better for Indian use cases like Aadhaar, PAN, IFSC, UPI IDs and vehicle registration numbers.

Looking back, the biggest takeaway wasn't learning another framework—it was gaining the confidence to work with larger codebases, debug unfamiliar problems, and keep building until everything finally worked.

---

## Contributing

Contributions, feature suggestions, and bug reports are always welcome.

If you find an issue or have an idea to improve the project, feel free to open an Issue or submit a Pull Request.
Improvements are still on the line, it's not perfect and I'll continue working on this.

---

## Connect With Me

**Udit Navariya**

- LinkedIn: https://www.linkedin.com/in/udit-navariya/

If you found this project useful or interesting, consider giving it a ⭐ on GitHub.


---

## License

Not licensed yet.
