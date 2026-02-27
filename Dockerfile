# ============================================================
# vocal-agent-fr-live — Dockerfile
# ============================================================
# Multi-stage build for the voice agent service
# ============================================================

FROM python:3.12-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies (pip packages)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install MeloTTS from GitHub (PyPI package is broken)
RUN pip install --no-cache-dir git+https://github.com/myshell-ai/MeloTTS.git && \
    python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng', quiet=True)" || true

# Install Chatterbox TTS from GitHub
RUN pip install --no-cache-dir git+https://github.com/resemble-ai/chatterbox.git || \
    echo "WARNING: Chatterbox install failed — fallback TTS unavailable"

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data/mem0 /app/data/models

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOST=0.0.0.0
ENV PORT=8765

# Expose port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

# Run the application
CMD ["python", "main.py"]
