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

async def upload_file_to_s3(
    file_bytes: bytes,
    filename: str,
    dataset_id: str,
    content_type: str = "application/octet-stream",
    timestamp: int = None
) -> dict:
    """Upload raw file bytes to AWS S3 and return secure url and key."""
    import asyncio
    import time
    
    client = get_s3_client()
    if client is None:
        raise Exception("AWS S3 storage is not configured or failed to initialize.")
        
    bucket = settings.AWS_S3_BUCKET
    if timestamp is None:
        timestamp = int(time.time())
    key = f"datasets/{dataset_id}/{timestamp}-{filename}"
    
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

async def get_s3_object_stream(s3_key: str):
    """Fetch a file object stream from AWS S3."""
    import asyncio
    client = get_s3_client()
    if client is None:
        raise Exception("AWS S3 storage is not configured or failed to initialize.")
        
    bucket = settings.AWS_S3_BUCKET
    if not bucket:
        raise Exception("AWS_S3_BUCKET is not configured in settings.")
    if not s3_key:
        raise Exception("s3_key parameter is empty.")
        
    def _get_stream():
        logger.info(f"Streaming key '{s3_key}' from S3 bucket '{bucket}'...")
        try:
            # Verify object exists in S3 before stream download
            client.head_object(Bucket=bucket, Key=s3_key)
            response = client.get_object(Bucket=bucket, Key=s3_key)
            return response['Body']
        except Exception as e:
            logger.error(f"S3 stream retrieval failed for key '{s3_key}' in bucket '{bucket}': {e}", exc_info=True)
            raise e
            
    return await asyncio.to_thread(_get_stream)

async def download_file_from_s3(s3_key: str, suffix: str = ".txt") -> str:
    """Download a file from AWS S3 to a temporary file path."""
    import asyncio
    
    client = get_s3_client()
    if client is None:
        raise Exception("AWS S3 storage is not configured or failed to initialize.")
        
    bucket = settings.AWS_S3_BUCKET
    if not bucket:
        raise Exception("AWS_S3_BUCKET is not configured in settings.")
    if not s3_key:
        raise Exception("s3_key parameter is empty.")
        
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = temp_file.name
    temp_file.close()
    
    def _download():
        logger.info(f"Downloading key '{s3_key}' from S3 bucket '{bucket}' to '{temp_path}'...")
        try:
            # Verify object exists in S3 before download
            client.head_object(Bucket=bucket, Key=s3_key)
            client.download_file(bucket, s3_key, temp_path)
            return temp_path
        except Exception as e:
            logger.error(f"S3 download failed for key '{s3_key}' in bucket '{bucket}': {e}", exc_info=True)
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            raise e
        
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

async def upload_chunks_to_s3(chunks: list, dataset_id: str) -> str:
    """Upload list of chunk dicts as a JSON file to AWS S3."""
    import json
    import asyncio
    
    client = get_s3_client()
    if client is None:
        raise Exception("AWS S3 storage is not configured or failed to initialize.")
        
    bucket = settings.AWS_S3_BUCKET
    key = f"datasets/{dataset_id}/chunks.json"
    
    # Serialize chunks list to json bytes
    chunks_json = json.dumps(chunks, default=str)
    chunks_bytes = chunks_json.encode('utf-8')
    
    def _upload():
        logger.info(f"Uploading chunks JSON to S3 bucket '{bucket}' as key '{key}'...")
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=chunks_bytes,
            ContentType="application/json"
        )
        return key
        
    return await asyncio.to_thread(_upload)

async def delete_chunks_from_s3(dataset_id: str) -> bool:
    """Delete chunks JSON from AWS S3."""
    import asyncio
    client = get_s3_client()
    if client is None:
        logger.warning("S3 client not initialized; cannot delete chunks JSON.")
        return False
    bucket = settings.AWS_S3_BUCKET
    key = f"datasets/{dataset_id}/chunks.json"
    
    def _delete():
        logger.info(f"Deleting chunks key '{key}' from S3 bucket '{bucket}'...")
        try:
            client.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete chunks key '{key}' from S3: {e}")
            return False
            
    return await asyncio.to_thread(_delete)
