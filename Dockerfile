# PartFinder — Docker image for Render
# Playwright + Tesseract need system libraries, so we use the official
# Playwright Python image (Chromium + all deps preinstalled) and add Tesseract.

FROM mcr.microsoft.com/playwright/python:v1.41.2-jammy

# System OCR engine for pytesseract
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Make sure the Chromium browser binary is present for this Playwright version
RUN playwright install chromium

# Copy the app (backend + frontend)
COPY backend ./backend
COPY frontend ./frontend

ENV PARTFINDER_HEADLESS=1 \
    PF_STATE_DIR=/tmp/pf_sessions \
    PORT=8000

WORKDIR /app/backend
EXPOSE 8000

# Render provides $PORT; serve_all.py reads it.
CMD ["python", "serve_all.py"]
