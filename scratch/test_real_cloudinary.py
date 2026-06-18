import sys
import os
import asyncio
import logging

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from config import settings
from services.cloudinary_service import upload_file_to_cloudinary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_real_cloudinary")

async def test():
    logger.info("Starting real Cloudinary upload test...")
    logger.info(f"Cloud Name: {settings.CLOUDINARY_CLOUD_NAME}")
    logger.info(f"API Key: {settings.CLOUDINARY_API_KEY}")
    
    test_content = b"This is a test upload to verify Cloudinary credentials."
    test_name = "test_upload_from_script.txt"
    
    try:
        res = await upload_file_to_cloudinary(test_content, test_name)
        logger.info("Upload successful!")
        logger.info(f"Result URL: {res.get('url')}")
        logger.info(f"Result Public ID: {res.get('public_id')}")
    except Exception as e:
        logger.error(f"Cloudinary upload failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test())
