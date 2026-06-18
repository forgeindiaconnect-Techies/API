import sys
import os
import asyncio
import logging
import cloudinary
import cloudinary.uploader

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_cloudinary_variants")

async def test():
    _cloud_name = settings.CLOUDINARY_CLOUD_NAME
    _api_key = settings.CLOUDINARY_API_KEY
    _api_secret = settings.CLOUDINARY_API_SECRET
    
    logger.info(f"Cloud Name: {_cloud_name}")
    logger.info(f"API Key: {_api_key}")
    
    cloudinary.config(
        cloud_name=_cloud_name,
        api_key=_api_key,
        api_secret=_api_secret,
        secure=True
    )
    
    # Test 1: Upload without public_id
    try:
        logger.info("Test 1: Uploading without public_id...")
        def upload_1():
            return cloudinary.uploader.upload(
                b"test file content without public id",
                resource_type="raw"
            )
        res1 = await asyncio.to_thread(upload_1)
        logger.info(f"Test 1 SUCCESS! URL: {res1.get('secure_url')}")
    except Exception as e:
        logger.error(f"Test 1 FAILED: {e}")
        
    # Test 2: Upload with clean public_id (no extensions)
    try:
        logger.info("Test 2: Uploading with clean public_id 'test_clean_id'...")
        def upload_2():
            return cloudinary.uploader.upload(
                b"test file content with clean public id",
                public_id="test_clean_id",
                resource_type="raw"
            )
        res2 = await asyncio.to_thread(upload_2)
        logger.info(f"Test 2 SUCCESS! URL: {res2.get('secure_url')}")
    except Exception as e:
        logger.error(f"Test 2 FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test())
