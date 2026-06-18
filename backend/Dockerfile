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
RUN pip install --no-cache-dir --default-timeout=100 --retries 5 -r requirements.txt

# Pre-download SentenceTransformer model to cache it inside the Docker image (lightweight download to prevent builder OOM)
ENV HF_HOME=/root/.cache/huggingface
# Force ONNX Runtime to execute on CPU and suppress GPU-seeking warnings
ENV ORT_LOGGING_LEVEL=3
ENV ONNXRUNTIME_PROVIDERS=CPUExecutionProvider
# Ensure stdout/stderr streams are sent straight to terminal without buffering
ENV PYTHONUNBUFFERED=1

COPY . .

# Create dirs
RUN mkdir -p uploads chroma_db models_store

EXPOSE 10000

CMD ["python", "main.py"]
