# Telegram Video Downloader Bot - Dockerfile
FROM python:3.11-slim

# Install ffmpeg and dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 botuser

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=botuser:botuser . .

# Create directories for downloads and cookies
RUN mkdir -p /app/downloads && chown -R botuser:botuser /app/downloads

USER botuser

# Default command
CMD ["python", "bot.py"]