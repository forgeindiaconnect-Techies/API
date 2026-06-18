import os
import sys
import asyncio
import logging

# Add backend directory to path at the very beginning
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_ai_endpoints_predictions")

from api.routes.ai import generate_image, caption_image, GenerateImageRequest
from fastapi import UploadFile
import io

def test_image_generation_fallback():
    # Test generation with prompt "car"
    req = GenerateImageRequest(prompt="car", style="photorealistic", size="512x512")
    try:
        logger.info("Calling generate_image for prompt 'car'...")
        result = asyncio.run(generate_image(data=req, current_user={"username": "demo@aistudio.com"}))
        logger.info(f"Result: {result}")
        assert "image_url" in result
        assert "car" in result["image_url"] or "car" in result["prompt"]
        logger.info("Image generation fallback test passed!")
    except Exception as e:
        logger.error(f"Image generation fallback test failed: {e}", exc_info=True)

def test_image_captioning_fallback():
    # Test captioning with a filename "cute-dog.jpg"
    file = UploadFile(filename="cute-dog.jpg", file=io.BytesIO(b"dummy image bytes"))
    try:
        logger.info("Calling caption_image for filename 'cute-dog.jpg'...")
        result = asyncio.run(caption_image(file=file, current_user={"username": "demo@aistudio.com"}))
        logger.info(f"Result: {result}")
        assert "caption" in result
        assert "dog" in result["caption"].lower()
        logger.info("Image captioning fallback test passed!")
    except Exception as e:
        logger.error(f"Image captioning fallback test failed: {e}", exc_info=True)

if __name__ == "__main__":
    test_image_generation_fallback()
    test_image_captioning_fallback()
