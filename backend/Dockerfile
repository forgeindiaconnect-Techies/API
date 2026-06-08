FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    ffmpeg \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download SentenceTransformer model to cache it inside the Docker image (lightweight download to prevent builder OOM)
ENV HF_HOME=/root/.cache/huggingface
# Force ONNX Runtime to execute on CPU and suppress GPU-seeking warnings
ENV ORT_LOGGING_LEVEL=3
ENV ONNXRUNTIME_PROVIDERS=CPUExecutionProvider
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='sentence-transformers/all-MiniLM-L6-v2')"

COPY . .

# Create dirs
RUN mkdir -p uploads chroma_db models_store

EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 120
