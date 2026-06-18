import os
import tempfile
import boto3
import logging
from config import settings

logger = logging.getLogger(__name__)

def get_s3_client():
    if not (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY and settings.AWS_S3_BUCKET):
        logger.warning("AWS credentials or S3 bucket not configured.")
        return None
    try:
        return boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME
        )
    except Exception as e:
        logger.error(f"Failed to initialize boto3 S3 client: {e}")
        return None

async def upload_file_to_s3(file_bytes: bytes, filename: str, content_type: str = "application/octet-stream") -> dict:
    """Upload raw file bytes to AWS S3 and return secure url and key."""
    import asyncio
    
    client = get_s3_client()
    if client is None:
        raise Exception("AWS S3 storage is not configured or failed to initialize.")
        
    bucket = settings.AWS_S3_BUCKET
    import uuid
    # Create a unique key for the S3 object
    unique_id = str(uuid.uuid4())
    ext = filename.split(".")[-1].lower() if "." in filename else "bin"
    key = f"datasets/{unique_id}.{ext}"
    
    def _upload():
        logger.info(f"Uploading file '{filename}' to S3 bucket '{bucket}' as key '{key}'...")
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=file_bytes,
            ContentType=content_type
        )
        url = f"https://{bucket}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/{key}"
        return {
            "s3_url": url,
            "secure_url": url,
            "s3_key": key
        }
        
    return await asyncio.to_thread(_upload)

async def download_file_from_s3(s3_key: str, suffix: str = ".txt") -> str:
    """Download a file from AWS S3 to a temporary file path."""
    import asyncio
    
    client = get_s3_client()
    if client is None:
        raise Exception("AWS S3 storage is not configured or failed to initialize.")
        
    bucket = settings.AWS_S3_BUCKET
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = temp_file.name
    temp_file.close()
    
    def _download():
        logger.info(f"Downloading key '{s3_key}' from S3 bucket '{bucket}' to '{temp_path}'...")
        client.download_file(bucket, s3_key, temp_path)
        return temp_path
        
    return await asyncio.to_thread(_download)

async def delete_file_from_s3(s3_key: str) -> bool:
    """Delete a file from AWS S3."""
    import asyncio
    
    client = get_s3_client()
    if client is None:
        logger.warning("S3 client not initialized; cannot delete object from S3.")
        return False
        
    bucket = settings.AWS_S3_BUCKET
    
    def _delete():
        logger.info(f"Deleting key '{s3_key}' from S3 bucket '{bucket}'...")
        try:
            client.delete_object(Bucket=bucket, Key=s3_key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete S3 object '{s3_key}': {e}")
            return False
            
    return await asyncio.to_thread(_delete)
