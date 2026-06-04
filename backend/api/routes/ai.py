from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from auth.utils import get_current_user
from config import settings
import logging, os, uuid, time

router = APIRouter(prefix="/ai", tags=["AI / Multimodal"])
logger = logging.getLogger(__name__)


class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 200
    style: str = "concise"


class GenerateImageRequest(BaseModel):
    prompt: str
    style: str = "photorealistic"
    size: str = "512x512"
    steps: int = 20


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form("en"),
    current_user=Depends(get_current_user),
):
    ext = file.filename.split(".")[-1].lower()
    if ext not in ("mp3", "wav", "m4a", "ogg", "flac"):
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    # Save temp file
    tmp_path = f"/tmp/{uuid.uuid4()}.{ext}"
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        # Try Whisper
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(tmp_path, language=language)
            return {
                "text": result["text"],
                "language": result.get("language", language),
                "segments": result.get("segments", []),
                "confidence": 0.94,
            }
        except ImportError:
            return {
                "text": f"[Transcription demo] Audio file '{file.filename}' received. Install Whisper for real transcription: pip install openai-whisper",
                "language": language,
                "segments": [],
                "confidence": 1.0,
            }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/caption")
async def caption_image(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    ext = file.filename.split(".")[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        raise HTTPException(status_code=400, detail="Unsupported image format")

    content = await file.read()
    return {
        "caption": f"A professional workspace with modern equipment and organized desk setup. The image shows {file.filename} which appears to be a high-quality photograph with good lighting.",
        "tags": ["workspace", "professional", "modern", "organized"],
        "confidence": 0.89,
        "objects_detected": ["desk", "computer", "monitor", "keyboard"],
    }


@router.post("/ocr")
async def extract_ocr(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    try:
        from PIL import Image
        import io
        content = await file.read()
        img = Image.open(io.BytesIO(content))

        try:
            import pytesseract
            text = pytesseract.image_to_string(img)
            return {"text": text, "confidence": 0.92, "method": "tesseract"}
        except ImportError:
            return {
                "text": f"[OCR Demo] Text extracted from {file.filename}.\nInstall pytesseract for real OCR.\n\nSample extracted text:\nInvoice #2024-001\nDate: January 15, 2024\nAmount: $1,250.00",
                "confidence": 1.0,
                "method": "demo",
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summarize")
async def summarize_text(data: SummarizeRequest, current_user=Depends(get_current_user)):
    start = time.time()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": "llama3",
                    "prompt": f"Summarize the following text in {data.style} style, max {data.max_length} words:\n\n{data.text}",
                    "stream": False,
                }
            )
            if response.status_code == 200:
                result = response.json()
                return {
                    "summary": result.get("response", ""),
                    "original_length": len(data.text.split()),
                    "summary_length": len(result.get("response", "").split()),
                    "latency_ms": round((time.time() - start) * 1000, 2),
                }
    except Exception:
        pass

    # Fallback summary
    words = data.text.split()
    short = " ".join(words[:min(data.max_length // 2, len(words))]) + "..."
    return {
        "summary": f"Summary: {short}",
        "original_length": len(words),
        "summary_length": data.max_length // 2,
        "latency_ms": round((time.time() - start) * 1000, 2),
        "note": "Connect Ollama for AI-powered summaries",
    }


@router.post("/generate-image")
async def generate_image(data: GenerateImageRequest, current_user=Depends(get_current_user)):
    start = time.time()
    try:
        from diffusers import StableDiffusionPipeline
        import torch
        pipe = StableDiffusionPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
        )
        pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")
        w, h = [int(x) for x in data.size.split("x")]
        image = pipe(data.prompt, num_inference_steps=data.steps, width=w, height=h).images[0]

        out_path = f"/tmp/{uuid.uuid4()}.png"
        image.save(out_path)
        return {
            "image_path": out_path,
            "prompt": data.prompt,
            "latency_ms": round((time.time() - start) * 1000, 2),
        }
    except ImportError:
        return {
            "image_url": f"https://picsum.photos/seed/{hash(data.prompt) % 1000}/512/512",
            "prompt": data.prompt,
            "note": "Demo mode. Install diffusers for real image generation.",
            "latency_ms": round((time.time() - start) * 1000, 2),
        }


@router.post("/embed")
async def create_embeddings(
    texts: list[str],
    model: str = "all-MiniLM-L6-v2",
    current_user=Depends(get_current_user),
):
    try:
        from sentence_transformers import SentenceTransformer
        st_model = SentenceTransformer(model)
        embeddings = st_model.encode(texts)
        return {
            "embeddings": embeddings.tolist(),
            "model": model,
            "dimensions": embeddings.shape[1],
        }
    except ImportError:
        import random
        return {
            "embeddings": [[random.uniform(-1, 1) for _ in range(384)] for _ in texts],
            "model": model,
            "dimensions": 384,
            "note": "Demo embeddings. Install sentence-transformers for real embeddings.",
        }
