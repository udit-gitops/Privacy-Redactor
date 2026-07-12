# 1. Base Python image optimized for production
FROM python:3.11-slim

# 2. Set system working directory inside container
WORKDIR /code

# 3. Copy only dependency list first (for layer caching optimization)
COPY ./requirements.txt /code/requirements.txt

# 4. Install system dependencies and python packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /code/requirements.txt

# 5. Download the heavy Microsoft Presidio SpaCy language model explicitly 
RUN python -m spacy download en_core_web_lg

# 6. Copy the rest of the application code into the container
COPY ./app /code/app

# 7. Expose port 8000 for network communication
EXPOSE 8000

# 8. Command to run the FastAPI app inside container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]