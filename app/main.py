from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import engine, get_db
from app import models, services

# Safe dynamic schema updates
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Privacy & Compliance Redactor API")

# Define request structure using Pydantic (Latest market practice)
class RedactRequest(BaseModel):
    text: str

@app.get("/")
def health_check():
    return {"status": "healthy", "service": "Privacy Redactor Engine"}

@app.post("/api/v1/redact")
def redact_text_endpoint(payload: RedactRequest, db: Session = Depends(get_db)):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
        
    # Execute the Core AI and Logic Pipeline
    result = services.process_text_redaction(payload.text)
    
    # Write to database logs using SQLAlchemy pure python structure
    db_log = models.RedactionLog(
        input_characters=result["character_count"],
        entities_redacted=result["entities_found"]
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    
    return {
        "secured_text": result["redacted_text"],
        "metrics": {
            "characters_processed": result["character_count"],
            "identities_masked": result["entities_found"],
            "log_reference_id": db_log.id
        }
    }