# ==============================================================================
# AutoPost AI Studio - Production Dockerfile
# ==============================================================================
FROM python:3.11-slim-bookworm

# Avoid prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies: FFmpeg, fontconfig, and open-source fonts for subtitles
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fontconfig \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-freefont-ttf \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for caching layers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and configuration
COPY config/ ./config/
COPY src/ ./src/
COPY run.py .
# COPY .env.example .

# Create output directory for generated videos
RUN mkdir -p /app/output

# Expose web dashboard port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/status || exit 1

# Start the application
CMD ["python", "run.py"]
