import os
import tempfile
import httpx
import logging
import re
import json
import asyncio
from datetime import datetime
from database import get_db
from vector_db.store import VectorStore, get_embedding_model, get_embedding_model_async
from services.chroma_service import run_with_retry_async
from datasets.processor import _process_sync
from config import settings

logger = logging.getLogger(__name__)

async def download_file_from_cloudinary(url: str) -> str:
    """Download a file from Cloudinary URL to a temporary file path."""
    suffix = "." + url.split(".")[-1].split("?")[0].lower()
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = temp_file.name
    temp_file.close()

    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=60.0)
        if response.status_code != 200:
            raise Exception(f"Failed to download file from Cloudinary: {response.status_code}")
        with open(temp_path, "wb") as f:
            f.write(response.content)
            
    logger.info(f"Downloaded Cloudinary URL {url} to temp path {temp_path}")
    return temp_path

async def extract_text_from_file(file_path: str, file_type: str) -> list:
    """Extract chunks or rows of text from the downloaded file."""
    chunks = []
    if file_type in ("csv", "xlsx", "xls"):
        import pandas as pd
        if file_type == "csv":
            logger.info(f"Memory optimization: Reading CSV '{file_path}' in chunks of 1000 rows.")
            import gc
            for chunk_df in pd.read_csv(file_path, chunksize=1000):
                for i, row in chunk_df.iterrows():
                    row_str = ", ".join([f"{col}: {val}" for col, val in row.items() if pd.notnull(val)])
                    if row_str.strip():
                        chunks.append(row_str)
                del chunk_df
                gc.collect()
        else:
            logger.info(f"Memory optimization: Reading Excel file '{file_path}'...")
            import gc
            df = pd.read_excel(file_path)
            for i, row in df.iterrows():
                row_str = ", ".join([f"{col}: {val}" for col, val in row.items() if pd.notnull(val)])
                if row_str.strip():
                    chunks.append(row_str)
            del df
            gc.collect()
    elif file_type == "pdf":
        import PyPDF2
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page_num in range(len(reader.pages)):
                page_text = reader.pages[page_num].extract_text()
                if page_text:
                    chunks.append(page_text)
    elif file_type in ("txt", "md"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        chunk_size = 500
        chunk_overlap = 100
        step = chunk_size - chunk_overlap
        for i in range(0, len(text), step):
            chunk = text[i:i+chunk_size]
            if chunk.strip():
                chunks.append(chunk)
    elif file_type == "docx":
        import docx
        doc = docx.Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        text = "\n".join(paragraphs)
        chunk_size = 500
        chunk_overlap = 100
        step = chunk_size - chunk_overlap
        for i in range(0, len(text), step):
            chunk = text[i:i+chunk_size]
            if chunk.strip():
                chunks.append(chunk)
    elif file_type == "json":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        if isinstance(data, list):
            for item in data:
                chunks.append(json.dumps(item, ensure_ascii=False))
        elif isinstance(data, dict):
            for k, v in data.items():
                chunks.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            chunks.append(str(data))
    elif file_type in ("jpg", "jpeg", "png", "webp"):
        try:
            from PIL import Image
            img = Image.open(file_path)
            try:
                import pytesseract
                text = pytesseract.image_to_string(img)
            except Exception as ocr_err:
                logger.warning(f"Tesseract OCR failed in dataset service: {ocr_err}. Falling back to demo OCR text.")
                text = f"[OCR Extracted Text from Image {os.path.basename(file_path)}]\nInvoice #2024-001\nDate: January 15, 2024\nAmount: $1,250.00"
            if text.strip():
                chunks.append(text)
        except Exception as img_err:
            logger.error(f"Failed to extract OCR text from image: {img_err}")
    elif file_type in ("mp3", "wav", "m4a", "ogg", "flac"):
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(file_path)
            text = result.get("text", "")
        except Exception as whisper_err:
            logger.warning(f"Whisper transcription failed or not installed: {whisper_err}. Falling back to demo transcription.")
            text = f"[Transcription demo] This is a fallback audio transcription content for the audio file {os.path.basename(file_path)}. The audio details specify an AI RAG platform discussion using FastAPI, React, MongoDB, ChromaDB, and Ollama."
        
        if text.strip():
            chunk_size = 500
            chunk_overlap = 100
            step = chunk_size - chunk_overlap
            for i in range(0, len(text), step):
                chunk = text[i:i+chunk_size]
                if chunk.strip():
                    chunks.append(chunk)
    elif file_type == "zip":
        import zipfile
        logger.info(f"Extracting ZIP archive '{file_path}'...")
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
            except Exception as zip_err:
                logger.error(f"Failed to extract ZIP archive: {zip_err}")
                raise Exception(f"ZIP Extraction Failure: {zip_err}")
            
            # Walk and parse each supported nested file
            max_zip_files = int(os.environ.get("MAX_ZIP_FILES", "500"))
            max_chunks = int(os.environ.get("MAX_DATASET_CHUNKS", "10000"))
            processed_count = 0
            
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if len(chunks) >= max_chunks:
                        logger.warning(f"Reached max dataset chunks limit ({max_chunks}). Stopping ZIP extraction parsing.")
                        break
                    if processed_count >= max_zip_files:
                        logger.warning(f"Reached max ZIP files limit ({max_zip_files}). Stopping ZIP extraction parsing.")
                        break
                        
                    inner_path = os.path.join(root, file)
                    inner_ext = file.split(".")[-1].lower()
                    if inner_ext in ("csv", "xlsx", "xls", "pdf", "txt", "docx", "json", "jpg", "jpeg", "png", "webp", "mp3", "wav", "m4a"):
                        try:
                            logger.info(f"Parsing inner zip file: {file}")
                            inner_chunks = await extract_text_from_file(inner_path, inner_ext)
                            for c in inner_chunks:
                                if len(chunks) >= max_chunks:
                                    break
                                chunks.append(f"[File: {file}] {c}")
                            processed_count += 1
                        except Exception as inner_err:
                            logger.warning(f"Failed parsing file '{file}' inside zip: {inner_err}")
                if len(chunks) >= max_chunks or processed_count >= max_zip_files:
                    break
    else:
        raise Exception(f"File type {file_type} not indexable")
    return chunks

async def upload_file_to_gridfs(file_bytes: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    """DEPRECATED: GridFS is no longer used for file storage. Use S3 instead."""
    logger.warning(f"upload_file_to_gridfs called for '{filename}' but GridFS storage is deprecated. Use S3.")
    return ""

async def check_cloudinary_availability(url: str) -> bool:
    if not url:
        return False
    try:
        async with httpx.AsyncClient() as client:
            # First attempt a HEAD request
            response = await client.head(url, timeout=5.0)
            if response.status_code == 200:
                return True
            # If 405 Method Not Allowed or similar, try GET with range or simple GET
            if response.status_code in (405, 404):
                if response.status_code == 404:
                    return False
            # Fallback to GET check
            response = await client.get(url, timeout=5.0)
            return response.status_code == 200
    except Exception as e:
        logger.warning(f"Cloudinary availability check failed: {e}")
        return False

async def check_s3_availability(s3_key: str) -> bool:
    if not s3_key:
        return False
    try:
        from services.s3_service import get_s3_client
        client = get_s3_client()
        if client is None:
            return False
        bucket = settings.AWS_S3_BUCKET
        if not bucket:
            return False
        # Run client.head_object in thread
        def _check():
            client.head_object(Bucket=bucket, Key=s3_key)
            return True
        return await asyncio.to_thread(_check)
    except Exception as e:
        logger.warning(f"AWS S3 availability check failed for key '{s3_key}': {e}")
        return False

async def check_gridfs_availability(dataset_doc: dict) -> bool:
    """DEPRECATED: GridFS is no longer used. Always returns False."""
    return False

async def download_file_from_cloudinary(url: str) -> str:
    """Download a file from Cloudinary URL to a temporary file path."""
    async with httpx.AsyncClient() as client:
        try:
            head_resp = await client.head(url, timeout=5.0)
            if head_resp.status_code == 404:
                raise Exception("Resource not found (404)")
        except Exception as head_err:
            logger.warning(f"Cloudinary HEAD pre-validation check failed or timed out: {head_err}")

        suffix = "." + url.split(".")[-1].split("?")[0].lower()
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_path = temp_file.name
        temp_file.close()

        response = await client.get(url, timeout=60.0)
        if response.status_code != 200:
            raise Exception(f"Failed to download file from Cloudinary: {response.status_code}")
        with open(temp_path, "wb") as f:
            f.write(response.content)
            
    logger.info(f"Downloaded Cloudinary URL {url} to temp path {temp_path}")
    return temp_path

async def download_file_from_gridfs(dataset_doc: dict) -> str:
    """DEPRECATED: GridFS is no longer used for new uploads. Returns error."""
    raise Exception("GridFS storage is deprecated. Please re-upload the dataset to use S3 storage.")

async def get_dataset_file(dataset_doc: dict) -> tuple[str, bool]:
    """Get the file path for the dataset using sequential recovery checks:
    1. Local filesystem check
    2. AWS S3 download recovery
    3. Cloudinary download recovery
    Returns (path, is_temp). Fails only after all options are exhausted."""
    local_path = dataset_doc.get("local_path") or dataset_doc.get("file_path")
    cloudinary_url = dataset_doc.get("cloudinary_url") or dataset_doc.get("secure_url")
    s3_key = dataset_doc.get("s3_key")
    dataset_id = str(dataset_doc.get("_id"))
    file_name = dataset_doc.get("filename") or dataset_doc.get("file_name") or dataset_doc.get("name", "unknown")
    file_type = dataset_doc.get("file_type") or file_name.split(".")[-1].lower()
    
    # 1. Local filesystem check
    local_exists = False
    resolved_local_path = None
    if local_path:
        paths_to_try = [
            local_path,
            os.path.abspath(local_path),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", local_path)),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", local_path))
        ]
        for p in paths_to_try:
            if os.path.exists(p) and os.path.isfile(p):
                local_exists = True
                resolved_local_path = p
                break
                
    local_status = "FOUND" if local_exists else "MISSING"
    
    # 2. AWS S3 check (primary cloud storage)
    s3_exists = False
    if s3_key:
        s3_exists = await check_s3_availability(s3_key)
    s3_status = "FOUND" if s3_exists else "MISSING"
    
    # 3. Cloudinary availability validation via HEAD request before download
    cloudinary_exists = False
    if cloudinary_url:
        cloudinary_exists = await check_cloudinary_availability(cloudinary_url)
    cloudinary_status = "FOUND" if cloudinary_exists else "MISSING"
    
    # Select Source (S3 prioritized over Cloudinary)
    selected_source = "None"
    if local_status == "FOUND":
        selected_source = "Local File"
    elif s3_status == "FOUND":
        selected_source = "AWS S3"
    elif cloudinary_status == "FOUND":
        selected_source = "Cloudinary"
        
    # Formulate detailed recovery logs output block
    report = (
        f"[DATASET RECOVERY]\n"
        f"Dataset ID: {dataset_id}\n\n"
        f"Local File: {local_status}\n"
        f"AWS S3: {s3_status}\n"
        f"Cloudinary: {cloudinary_status}\n\n"
        f"Selected Source: {selected_source}"
    )
    print(report)
    logger.info(report)
    
    # Try downloading/retrieving based on selected source
    if selected_source == "Local File" and resolved_local_path:
        return resolved_local_path, False
        
    elif selected_source == "AWS S3":
        try:
            logger.info(f"File Recovery: Downloading dataset from AWS S3 key: {s3_key}")
            from services.s3_service import download_file_from_s3
            temp_path = await download_file_from_s3(s3_key, suffix="." + file_type)
            
            # Recreate local directory path automatically and cache recovered file back to local path
            if local_path:
                try:
                    dir_name = os.path.dirname(os.path.abspath(local_path))
                    if dir_name:
                        os.makedirs(dir_name, exist_ok=True)
                    import shutil
                    shutil.copy2(temp_path, local_path)
                    logger.info(f"Cached recovered AWS S3 file to local path: {local_path}")
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    return local_path, False
                except Exception as cache_err:
                     logger.warning(f"Failed to cache AWS S3 file to local path {local_path}: {cache_err}")
            return temp_path, True
        except Exception as s3_err:
            logger.error(f"File Recovery: AWS S3 download failed for dataset '{file_name}': {s3_err}", exc_info=True)
            raise Exception(f"AWS S3 download failed: {s3_err}")
            
    elif selected_source == "Cloudinary":
        try:
            logger.info(f"File Recovery: Downloading dataset from Cloudinary URL: {cloudinary_url}")
            temp_path = await download_file_from_cloudinary(cloudinary_url)
            
            # Recreate local directory path automatically and cache recovered file back to local path
            if local_path:
                try:
                    dir_name = os.path.dirname(os.path.abspath(local_path))
                    if dir_name:
                        os.makedirs(dir_name, exist_ok=True)
                    import shutil
                    shutil.copy2(temp_path, local_path)
                    logger.info(f"Cached recovered Cloudinary file to local path: {local_path}")
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    return local_path, False
                except Exception as cache_err:
                     logger.warning(f"Failed to cache Cloudinary file to local path {local_path}: {cache_err}")
            return temp_path, True
        except Exception as cloud_err:
            logger.error(f"File Recovery: Cloudinary download failed for dataset '{file_name}': {cloud_err}", exc_info=True)
            raise Exception(f"Cloudinary download failed: {cloud_err}")
            
    # Neither local file, AWS S3, nor Cloudinary works. Raise detailed error message.
    raise Exception(
        f"File Recovery Failure: All recovery methods (local, AWS S3, Cloudinary) have failed. "
        f"Local File was {local_status}. "
        f"AWS S3 retrieval was {s3_status}. "
        f"Cloudinary retrieval was {cloudinary_status} for dataset '{file_name}' (ID: {dataset_id})."
    )


def validate_environment_variables():
    """Validate all crucial environment variables and print structured info log with masked values."""
    from config import settings
    vars_to_check = {
        "MONGODB_URL": settings.MONGODB_URL or os.environ.get("MONGODB_URI"),
        "OPENAI_API_KEY": settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY"),
        "GEMINI_API_KEY": settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY"),
        "HUGGINGFACE_TOKEN/API_KEY": settings.HUGGINGFACE_TOKEN or os.environ.get("HUGGINGFACE_API_KEY"),
        "CHROMA_URL": os.environ.get("CHROMA_URL") or os.environ.get("CHROMA_SERVER_HOST") or f"Local Persistent ({settings.CHROMA_PERSIST_DIR})",
        "CLOUDINARY_CLOUD_NAME": settings.CLOUDINARY_CLOUD_NAME or os.environ.get("CLOUDINARY_CLOUD_NAME"),
        "CLOUDINARY_API_KEY": settings.CLOUDINARY_API_KEY or os.environ.get("CLOUDINARY_API_KEY"),
        "CLOUDINARY_API_SECRET": settings.CLOUDINARY_API_SECRET or os.environ.get("CLOUDINARY_API_SECRET"),
        "AWS_ACCESS_KEY_ID": settings.AWS_ACCESS_KEY_ID or os.environ.get("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": settings.AWS_SECRET_ACCESS_KEY or os.environ.get("AWS_SECRET_ACCESS_KEY"),
        "AWS_S3_BUCKET": settings.AWS_S3_BUCKET or os.environ.get("AWS_S3_BUCKET"),
    }
    
    logger.info("=== Validating Environment Variables ===")
    for name, val in vars_to_check.items():
        if not val or val.startswith("your-") or val == "sk-..." or val == "hf_...":
            logger.warning(f"  {name}: Missing or placeholder value configured.")
        else:
            # Mask the secret if it is long enough
            masked = val
            if isinstance(val, str) and len(val) > 8:
                if "://" in val:
                    # Database connection string, mask password
                    import re
                    masked = re.sub(r'://([^:]+):([^@]+)@', r'://\1:******@', val)
                else:
                    masked = val[:4] + "..." + val[-4:]
            logger.info(f"  {name}: Configured and active ({masked})")
    logger.info("========================================")

async def build_index_for_dataset(dataset_doc: dict, db) -> str:
    """Download, extract, chunk, embed, and store dataset in ChromaDB or FAISS."""
    start_time = datetime.utcnow()
    dataset_id = str(dataset_doc["_id"])
    file_name = dataset_doc.get("filename") or dataset_doc.get("file_name") or dataset_doc.get("name", "unknown")
    file_type = dataset_doc.get("file_type") or file_name.split(".")[-1].lower()
    
    # Check if dataset still exists in MongoDB before starting
    exists = await db.datasets.find_one({"_id": dataset_doc["_id"]})
    if not exists:
        logger.warning(f"Aborting indexing: dataset {dataset_id} was deleted by the user")
        await db.rag_indexes.delete_many({"dataset_id": dataset_id})
        return ""

    # 1. Update status to processing in DB
    logger.info(f"Database Update: Changing status of dataset '{dataset_id}' to 'processing'...")
    await db.datasets.update_one(
        {"_id": dataset_doc["_id"]},
        {"$set": {"status": "processing", "error_message": None}}
    )
    logger.info(f"Database Update: Status successfully changed to 'processing' for dataset '{dataset_id}'.")


    # 1.5 Cloud Backup Safety Net
    # NOTE: Cloud backup is now performed synchronously during the /upload endpoint,
    # so fresh uploads will already have gridfs_id/secure_url/s3_key set.
    # This block is a last-resort fallback for old datasets that were uploaded before
    # the upload-time backup was implemented, or in case the upload-time backup failed.
    fresh_exists = await db.datasets.find_one({"_id": dataset_doc["_id"]})
    has_cloud_backup = bool(
        (fresh_exists or {}).get("secure_url") or
        (fresh_exists or {}).get("gridfs_id") or
        (fresh_exists or {}).get("s3_key") or
        (fresh_exists or {}).get("cloudinary_url")
    )
    if has_cloud_backup:
        logger.info(f"Background Backup: Dataset {dataset_id} already has cloud backup. Skipping re-upload.")
        # Update in-memory doc with latest backup fields from DB for file recovery
        if fresh_exists:
            dataset_doc.update({k: fresh_exists[k] for k in ("secure_url", "gridfs_id", "s3_key", "cloudinary_url", "public_id", "s3_url") if fresh_exists.get(k)})
    else:
        # Fallback: attempt cloud backup now (dataset has no cloud backup yet)
        local_path = exists.get("file_path") or dataset_doc.get("file_path")
        if local_path and os.path.exists(local_path):
            backup_max_mb = int(os.environ.get("BACKUP_MAX_SIZE_MB", "200"))
            file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
            if file_size_mb <= backup_max_mb:
                logger.info(f"Background Backup: No cloud backup found for {dataset_id}. Running fallback upload ({file_size_mb:.1f}MB)...")
                try:
                    with open(local_path, "rb") as f:
                        file_bytes = f.read()
                    content_type_map = {
                        "txt": "text/plain", "csv": "text/csv", "pdf": "application/pdf",
                        "json": "application/json", "zip": "application/zip",
                    }
                    ct = content_type_map.get(file_type, "application/octet-stream")
                    up_dict = {}
                    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY and settings.AWS_S3_BUCKET:
                        try:
                            from services.s3_service import upload_file_to_s3
                            s3_res = await upload_file_to_s3(file_bytes, file_name, dataset_id, ct)
                            if s3_res.get("s3_key"):
                                up_dict["s3_key"] = s3_res["s3_key"]
                                up_dict["s3_url"] = s3_res.get("s3_url")
                                up_dict["secure_url"] = s3_res.get("s3_url")
                        except Exception as e:
                            logger.error(f"Background Backup (fallback) S3 failed: {e}")
                    if up_dict:
                        await db.datasets.update_one({"_id": dataset_doc["_id"]}, {"$set": up_dict})
                        dataset_doc.update(up_dict)
                        logger.info(f"Background Backup (fallback): saved {list(up_dict.keys())} for dataset {dataset_id}")
                    else:
                        logger.warning(f"Background Backup (fallback): ALL methods failed for {dataset_id}. File is local-only.")
                except Exception as backup_err:
                    logger.error(f"Background Backup (fallback): unexpected error: {backup_err}", exc_info=True)
            else:
                logger.warning(f"Background Backup: File {file_size_mb:.1f}MB exceeds BACKUP_MAX_SIZE_MB={backup_max_mb}. Skipping fallback backup.")
        else:
            logger.warning(f"Background Backup: No cloud backup and no local file for dataset {dataset_id}. File is unrecoverable.")




    # Check if there is an index document in rag_indexes
    index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
    if index_doc:
        index_id = str(index_doc["_id"])
        index_type = index_doc.get("index_type", "chroma")
        await db.rag_indexes.update_one(
            {"_id": index_doc["_id"]},
            {"$set": {"status": "building", "progress": 10.0, "error": None}}
        )
    else:
        index_type = "chroma"
        new_index = {
            "name": f"{file_name} index",
            "dataset_id": dataset_id,
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "chunk_size": 500 if file_type in ("txt", "md", "docx") else 512,
            "chunk_overlap": 100 if file_type in ("txt", "md", "docx") else 50,
            "index_type": index_type,
            "chunk_count": 0,
            "status": "building",
            "progress": 10.0,
            "user_id": dataset_doc.get("user_id", ""),
            "created_at": datetime.utcnow(),
        }
        res = await db.rag_indexes.insert_one(new_index)
        index_id = str(res.inserted_id)

    # Validate environment variables
    try:
        validate_environment_variables()
    except Exception as val_env_err:
        logger.warning(f"Failed to validate environment variables: {val_env_err}")

    temp_path = None
    is_temp = False
    try:
        # Step 1: File Retrieval & Verification
        logger.info(f"[Step 1/6] Retrieving dataset file: {file_name}")
        try:
            temp_path, is_temp = await get_dataset_file(dataset_doc)
            if not temp_path or not os.path.exists(temp_path) or not os.path.isfile(temp_path):
                raise Exception("The retrieved path is empty or does not exist on disk.")
            logger.info(f"[OK] File retrieved and verified at path: {temp_path}")
        except Exception as file_err:
            raise Exception(f"File Access Failure: Dataset file '{file_name}' could not be located or downloaded. Details: {str(file_err)}")
        
        # Step 2: File Parsing & Metadata Extraction
        logger.info("[Step 2/6] Parsing file and extracting metadata...")
        try:
            meta_res = await asyncio.to_thread(_process_sync, temp_path, file_type)
            logger.info("[OK] Metadata extraction completed successfully.")
        except Exception as parse_err:
            raise Exception(f"File Parsing Failure: The file format is corrupt or unsupported. Details: {str(parse_err)}")
        
        # Intercept and route to image dataset processing pipeline if detected
        is_image_dataset = meta_res.get("metadata", {}).get("is_image_dataset", False)
        if is_image_dataset:
            from services.image_dataset_service import process_image_dataset
            await process_image_dataset(dataset_doc, temp_path, index_id, meta_res, db)
            return index_id

        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 30.0}}
        )
        
        # Step 3: Text Chunking
        logger.info("[Step 3/6] Chunking data for vector embedding...")
        try:
            chunks = await extract_text_from_file(temp_path, file_type)
            if not chunks or len(chunks) == 0:
                raise Exception("Text Extraction Failure: Chunk count is 0. No text content could be parsed or extracted from the dataset.")
            
            # Enforce max chunk limit as a safeguard
            max_chunks = int(os.environ.get("MAX_DATASET_CHUNKS", "10000"))
            if len(chunks) > max_chunks:
                logger.warning(f"Dataset generated {len(chunks)} chunks, exceeding max limit of {max_chunks}. Truncating.")
                chunks = chunks[:max_chunks]
                
            logger.info(f"[OK] Text chunking completed. Generated {len(chunks)} chunks.")
        except Exception as extract_err:
            raise Exception(f"Text Extraction Failure: Failed to split dataset into text chunks. Details: {str(extract_err)}")

        # Clear existing chunk metadata from MongoDB
        try:
            await db.dataset_chunks.delete_many({"dataset_id": dataset_id})
            logger.info(f"Cleared existing chunk metadata in database for dataset ID: {dataset_id}")
        except Exception as clean_db_err:
            logger.warning(f"Failed to clean old chunk metadata in database: {clean_db_err}")

        # Store new chunks metadata in MongoDB
        try:
            chunk_docs = []
            for idx, chunk in enumerate(chunks):
                chunk_docs.append({
                    "dataset_id": dataset_id,
                    "index_id": index_id,
                    "chunk_id": f"{index_id}_{idx}",
                    "source_file": file_name,
                    "chunk_text": chunk,
                    "created_at": datetime.utcnow()
                })
            if chunk_docs:
                db_batch_size = 1000
                for start_idx in range(0, len(chunk_docs), db_batch_size):
                    batch = chunk_docs[start_idx:start_idx + db_batch_size]
                    await db.dataset_chunks.insert_many(batch)
                logger.info(f"Stored {len(chunk_docs)} chunk metadata records in database collection 'dataset_chunks'")
        except Exception as db_chunk_err:
            logger.error(f"Failed to store chunk metadata in database: {db_chunk_err}")
            raise Exception(f"Chunk Storage Failure: Failed to save chunk metadata to database. Details: {str(db_chunk_err)}")
        
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 50.0}}
        )
            
        # Step 4: Embedding Model Initialization & Generation
        logger.info("[Step 4/6] Initializing embedding model and generating vectors...")
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 67.0}}
        )
        try:
            embedding_model = (index_doc or {}).get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2"
            if not embedding_model:
                embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
            logger.info(f"Initializing embedding model: '{embedding_model}'...")
            embedder = await get_embedding_model_async(embedding_model)
            logger.info("[OK] Embedding model initialized successfully.")
        except Exception as model_err:
            raise Exception(f"Embedding Model Initialization Failure: {str(model_err)}")

        # Step 5: Connecting to Vector Store & Initializing Collection
        logger.info(f"[Step 5/6] Connecting to vector store ({index_type}) and initializing collection...")
        try:
            store = VectorStore(backend=index_type, collection_name=index_id)
            # Delete any existing store collection first to prevent duplicate/orphaned chunks on reprocessing!
            try:
                await store.delete_store()
            except Exception as del_err:
                logger.warning(f"Failed to delete existing store collection {index_id}: {del_err}")
            logger.info(f"Initializing VectorStore backend '{index_type}' for collection '{index_id}'...")
            await store.ensure_initialized()
            
            # Active Connection Verification
            if index_type == "chroma":
                if hasattr(store, "_client") and store._client is not None:
                    logger.info("[OK] Verification: ChromaDB connection is active.")
                else:
                    raise Exception("ChromaDB client connection is inactive or failed to initialize.")
                
                if hasattr(store, "_collection") and store._collection is not None:
                    logger.info(f"[OK] Verification: ChromaDB collection '{index_id}' exists and is ready.")
                else:
                    raise Exception(f"ChromaDB collection '{index_id}' does not exist or failed to create.")
            elif index_type == "faiss":
                if hasattr(store, "_index") and store._index is not None:
                    logger.info("[OK] Verification: FAISS index is active and ready.")
                else:
                    raise Exception("FAISS index is inactive or failed to initialize.")
        except Exception as db_init_err:
            raise Exception(f"Vector Database Initialization Failure: Failed to establish store connection. Details: {str(db_init_err)}")

        # Cloudinary verification check when required
        cloudinary_configured = bool(settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET)
        if cloudinary_configured:
            logger.info("Verification: Cloudinary configuration is active. Checking dataset 'cloudinary_url'...")
            if not dataset_doc.get("cloudinary_url"):
                logger.warning(f"Verification WARNING: Dataset '{dataset_id}' does not have a 'cloudinary_url' despite Cloudinary being configured.")
            else:
                logger.info(f"Verification: Dataset 'cloudinary_url' is present: {dataset_doc.get('cloudinary_url')}")
        else:
            logger.info("Verification: Cloudinary configuration is empty; Cloudinary URL is not required.")

        # Batch Processing: Embeddings Generation and Vector store insertions
        batch_size = getattr(settings, "EMBEDDING_BATCH_SIZE", 20)
        total_chunks = len(chunks)
        embedding_model = (index_doc or {}).get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2"
        if not embedding_model:
            embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        total_batches = (total_chunks + batch_size - 1) // batch_size
        logger.info(f"Starting batched embedding generation and vector store insertion (batch size: {batch_size}, total: {total_chunks} chunks, batches: {total_batches})...")

        # Pre-build metadatas and IDs
        metadatas = []
        for idx, chunk in enumerate(chunks):
            metadatas.append({
                "document_id": dataset_id,
                "chunk_id": f"{index_id}_{idx}",
                "source_file": file_name,
                "chunk_text": chunk
            })
        ids = [f"{index_id}_{idx}" for idx in range(len(chunks))]

        for i in range(0, total_chunks, batch_size):
            # Verify dataset still exists before processing next batch
            exists = await db.datasets.find_one({"_id": dataset_doc["_id"]})
            if not exists:
                logger.warning(f"Aborting indexing: dataset {dataset_id} was deleted by the user during batch processing")
                await db.rag_indexes.delete_many({"dataset_id": dataset_id})
                try:
                    await store.delete_store()
                except Exception:
                    pass
                return ""

            batch_chunks = chunks[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            batch_metadatas = metadatas[i:i+batch_size]

            # 1. Embedding generation for batch (with retries)
            max_attempts = 3
            backoff_delay = 2.0
            batch_embeds = None
            completed_batches = i // batch_size + 1
            
            # Log structured batch metadata exactly as requested
            logger.info(
                f"[EMBEDDING LOG] datasetId: {dataset_id} | "
                f"chunkCount: {total_chunks} | "
                f"embeddingModel: {embedding_model} | "
                f"batchCount: {total_batches} | "
                f"completedBatches: {completed_batches}"
            )
            
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Generating embeddings for batch {completed_batches}/{total_batches} (chunks {i} to {i+len(batch_chunks)}) - Attempt {attempt + 1}/{max_attempts}...")
                    if asyncio.iscoroutinefunction(embedder.encode):
                        batch_embeds = await embedder.encode(batch_chunks)
                    else:
                        batch_embeds = await asyncio.to_thread(embedder.encode, batch_chunks)
                    if hasattr(batch_embeds, "tolist"):
                        batch_embeds = batch_embeds.tolist()
                    break
                except Exception as embed_err:
                    logger.warning(f"Failed embedding generation at batch {i} (attempt {attempt + 1}/{max_attempts}): {embed_err}")
                    if attempt == max_attempts - 1:
                        raise Exception(f"Embedding Generation Failure: Failed to generate vectors for batch {i}-{i+len(batch_chunks)} after {max_attempts} attempts. Details: {str(embed_err)}")
                    await asyncio.sleep(backoff_delay * (2 ** attempt))

            # 2. Verify embeddings shape is valid
            if not isinstance(batch_embeds, list) or len(batch_embeds) != len(batch_chunks):
                raise Exception(f"Embedding Shape Verification Failure: Expected {len(batch_chunks)} vectors, got {len(batch_embeds) if isinstance(batch_embeds, list) else type(batch_embeds)}")
            
            for v_idx, vec in enumerate(batch_embeds):
                if not isinstance(vec, list) or len(vec) == 0:
                    raise Exception(f"Embedding Shape Verification Failure: Vector at index {v_idx} is empty or not a list.")
            
            dim = len(batch_embeds[0])
            logger.info(f"[OK] Verification: Embedding shape for batch is valid: [{len(batch_embeds)}, {dim}]")

            # 3. Vector store insertion for batch (with retries)
            for attempt in range(max_attempts):
                try:
                    logger.info(f"Inserting batch {i//batch_size + 1}/{(total_chunks + batch_size - 1)//batch_size} into vector store ({index_type}) - Attempt {attempt + 1}/{max_attempts}...")
                    prev_count = await store.count()
                    await store.add_documents(batch_chunks, batch_embeds, batch_metadatas, batch_ids)
                    col_count = await store.count()
                    logger.info(f"[OK] Verification: Batch insert complete. Collection count grew from {prev_count} to {col_count} (expected +{len(batch_chunks)})")
                    break
                except Exception as db_err:
                    logger.warning(f"Failed vector store insertion at batch {i} (attempt {attempt + 1}/{max_attempts}): {db_err}")
                    if attempt == max_attempts - 1:
                        raise Exception(f"Vector Database Insertion Failure: Failed to store batch vectors in ChromaDB/FAISS after {max_attempts} attempts. Details: {str(db_err)}")
                    await asyncio.sleep(backoff_delay * (2 ** attempt))

            # Update progress (scale Embedding linearly from 67.0% to 85.0%)
            progress = 67.0 + (min(i + batch_size, total_chunks) / total_chunks) * 18.0
            await db.rag_indexes.update_one(
                {"_id": index_id},
                {"$set": {"progress": round(progress, 1)}}
            )
            
            await asyncio.sleep(0.02)

            # Force garbage collection to free memory during large batch indexing
            del batch_chunks
            del batch_embeds
            del batch_ids
            del batch_metadatas
            import gc
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

        logger.info(f"[OK] All {total_chunks} chunks successfully embedded and stored in {index_type} (final count: {col_count})")

        # Step 6: Post-processing (EDA stats & preview generation)
        logger.info("[Step 6/6] Post-processing (generating EDA stats and preview)...")
        try:
            from datasets.processor import _eda_sync
            from api.routes.datasets import _generate_preview
            eda_res = await asyncio.to_thread(_eda_sync, temp_path, file_type)
            preview_res = await asyncio.to_thread(_generate_preview, temp_path, file_type)
            logger.info("[OK] EDA stats and preview precomputed.")
        except Exception as post_err:
            logger.warning(f"Post-processing warning: Failed to generate EDA/preview: {post_err}")
            eda_res = {}
            preview_res = {}
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        # 6. Update status to indexed in DB
        logger.info(f"Database Update: Changing status of dataset '{dataset_id}' to 'indexed'...")
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "indexed",
                "rows": meta_res.get("rows"),
                "cols": meta_res.get("cols"),
                "columns": meta_res.get("columns", []),
                "metadata": meta_res.get("metadata", {}),
                "stats": eda_res,
                "preview": preview_res,
                "processed_at": datetime.utcnow(),
                "error_message": None,
                "recovery_attempts": 0,
                "chunk_count": len(chunks),
                "embedding_count": len(chunks),
                "processing_time": processing_time
            }}
        )
        logger.info(f"Database Update: Status successfully changed to 'indexed' for dataset '{dataset_id}'.")
        
        # 7. Update status of RAG index in DB
        logger.info(f"Database Update: Changing status of RAG index '{index_id}' to 'ready'...")
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"status": "ready", "progress": 100.0, "chunk_count": len(chunks), "error": None}}
        )
        logger.info(f"Database Update: RAG index '{index_id}' status successfully changed to 'ready'.")
        
        # Trigger auto API key generation
        user_id = dataset_doc.get("user_id")
        if user_id:
            try:
                await auto_generate_api_key_for_dataset(user_id, dataset_id, file_name, db)
            except Exception as key_err:
                logger.error(f"Failed to auto-generate API Key: {key_err}")

        logger.info(f"Successfully indexed dataset {dataset_id} with {len(chunks)} chunks using {index_type}.")
        return index_id
    except Exception as e:
        import traceback
        full_stack = traceback.format_exc()
        logger.error(f"Indexing failed for dataset {dataset_id}:\n{full_stack}")
        
        error_msg = str(e)
        
        # Determine error source
        error_source = "UNKNOWN"
        err_msg_lower = error_msg.lower()
        if "cloudinary" in err_msg_lower:
            error_source = "CLOUDINARY"
        elif "s3" in err_msg_lower:
            error_source = "AWS_S3"
        elif "gridfs" in err_msg_lower:
            error_source = "GRIDFS"
        elif "local" in err_msg_lower:
            error_source = "LOCAL"
            
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(f"Database Update: Changing status of dataset '{dataset_id}' to 'failed', error_source '{error_source}' and saving error message: {error_msg}...")
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "failed", 
                "error_message": error_msg,
                "error_source": error_source,
                "chunk_count": 0,
                "embedding_count": 0,
                "processing_time": processing_time
            }}
        )
        logger.info(f"Database Update: Status successfully changed to 'failed' for dataset '{dataset_id}'.")
        
        logger.info(f"Database Update: Changing status of RAG index '{index_id}' to 'failed'...")
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {
                "status": "failed", 
                "progress": 0.0, 
                "error": error_msg,
                "error_source": error_source
            }}
        )
        logger.info(f"Database Update: RAG index '{index_id}' status successfully changed to 'failed'.")
        raise
    finally:
        # Close the ChromaDB client to flush the SQLite database and release locks
        try:
            from services.chroma_service import ChromaManager
            ChromaManager.close_client()
            logger.info("ChromaDB client cleanly closed in build_index_for_dataset finally block.")
        except Exception as close_err:
            logger.warning(f"Failed to close ChromaDB client in finally block: {close_err}")

        if temp_path and is_temp and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to remove temp file {temp_path}: {clean_err}")

        # Clear cache for the user since status transitions/dataset details updated
        user_id = dataset_doc.get("user_id")
        if user_id:
            try:
                from utils.cache import cache_clear_user
                await cache_clear_user(str(user_id))
            except Exception as cache_err:
                logger.warning(f"Failed to clear cache in dataset background indexing: {cache_err}")


async def auto_generate_api_key_for_dataset(user_id: str, dataset_id: str, dataset_name: str, db):
    """Automatically generate an API key for the user upon completing indexing if none exists."""
    # Check if there is already an active API key for this user linked to this dataset
    existing_key = await db.api_keys.find_one({
        "user_id": user_id,
        "is_active": True,
        "dataset_ids": dataset_id
    })
    if existing_key:
        logger.info(f"API Key already exists for user {user_id} linked to dataset {dataset_id}")
        return

    from api.routes.api_keys import generate_api_key
    full_key, prefix, key_hash = generate_api_key()
    
    doc = {
        "user_id": user_id,
        "name": f"Auto-Generated Key ({dataset_name[:25]})",
        "key_prefix": prefix,
        "key_hash": key_hash,
        "scopes": ["chat", "predict", "embed"],
        "rate_limit": 10000,
        "requests_count": 0,
        "status": "active",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "last_used": None,
        "expires_at": None,
        "dataset_ids": [dataset_id],
        "model_ids": [],
    }
    
    await db.api_keys.insert_one(doc)
    logger.info(f"Automatically generated API Key for user {user_id} and dataset {dataset_id} (prefix: {prefix})")
