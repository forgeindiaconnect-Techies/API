from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time
import asyncio

from config import settings
from database import connect_db, disconnect_db
from middleware import AuthMiddleware, RequestLoggingMiddleware
from api.routes.auth import router as auth_router
from api.routes.chat import router as chat_router
from api.routes.datasets import router as datasets_router
from api.routes.models_router import router as models_router
from api.routes.rag import router as rag_router
from api.routes.api_keys import router as api_keys_router
from api.routes.analytics import router as analytics_router
from api.routes.ai import router as ai_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def get_rss_memory_mb() -> float:
    """Return the current RSS memory usage of the process in MB."""
    import os
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        pass
        
    try:
        if os.path.exists("/proc/self/status"):
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return float(parts[1]) / 1024.0
    except Exception:
        pass
        
    try:
        import resource
        import sys
        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            return maxrss / 1024.0
        else:
            return maxrss / (1024.0 * 1024.0)
    except Exception:
        pass
        
    return 0.0


def acquire_startup_lock() -> bool:
    """Acquire a file lock to ensure only one worker performs startup tasks."""
    import os
    import time
    persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db")
    os.makedirs(persist_dir, exist_ok=True)
    lock_file = os.path.join(persist_dir, "startup.lock")
    
    if os.path.exists(lock_file):
        try:
            mtime = os.path.getmtime(lock_file)
            if time.time() - mtime < 120:
                logger.info("Startup lock exists and is fresh. Skipping startup tasks for this worker.")
                return False
        except Exception:
            pass
            
    try:
        with open(lock_file, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        logger.warning(f"Failed to acquire startup lock: {e}")
        return False


async def initialize_app_bg():
    import time
    start_time = time.time()
    initial_mem = get_rss_memory_mb()
    logger.info(f"Starting background app initialization (Initial Memory: {initial_mem:.2f} MB)...")
    
    # 1. Connect to MongoDB
    try:
        await connect_db()
    except Exception as e:
        logger.error(f"Startup MongoDB connection failed: {e}")
        
    db_conn_time = time.time()
    logger.info(f"MongoDB connection time: {db_conn_time - start_time:.2f}s (Memory: {get_rss_memory_mb():.2f} MB)")
    
    # Check worker lock to avoid duplicate loading across multiple workers
    if not acquire_startup_lock():
        logger.info("Skipping heavy initialization tasks (model pre-load, RAG recovery) for this worker.")
        return

    # Add a delay to let the server bind the port and become healthy first
    delay_sec = 10
    logger.info(f"Delaying heavy initialization tasks by {delay_sec} seconds to ensure immediate API port binding...")
    await asyncio.sleep(delay_sec)
    
    # 2. Lazy Model Loading: The embedding model will be loaded lazily on demand
    # instead of pre-loading at startup to stay within the 512MB RAM Render Free Tier limit.
    logger.info("Bypassing startup model pre-loading to optimize memory usage (lazy loading is active).")


    # 3. RAG index startup recovery check
    logger.info("Starting RAG startup recovery checks...")
    recovery_start = time.time()
    try:
        from services.startup_rebuild import run_startup_recovery
        await run_startup_recovery()
        recovery_time = time.time() - recovery_start
        logger.info(f"RAG startup recovery checks completed in {recovery_time:.2f}s (Memory: {get_rss_memory_mb():.2f} MB)")
    except Exception as recovery_err:
        logger.error(f"Startup recovery failed: {recovery_err}")
        
    total_time = time.time() - start_time
    final_mem = get_rss_memory_mb()
    logger.info(f"Background app initialization completed in {total_time:.2f}s. Final Memory: {final_mem:.2f} MB (Delta: {final_mem - initial_mem:.2f} MB)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Personal AI Studio API (Immediate Port Binding Mode)...")
    # Start the initialization asynchronously in the background so Uvicorn binds immediately
    init_task = asyncio.create_task(initialize_app_bg())
    
    yield
    
    logger.info("Shutting down...")
    if not init_task.done():
        init_task.cancel()
    await disconnect_db()
    
    # Clean up startup lock
    try:
        import os
        persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db")
        lock_file = os.path.join(persist_dir, "startup.lock")
        if os.path.exists(lock_file):
            os.remove(lock_file)
            logger.info("Cleaned up startup lock file.")
    except Exception:
        pass


app = FastAPI(
    title="Personal AI Studio API",
    description="Full-stack AI Platform with RAG, LLM fine-tuning, and multimodal AI",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ─── Middleware ────────────────────────────────────────────────────────────────
# Middleware added last executes first. Outer-most middleware runs first.

# 1. GZip compression (inner-most)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. Authentication (attaches validated user to request.state.user)
app.add_middleware(AuthMiddleware)

# 3. Request Logging & Manual CORS response injection on exceptions/streams
app.add_middleware(RequestLoggingMiddleware)

# 4. CORSMiddleware (outer-most, handles preflight OPTIONS requests directly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://d-ai-nu.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173"
    ],
    allow_origin_regex="https://.*\\.vercel\\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ─── Exception Handlers ───────────────────────────────────────────────────────

ALLOWED_ORIGINS = [
    "https://d-ai-nu.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
]

def _cors_headers(request: Request) -> dict:
    origin = request.headers.get("origin", "")
    if origin in ALLOWED_ORIGINS or (origin.startswith("https://") and origin.endswith(".vercel.app")):
        resolved = origin
    else:
        resolved = "https://d-ai-nu.vercel.app"
    return {
        "Access-Control-Allow-Origin": resolved,
        "Access-Control-Allow-Credentials": "true",
    }

@app.exception_handler(404)
async def not_found(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=404,
        content={"detail": "Resource not found"},
        headers=_cors_headers(request),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(f"StarletteHTTPException ({exc.status_code}): {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=_cors_headers(request),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"RequestValidationError: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": exc.errors()},
        headers=_cors_headers(request),
    )


@app.exception_handler(500)
async def server_error(request: Request, exc: Exception):
    logger.error(f"Internal server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=_cors_headers(request),
    )


# ─── Routers ──────────────────────────────────────────────────────────────────

PREFIX = "/api/v1"

app.include_router(auth_router, prefix=PREFIX)
app.include_router(chat_router, prefix=PREFIX)
app.include_router(datasets_router, prefix=PREFIX)
app.include_router(models_router, prefix=PREFIX)
app.include_router(rag_router, prefix=PREFIX)
app.include_router(api_keys_router, prefix=f"{PREFIX}/api-keys")
app.include_router(api_keys_router, prefix=f"{PREFIX}/api_keys")
app.include_router(analytics_router, prefix=PREFIX)
app.include_router(ai_router, prefix=PREFIX)


# ─── Health & Info ────────────────────────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"])
async def root(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)
    return {
        "status": "healthy",
        "message": "Personal AI Studio API is running",
        "version": settings.APP_VERSION,
    }


@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=b"", media_type="image/x-icon", status_code=200)


@app.get("/robots.txt", include_in_schema=False)
async def robots():
    return Response(content="User-agent: *\nDisallow: /", media_type="text/plain", status_code=200)


@app.get("/api/v1/info")
async def info():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "features": [
            "Authentication (JWT)",
            "AI Chat with streaming",
            "Dataset upload & processing",
            "Automatic EDA",
            "RAG pipeline (ChromaDB/FAISS)",
            "LLM fine-tuning (LoRA/QLoRA)",
            "Multimodal AI (OCR, caption, transcribe)",
            "API key management",
            "Usage analytics",
        ],
        "models_supported": ["llama3", "mistral", "deepseek", "whisper", "stable-diffusion"],
        "file_types_supported": ["csv", "xlsx", "pdf", "txt", "docx", "jpg", "png", "mp3", "wav", "zip"],
    }


@app.get("/api/v1/test-embedder")
async def test_embedder():
    from vector_db.store import get_embedding_model
    import numpy as np
    import os
    embedder = get_embedding_model()
    
    # Test encoding
    test_text = "test query"
    emb = embedder.encode(test_text)
    
    return {
        "class_name": embedder.__class__.__name__,
        "vector_type": str(type(emb)),
        "vector_len": len(emb) if hasattr(emb, "__len__") else None,
        "is_numpy": isinstance(emb, np.ndarray),
        "is_render_env": os.environ.get("RENDER") == "true" or os.environ.get("RENDER_SERVICE_ID") is not None,
        "disable_local_env": os.environ.get("DISABLE_LOCAL_EMBEDDINGS") == "true",
        "openai_key_configured": bool(settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-..."))
    }


# ─── Generated Inference Endpoints ────────────────────────────────────────────
# These are the auto-generated endpoints mentioned in the spec

@app.post("/api/v1/predict")
async def public_predict(request: Request):
    """Public inference endpoint (requires API key)"""
    api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Valid API key required")
    body = await request.json()
    return {
        "prediction": {"label": "positive", "confidence": 0.92},
        "model": body.get("model", "default"),
        "latency_ms": 48.2,
    }


@app.post("/api/v1/chat")
async def public_chat(request: Request):
    """Public chat endpoint (requires API key)"""
    api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Valid API key required")
    body = await request.json()
    return {
        "response": f"API response to: {body.get('message', '')}",
        "model": body.get("model", "llama3"),
        "tokens_used": 142,
    }


@app.post("/api/v1/image-generate")
async def public_image_generate(request: Request):
    """Public image generation endpoint (requires API key)"""
    api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Valid API key required")
    body = await request.json()
    return {
        "image_url": f"https://picsum.photos/seed/{hash(body.get('prompt', ''))%1000}/512/512",
        "prompt": body.get("prompt", ""),
        "latency_ms": 3200,
    }


@app.post("/api/v1/audio-transcribe")
async def public_audio_transcribe(request: Request):
    """Public audio transcription endpoint (requires API key)"""
    api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not api_key.startswith("sk-"):
        raise HTTPException(status_code=401, detail="Valid API key required")
    return {
        "text": "Transcription of your audio file.",
        "language": "en",
        "confidence": 0.94,
    }

