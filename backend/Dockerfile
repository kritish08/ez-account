# ============================================================
# EZ Account — Backend Dockerfile
# FastAPI + Uvicorn | Python 3.11-slim
# ============================================================

FROM python:3.11-slim-bookworm

# System dependencies (WeasyPrint needs cairo/pango for PDF generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libcairo2 \
    libglib2.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend code (except what's in .dockerignore)
COPY . .

# Ensure no local __pycache__ or existing uploads in the image
RUN find . -type d -name "__pycache__" -exec rm -rf {} + \
    && rm -rf uploads/ \
    && mkdir -p /app/uploads

EXPOSE 8001

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
