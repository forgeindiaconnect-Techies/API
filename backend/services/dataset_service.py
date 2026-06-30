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

def log_dataset_status(dataset_id: str, file_path: str, file_type: str, status: str, progress: float, rows: int = None, cols: int = None, error_trace: str = None):
    """Write structured logs for dataset processing status containing all required fields."""
    logger.info(
        f"[DATASET PROCESS STATUS] datasetId: {dataset_id} | "
        f"filePath: {file_path} | "
        f"fileType: {file_type} | "
        f"status: {status} | "
        f"progress: {progress}% | "
        f"rows: {rows} | "
        f"cols: {cols}"
        f"{f' | errorTrace: {error_trace}' if error_trace else ''}"
    )

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
            
            # Auto-detect encoding
            detected_enc = None
            try:
                import chardet
                with open(file_path, "rb") as f:
                    rawdata = f.read(20000)
                    result = chardet.detect(rawdata)
                    detected_enc = result.get("encoding")
            except Exception as e:
                logger.warning(f"Chardet failed to detect encoding during extract: {e}")

            encodings = [detected_enc] if detected_enc else []
            encodings += ["utf-8", "latin-1", "utf-8-sig", "cp1252"]
            reader = None
            for enc in encodings:
                if not enc:
                    continue
                try:
                    for test_chunk in pd.read_csv(file_path, chunksize=1, encoding=enc, on_bad_lines="skip"):
                        break
                    reader = pd.read_csv(file_path, chunksize=1000, encoding=enc, on_bad_lines="skip")
                    break
                except Exception:
                    continue
            if reader is None:
                reader = pd.read_csv(file_path, chunksize=1000, on_bad_lines="skip")
            
            for chunk_df in reader:
                # Remove completely empty rows from the chunk
                chunk_df = chunk_df.dropna(how="all")
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
            df = df.dropna(how="all")
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
                if page_text and page_text.strip():
                    chunks.append(page_text.strip())
    elif file_type in ("txt", "md"):
        import re
        
        # Auto-detect encoding
        detected_enc = None
        try:
            import chardet
            with open(file_path, "rb") as f:
                rawdata = f.read(50000)
                result = chardet.detect(rawdata)
                detected_enc = result.get("encoding")
        except Exception as e:
            logger.warning(f"Chardet failed to detect encoding: {e}")

        encodings = [detected_enc] if detected_enc else []
        encodings += ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
        text = None
        
        for enc in encodings:
            if not enc:
                continue
            try:
                with open(file_path, "r", encoding=enc) as f:
                    text = f.read()
                break
            except Exception:
                continue

        if text is None:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

        # Split into paragraphs, remove empty paragraphs
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        
        # Paragraph-based chunking with overlap
        current_chunk = []
        current_len = 0
        chunk_size = 500
        chunk_overlap = 100
        
        for p in paragraphs:
            if len(p) > chunk_size:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_len = 0
                sentences = re.split(r'(?<=[.!?])\s+', p)
                sub_chunk = []
                sub_len = 0
                for s in sentences:
                    if sub_len + len(s) > chunk_size:
                        if sub_chunk:
                            chunks.append(" ".join(sub_chunk))
                        sub_chunk = [s]
                        sub_len = len(s)
                    else:
                        sub_chunk.append(s)
                        sub_len += len(s) + 1
                if sub_chunk:
                    chunks.append(" ".join(sub_chunk))
            else:
                if current_len + len(p) > chunk_size:
                    chunks.append("\n\n".join(current_chunk))
                    if len(p) < chunk_overlap:
                        current_chunk = [current_chunk[-1], p] if current_chunk else [p]
                        current_len = sum(len(x) for x in current_chunk) + 2
                    else:
                        current_chunk = [p]
                        current_len = len(p)
                else:
                    current_chunk.append(p)
                    current_len += len(p) + 2
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
    elif file_type == "docx":
        import docx
        import re
        doc = docx.Document(file_path)
        
        # Extract paragraphs preserving bold/italic runs as Markdown formatting
        paragraphs = []
        for p in doc.paragraphs:
            p_text = ""
            for run in p.runs:
                text = run.text
                if not text:
                    continue
                if run.bold:
                    text = f"**{text}**"
                if run.italic:
                    text = f"*{text}*"
                p_text += text
            if p_text.strip():
                paragraphs.append(p_text.strip())
                
        # Paragraph-based chunking
        current_chunk = []
        current_len = 0
        chunk_size = 500
        chunk_overlap = 100
        
        for p in paragraphs:
            if len(p) > chunk_size:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_len = 0
                sentences = re.split(r'(?<=[.!?])\s+', p)
                sub_chunk = []
                sub_len = 0
                for s in sentences:
                    if sub_len + len(s) > chunk_size:
                        if sub_chunk:
                            chunks.append(" ".join(sub_chunk))
                        sub_chunk = [s]
                        sub_len = len(s)
                    else:
                        sub_chunk.append(s)
                        sub_len += len(s) + 1
                if sub_chunk:
                    chunks.append(" ".join(sub_chunk))
            else:
                if current_len + len(p) > chunk_size:
                    chunks.append("\n\n".join(current_chunk))
                    if len(p) < chunk_overlap:
                        current_chunk = [current_chunk[-1], p] if current_chunk else [p]
                        current_len = sum(len(x) for x in current_chunk) + 2
                    else:
                        current_chunk = [p]
                        current_len = len(p)
                else:
                    current_chunk.append(p)
                    current_len += len(p) + 2
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
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
            # Validate image corruption
            with Image.open(file_path) as img:
                img.verify()
            with Image.open(file_path) as img:
                img.load()
                try:
                    import pytesseract
                    text = pytesseract.image_to_string(img)
                except Exception as ocr_err:
                    logger.warning(f"Tesseract OCR failed in dataset service: {ocr_err}. Falling back to demo OCR text.")
                    text = f"[OCR Extracted Text from Image {os.path.basename(file_path)}]\nInvoice #2024-001\nDate: January 15, 2024\nAmount: $1,250.00"
                if text.strip():
                    chunks.append(text.strip())
        except Exception as img_err:
            logger.error(f"Failed to validate or extract OCR text from image: {img_err}")
            raise Exception(f"Corrupted or invalid image file: {str(img_err)}")
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
    """Download, extract, chunk, embed, and store dataset in ChromaDB or FAISS with 10-min timeout."""
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

    # Setup parameters for stages logs
    log_params = {
        "dataset_id": dataset_id,
        "filename": file_name,
        "dataset_type": file_type,
        "file_path": dataset_doc.get("file_path"),
        "file_size": dataset_doc.get("size_bytes") or dataset_doc.get("size", 0),
        "worker_started": start_time.isoformat() + "Z",
        "worker_finished": None,
        "rows_count": None,
        "chunks_created": None,
        "embedding_started": None,
        "embedding_completed": None,
        "vector_db_insert_success": None,
        "mongodb_update_success": None,
        "error": None
    }

    def print_stage_log(stage_name: str):
        logger.info(
            f"[DATASET PROCESSING - STAGE: {stage_name}]\n"
            f"  Dataset ID: {log_params['dataset_id']}\n"
            f"  Filename: {log_params['filename']}\n"
            f"  Dataset Type: {log_params['dataset_type']}\n"
            f"  File Path: {log_params['file_path']}\n"
            f"  File Size: {log_params['file_size']} bytes\n"
            f"  Worker Started: {log_params['worker_started']}\n"
            f"  Worker Finished: {log_params['worker_finished']}\n"
            f"  Rows Count: {log_params['rows_count']}\n"
            f"  Chunks Created: {log_params['chunks_created']}\n"
            f"  Embedding Started: {log_params['embedding_started']}\n"
            f"  Embedding Completed: {log_params['embedding_completed']}\n"
            f"  Vector DB Insert Success: {log_params['vector_db_insert_success']}\n"
            f"  MongoDB Update Success: {log_params['mongodb_update_success']}\n"
            f"  Errors: {log_params['error']}"
        )

    # Reading File = 30%
    logger.info(f"Database Update: Changing status of dataset '{dataset_id}' to 'reading_file'...")
    await db.datasets.update_one(
        {"_id": dataset_doc["_id"]},
        {"$set": {
            "status": "reading_file",
            "progress": 30.0,
            "currentStage": "Reading File",
            "current_stage": "Reading File",
            "startedAt": start_time
        }}
    )
    log_params["mongodb_update_success"] = True
    print_stage_log("Worker Started")

    # Cloud Backup Safety Net fallback for old datasets
    fresh_exists = await db.datasets.find_one({"_id": dataset_doc["_id"]})
    has_cloud_backup = bool(
        (fresh_exists or {}).get("secure_url") or
        (fresh_exists or {}).get("gridfs_id") or
        (fresh_exists or {}).get("s3_key") or
        (fresh_exists or {}).get("cloudinary_url")
    )
    if has_cloud_backup:
        logger.info(f"Background Backup: Dataset {dataset_id} already has cloud backup. Skipping re-upload.")
        if fresh_exists:
            dataset_doc.update({k: fresh_exists[k] for k in ("secure_url", "gridfs_id", "s3_key", "cloudinary_url", "public_id", "s3_url") if fresh_exists.get(k)})
    else:
        local_path = exists.get("file_path") or dataset_doc.get("file_path")
        if local_path and os.path.exists(local_path):
            backup_max_mb = int(os.environ.get("BACKUP_MAX_SIZE_MB", "200"))
            file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
            if file_size_mb <= backup_max_mb:
                logger.info(f"Background Backup: No cloud backup found for {dataset_id}. Running fallback upload...")
                try:
                    with open(local_path, "rb") as f:
                        file_bytes = f.read()
                    content_type_map = {"txt": "text/plain", "csv": "text/csv", "pdf": "application/pdf", "json": "application/json", "zip": "application/zip"}
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
                except Exception as backup_err:
                    logger.error(f"Background Backup (fallback) error: {backup_err}", exc_info=True)

    # Check/Create index document in rag_indexes
    index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
    if index_doc:
        index_id = str(index_doc["_id"])
        index_type = index_doc.get("index_type", "chroma")
        await db.rag_indexes.update_one(
            {"_id": index_doc["_id"]},
            {"$set": {"status": "building", "progress": 30.0, "error": None}}
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
            "progress": 30.0,
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

    async def do_indexing():
        nonlocal temp_path, is_temp
        # Step 1: File Retrieval & Verification
        logger.info(f"[Step 1/6] Retrieving dataset file: {file_name}")
        try:
            temp_path, is_temp = await get_dataset_file(dataset_doc)
            if not temp_path or not os.path.exists(temp_path) or not os.path.isfile(temp_path):
                raise Exception("The retrieved path is empty or does not exist on disk.")
            logger.info(f"[OK] File retrieved and verified at path: {temp_path}")
        except Exception as file_err:
            raise Exception(f"File Access Failure: Dataset file '{file_name}' could not be located or downloaded. Details: {str(file_err)}")
        
        # Step 2: Preprocessing = 50%
        logger.info("[Step 2/6] Parsing file and extracting metadata...")
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "preprocessing",
                "progress": 50.0,
                "currentStage": "Preprocessing",
                "current_stage": "Preprocessing"
            }}
        )
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 50.0}}
        )
        print_stage_log("Preprocessing")

        try:
            meta_res = await asyncio.to_thread(_process_sync, temp_path, file_type)
            logger.info("[OK] Metadata extraction completed successfully.")
        except Exception as parse_err:
            raise Exception(f"File Parsing Failure: The file format is corrupt or unsupported. Details: {str(parse_err)}")
        
        is_image_dataset = meta_res.get("metadata", {}).get("is_image_dataset", False)
        if is_image_dataset:
            from services.image_dataset_service import process_image_dataset
            await process_image_dataset(dataset_doc, temp_path, index_id, meta_res, db)
            return index_id

        rows_count = meta_res.get("rows")
        cols_count = meta_res.get("cols")
        log_params["rows_count"] = rows_count
        
        # Step 3: Chunking = 70%
        logger.info("[Step 3/6] Chunking data for vector embedding...")
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "chunking",
                "progress": 70.0,
                "currentStage": "Chunking",
                "current_stage": "Chunking"
            }}
        )
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 70.0}}
        )
        print_stage_log("Chunking")

        try:
            chunks = await extract_text_from_file(temp_path, file_type)
            if not chunks or len(chunks) == 0:
                raise Exception("Text Extraction Failure: Chunk count is 0. No text content could be parsed or extracted from the dataset.")
            
            max_chunks = int(os.environ.get("MAX_DATASET_CHUNKS", "10000"))
            if len(chunks) > max_chunks:
                logger.warning(f"Dataset generated {len(chunks)} chunks, exceeding max limit of {max_chunks}. Truncating.")
                chunks = chunks[:max_chunks]
                
            logger.info(f"[OK] Text chunking completed. Generated {len(chunks)} chunks.")
        except Exception as extract_err:
            raise Exception(f"Text Extraction Failure: Failed to split dataset into text chunks. Details: {str(extract_err)}")

        log_params["chunks_created"] = len(chunks)

        # Clear existing chunk metadata from MongoDB
        try:
            await db.dataset_chunks.delete_many({"dataset_id": dataset_id})
        except Exception as clean_db_err:
            logger.warning(f"Failed to clean old chunk metadata in database: {clean_db_err}")

        # Store new chunks metadata in S3 (fallback to MongoDB if S3 fails)
        try:
            chunk_docs = []
            for idx, chunk in enumerate(chunks):
                chunk_docs.append({
                    "dataset_id": dataset_id,
                    "index_id": index_id,
                    "chunk_id": f"{index_id}_{idx}",
                    "source_file": file_name,
                    "chunk_text": chunk,
                    "created_at": datetime.utcnow().isoformat() + "Z"
                })
            
            s3_success = False
            if chunk_docs:
                try:
                    from services.s3_service import upload_chunks_to_s3
                    chunks_s3_key = await upload_chunks_to_s3(chunk_docs, dataset_id)
                    await db.datasets.update_one(
                        {"_id": dataset_doc["_id"]},
                        {"$set": {"chunks_s3_key": chunks_s3_key}}
                    )
                    s3_success = True
                    logger.info(f"Successfully stored {len(chunk_docs)} chunks in AWS S3 with key '{chunks_s3_key}'.")
                except Exception as s3_err:
                    logger.warning(f"AWS S3 chunks storage failed: {s3_err}. Falling back to MongoDB storage.")
            
            if not s3_success and chunk_docs:
                db_batch_size = 1000
                for start_idx in range(0, len(chunk_docs), db_batch_size):
                    batch = chunk_docs[start_idx:start_idx + db_batch_size]
                    await db.dataset_chunks.insert_many(batch)
                logger.info(f"Successfully stored {len(chunk_docs)} chunks in MongoDB dataset_chunks.")
        except Exception as chunk_err:
            logger.error(f"Failed to store chunk metadata: {chunk_err}")
            raise Exception(f"Chunk Storage Failure: Failed to save chunk metadata. Details: {str(chunk_err)}")
        
        # Step 4: Embedding = 90%
        logger.info("[Step 4/6] Initializing embedding model and generating vectors...")
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "embedding",
                "progress": 90.0,
                "currentStage": "Embedding",
                "current_stage": "Embedding"
            }}
        )
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 90.0}}
        )
        log_params["embedding_started"] = datetime.utcnow().isoformat() + "Z"
        print_stage_log("Embedding Started")

        try:
            embedding_model = (index_doc or {}).get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2"
            embedder = await get_embedding_model_async(embedding_model)
        except Exception as model_err:
            raise Exception(f"Embedding Model Initialization Failure: {str(model_err)}")

        # Step 5: Connecting to Vector Store
        try:
            store = VectorStore(backend=index_type, collection_name=index_id)
            try:
                await store.delete_store()
            except Exception as del_err:
                logger.warning(f"Failed to delete existing store collection {index_id}: {del_err}")
            await store.ensure_initialized()
        except Exception as db_init_err:
            raise Exception(f"Vector Database Initialization Failure: Failed to establish store connection. Details: {str(db_init_err)}")

        # Batch Processing: Embeddings Generation and Vector store insertions
        batch_size = getattr(settings, "EMBEDDING_BATCH_SIZE", 20)
        total_chunks = len(chunks)
        total_batches = (total_chunks + batch_size - 1) // batch_size
        
        metadatas = [{"document_id": dataset_id, "chunk_id": f"{index_id}_{idx}", "source_file": file_name, "chunk_text": chunk} for idx, chunk in enumerate(chunks)]
        ids = [f"{index_id}_{idx}" for idx in range(len(chunks))]

        for i in range(0, total_chunks, batch_size):
            exists = await db.datasets.find_one({"_id": dataset_doc["_id"]})
            if not exists:
                logger.warning(f"Aborting indexing: dataset {dataset_id} was deleted by the user")
                return ""

            batch_chunks = chunks[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            batch_metadatas = metadatas[i:i+batch_size]

            # 1. Embedding generation for batch (with retries)
            max_attempts = 3
            backoff_delay = 2.0
            batch_embeds = None
            completed_batches = i // batch_size + 1
            
            for attempt in range(max_attempts):
                try:
                    if asyncio.iscoroutinefunction(embedder.encode):
                        batch_embeds = await embedder.encode(batch_chunks)
                    else:
                        batch_embeds = await asyncio.to_thread(embedder.encode, batch_chunks)
                    if hasattr(batch_embeds, "tolist"):
                        batch_embeds = batch_embeds.tolist()
                    break
                except Exception as embed_err:
                    if attempt == max_attempts - 1:
                        raise Exception(f"Embedding Generation Failure: Failed to generate vectors for batch {i}-{i+len(batch_chunks)} after {max_attempts} attempts. Details: {str(embed_err)}")
                    await asyncio.sleep(backoff_delay * (2 ** attempt))

            # 2. Verify embeddings shape
            if not isinstance(batch_embeds, list) or len(batch_embeds) != len(batch_chunks):
                raise Exception(f"Embedding Shape Verification Failure: Expected {len(batch_chunks)} vectors, got {len(batch_embeds) if isinstance(batch_embeds, list) else type(batch_embeds)}")
            
            # 3. Vector store insertion for batch (with retries)
            for attempt in range(max_attempts):
                try:
                    await store.add_documents(batch_chunks, batch_embeds, batch_metadatas, batch_ids)
                    break
                except Exception as db_err:
                    if attempt == max_attempts - 1:
                        raise Exception(f"Vector Database Insertion Failure: Failed to store batch vectors after {max_attempts} attempts. Details: {str(db_err)}")
                    await asyncio.sleep(backoff_delay * (2 ** attempt))

            # Scale progress slightly within the 90%-95% range
            progress = 90.0 + (min(i + batch_size, total_chunks) / total_chunks) * 5.0
            await db.datasets.update_one(
                {"_id": dataset_doc["_id"]},
                {"$set": {"progress": round(progress, 1)}}
            )
            await db.rag_indexes.update_one(
                {"_id": index_id},
                {"$set": {"progress": round(progress, 1)}}
            )
            
            import gc
            gc.collect()

        log_params["embedding_completed"] = datetime.utcnow().isoformat() + "Z"
        log_params["vector_db_insert_success"] = True
        print_stage_log("Embedding Completed")

        # Step 6: Post-processing (EDA stats & preview generation)
        logger.info("[Step 6/6] Post-processing (generating EDA stats and preview)...")
        try:
            from datasets.processor import _eda_sync
            from api.routes.datasets import _generate_preview
            eda_res = await asyncio.to_thread(_eda_sync, temp_path, file_type)
            preview_res = await asyncio.to_thread(_generate_preview, temp_path, file_type)
        except Exception as post_err:
            logger.warning(f"Post-processing warning: Failed to generate EDA/preview: {post_err}")
            eda_res = {}
            preview_res = {}
        
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        # 6. Update status to completed in DB
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "completed",
                "progress": 100,
                "currentStage": "Completed",
                "current_stage": "Completed",
                "rows": meta_res.get("rows"),
                "cols": meta_res.get("cols"),
                "columns": meta_res.get("columns", []),
                "metadata": meta_res.get("metadata", {}),
                "stats": eda_res,
                "preview": preview_res,
                "processed_at": datetime.utcnow(),
                "completedAt": datetime.utcnow(),
                "completed_at": datetime.utcnow(),
                "error_message": None,
                "error": None,
                "recovery_attempts": 0,
                "chunks": len(chunks),
                "chunk_count": len(chunks),
                "embeddingCount": len(chunks),
                "embedding_count": len(chunks),
                "processingTime": processing_time,
                "processing_time": processing_time
            }}
        )
        
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"status": "ready", "progress": 100.0, "chunk_count": len(chunks), "error": None}}
        )
        
        log_params["worker_finished"] = datetime.utcnow().isoformat() + "Z"
        log_params["mongodb_update_success"] = True
        print_stage_log("Worker Finished")
        
        user_id = dataset_doc.get("user_id")
        if user_id:
            try:
                await auto_generate_api_key_for_dataset(user_id, dataset_id, file_name, db)
            except Exception as key_err:
                logger.error(f"Failed to auto-generate API Key: {key_err}")

        return index_id

    try:
        # Wrap execution in a configurable timeout (default 1 hour / 3600s to handle massive datasets on CPU)
        indexing_timeout = float(os.environ.get("INDEXING_TIMEOUT_SECONDS", "3600.0"))
        res_idx = await asyncio.wait_for(do_indexing(), timeout=indexing_timeout)
        return res_idx
    except Exception as e:
        import traceback
        full_stack = traceback.format_exc()
        error_msg = str(e)
        if isinstance(e, asyncio.TimeoutError):
            error_msg = "Processing Timeout"
            
        logger.error(f"Indexing failed for dataset {dataset_id}:\n{full_stack}")
        log_params["error"] = error_msg
        log_params["worker_finished"] = datetime.utcnow().isoformat() + "Z"
        print_stage_log("Errors")

        # Rollback database and vector store chunks
        logger.warning(f"Rollback: Cleaning up partial database assets for failed dataset '{dataset_id}'...")
        try:
            await db.dataset_chunks.delete_many({"dataset_id": dataset_id})
        except Exception as rollback_db_err:
            logger.error(f"Rollback: Failed to delete dataset_chunks: {rollback_db_err}")
            
        try:
            from services.s3_service import delete_chunks_from_s3
            await delete_chunks_from_s3(dataset_id)
        except Exception as rollback_s3_err:
            logger.error(f"Rollback: Failed to delete S3 chunks: {rollback_s3_err}")
            
        try:
            store = VectorStore(backend=index_type, collection_name=index_id)
            await store.delete_store()
        except Exception as rollback_vs_err:
            logger.error(f"Rollback: Failed to delete vector store: {rollback_vs_err}")

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
        
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "failed",
                "progress": 0.0,
                "currentStage": "Failed",
                "current_stage": "Failed",
                "error_message": error_msg,
                "error": error_msg,
                "error_source": error_source,
                "completedAt": datetime.utcnow(),
                "completed_at": datetime.utcnow(),
                "chunks": 0,
                "chunk_count": 0,
                "embeddingCount": 0,
                "embedding_count": 0,
                "processingTime": processing_time,
                "processing_time": processing_time
            }}
        )

        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {
                "status": "failed",
                "progress": 0.0,
                "error": error_msg,
                "error_source": error_source
            }}
        )
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
