FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip ffmpeg tesseract-ocr git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# Official bgutil PO-token provider, matching the yt-dlp plugin major/minor.
RUN git clone --depth 1 --branch 2.0.0 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil && \
    cd /opt/bgutil/server && npm ci --omit=dev --no-audit --no-fund && \
    npm ci --no-audit --no-fund && npx tsc

COPY . .

ENV PYTHONUNBUFFERED=1
ENV POT_SERVER_URL=http://127.0.0.1:4416

# Start the PO-token provider locally, then the FastAPI app.
CMD ["sh","-c","node /opt/bgutil/server/build/main.js --host 127.0.0.1 & exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000}"]
