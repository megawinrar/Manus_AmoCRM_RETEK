# ═══════════════════════════════════════════════════════════════════
# RETEK amoCRM Microservice — Production Dockerfile
# ═══════════════════════════════════════════════════════════════════
FROM python:3.11-slim

# System dependencies (pdftotext, tesseract for OCR fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-rus \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user (non-root)
RUN useradd -m -s /bin/bash appuser

# Working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
COPY deploy/requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements.txt -r requirements-deploy.txt

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY docs/ ./docs/

# Create data directories
RUN mkdir -p /app/data /app/logs /app/backups && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Entry point
CMD ["uvicorn", "src.microservice.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
