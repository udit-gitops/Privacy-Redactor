# 1. Base image
FROM python:3.11-slim

# 2. Install system dependencies including Tesseract with Hindi + English language packs
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 3. Set working directory
WORKDIR /code

# 4. Copy and install Python dependencies first (layer caching)
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /code/requirements.txt

# 5. Download spaCy model
RUN python -m spacy download en_core_web_lg

# 6. Copy application code
COPY ./app /code/app

# 7. Expose port
EXPOSE 8000

# 8. Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]