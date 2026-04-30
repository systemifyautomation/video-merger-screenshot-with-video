# ── Base image with FFmpeg ────────────────────────────────────────────────────
FROM python:3.12-slim

# Install FFmpeg (and ffprobe) system-wide
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY merger.py .
COPY api.py .

# ── API server ───────────────────────────────────────────────────────────────
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
