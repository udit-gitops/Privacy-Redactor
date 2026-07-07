# Automated Contextual Privacy & Compliance Redactor API

An enterprise-grade, API-first security microservice designed to mitigate data compliance risks (GDPR/HIPAA) by contextually redacting Personally Identifiable Information (PII) from corporate data streams before external ingestion.

## 🚀 Architecture & Technical Highlights
* **Framework:** **FastAPI** utilizing asynchronous routing hooks for high-performance JSON throughput.
* **Core Engine:** **Microsoft Presidio** for structural Named Entity Recognition (NER) pipeline management to instantly mask standard entities (Emails, Phones, IPs).
* **AI Layer:** Hybrid contextual tie-breaker logic powered by **Groq Cloud (Llama 3)** to dynamically resolve token ambiguity (e.g., distinguishing between 'Apple' the common fruit vs. 'Apple' the private corporate leak) with zero-latency overhead.
* **Database Logs:** **PostgreSQL via SQLAlchemy ORM** to execute transactional metadata metric logging without storing plain-text user payloads.

## 🛠️ Project Directory Layout
```text
privacy-redactor-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI Gateway Routes
│   ├── database.py      # SQLAlchemy & Engine configurations
│   ├── models.py        # Database Logging Schemas
│   └── services.py      # Core Presidio & Groq Integration Pipeline
│
├── .env                 # Local Environment Flags (Git Ignored)
├── .gitignore           # File exclusion layout
└── requirements.txt     # System Core Dependencies