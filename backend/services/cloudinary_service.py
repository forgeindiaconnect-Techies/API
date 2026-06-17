import cloudinary
import cloudinary.uploader
import logging
import os
from config import settings

logger = logging.getLogger(__name__)

# Configure Cloudinary — try settings first, then fall back to env vars directly
_cloud_name = settings.CLOUDINARY_CLOUD_NAME or os.environ.get("CLOUDINARY_CLOUD_NAME", "")
_api_key = settings.CLOUDINARY_API_KEY or os.environ.get("CLOUDINARY_API_KEY", "")
_api_secret = settings.CLOUDINARY_API_SECRET or os.environ.get("CLOUDINARY_API_SECRET", "")

if _cloud_name and _api_key and _api_secret:
    try:
        cloudinary.config(
            cloud_name=_cloud_name,
            api_key=_api_key,
            api_secret=_api_secret,
            secure=True
        )
        logger.info("Cloudinary configured successfully.")
    except Exception as e:
        logger.error(f"Cloudinary configuration failed: {e}")
else:
    logger.warning(
        "Cloudinary environment keys are missing. "
        "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET. "
        "File uploads will fall back to local storage."
    )
async def upload_file_to_cloudinary(file_bytes: bytes, file_name: str, resource_type: str = None) -> dict:
    """
    Upload file bytes to Cloudinary.
    Uses 'raw' resource type for tabular/text/pdf files to prevent image processing failure.
    """
    import asyncio
    
    ext = file_name.split(".")[-1].lower()
    if not resource_type:
        resource_type = "image" if ext in ("jpg", "jpeg", "png", "webp", "gif") else "raw"
        logger.info(f"Cloudinary Upload: File extension '{ext}' identified. Auto resource_type='{resource_type}' (required raw for csv/txt/pdf/docx)")
    else:
        logger.info(f"Cloudinary Upload: Using explicit override resource_type='{resource_type}' for file '{file_name}'")
    
    def _upload():
        return cloudinary.uploader.upload(
            file_bytes,
            public_id=file_name,
            resource_type=resource_type
        )
    
    try:
        result = await asyncio.to_thread(_upload)
        logger.info(f"Complete Cloudinary upload response: {result}")
        
        url = result.get("secure_url") or result.get("url")
        public_id = result.get("public_id")
        logger.info(f"Cloudinary upload successful: {public_id}")
        
        return {
            "url": url,
            "secure_url": result.get("secure_url") or url,
            "public_id": public_id,
        }
    except Exception as e:
        logger.error(f"Cloudinary upload failed for '{file_name}': {e}", exc_info=True)
        raise
