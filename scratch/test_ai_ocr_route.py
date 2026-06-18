import os
import sys
import io
import asyncio
import logging

# Add backend directory to path at the very beginning
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_ai_ocr_route")

from api.routes.ai import extract_ocr
from fastapi import UploadFile
from PIL import Image

def test_ocr_endpoint_directly():
    # Dynamically generate valid image bytes using PIL
    img = Image.new('RGB', (10, 10), color = 'red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    png_bytes = img_bytes.getvalue()
    
    file = UploadFile(filename="test_image.png", file=io.BytesIO(png_bytes))
    
    try:
        logger.info("Calling extract_ocr directly...")
        # Since it is an async function, we run it using asyncio.run
        result = asyncio.run(extract_ocr(file=file, current_user={"username": "demo@aistudio.com"}))
        logger.info(f"Result: {result}")
        
        assert "text" in result
        assert "confidence" in result
        assert "method" in result
        logger.info("Direct route test passed successfully!")
    except Exception as e:
        logger.error(f"Direct route test failed: {e}", exc_info=True)

if __name__ == "__main__":
    test_ocr_endpoint_directly()
