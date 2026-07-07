from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database import Base

class RedactionLog(Base):
    __tablename__ = "redaction_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    input_characters = Column(Integer)
    entities_redacted = Column(Integer)