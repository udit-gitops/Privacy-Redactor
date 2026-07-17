import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Database is optional — if not set, telemetry logging is skipped
engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    except Exception as e:
        print(f"⚠️  Database connection failed: {e}. Running in no-telemetry mode.")
        engine = None
        SessionLocal = None
else:
    print("ℹ️  DATABASE_URL not set. Running without telemetry logging.")

Base = declarative_base()

def get_db():
    """Database session generator — returns None if database is not configured."""
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
