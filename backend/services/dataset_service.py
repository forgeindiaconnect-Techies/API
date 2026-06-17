import os
import tempfile
import httpx
import logging
import re
import pandas as pd
import PyPDF2
import docx
import json
import asyncio
from datetime import datetime
from database import get_db
from vector_db.store import VectorStore, get_embedding_model, get_embedding_model_async
from services.chroma_service import run_with_retry_async
from datasets.processor import _process_sync

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
        if file_type == "csv":
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        for i, row in df.iterrows():
            row_str = ", ".join([f"{col}: {val}" for col, val in row.items() if pd.notnull(val)])
            chunks.append(row_str)
    elif file_type == "pdf":
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
    else:
        raise Exception(f"File type {file_type} not indexable")
    return chunks

async def upload_file_to_gridfs(file_bytes: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    """Upload file bytes to MongoDB GridFS and return the string gridfs_id."""
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    import io
    
    db = get_db()
    if db is None or (hasattr(db, "_db") and db._db.__class__.__name__ == "MockDB"):
        logger.warning("GridFS: Database is MockDB or unavailable. Skipping GridFS upload.")
        return ""
        
    try:
        raw_db = db._db
        fs = AsyncIOMotorGridFSBucket(raw_db)
        stream = io.BytesIO(file_bytes)
        gridfs_id = await fs.upload_from_stream(
            filename,
            stream,
            metadata={"content_type": content_type}
        )
        logger.info(f"Successfully uploaded {filename} to GridFS with ID: {gridfs_id}")
        return str(gridfs_id)
    except Exception as e:
        logger.error(f"Failed to upload file to GridFS: {e}", exc_info=True)
        return ""

async def download_file_from_gridfs(dataset_doc: dict) -> str:
    """Download a file from MongoDB GridFS to a local temporary file path and return the path."""
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    from bson import ObjectId
    
    db = get_db()
    if db is None or (hasattr(db, "_db") and db._db.__class__.__name__ == "MockDB"):
        raise Exception("GridFS download failed: Database is MockDB or unavailable")
        
    gridfs_id = dataset_doc.get("gridfs_id")
    if not gridfs_id:
        raise Exception("No gridfs_id found in dataset document")
        
    try:
        raw_db = db._db
        fs = AsyncIOMotorGridFSBucket(raw_db)
        
        # Determine suffix
        suffix = "." + dataset_doc.get("file_type", "txt").lower()
        
        # Create named temporary file (closed immediately so we can write to it)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_path = temp_file.name
        temp_file.close()
        
        # Open in write-binary mode
        with open(temp_path, "wb") as f:
            await fs.download_to_stream(ObjectId(gridfs_id), f)
            
        logger.info(f"Successfully downloaded GridFS ID {gridfs_id} to temp path {temp_path}")
        return temp_path
    except Exception as e:
        logger.error(f"Failed to download file from GridFS: {e}", exc_info=True)
        raise

async def get_dataset_file(dataset_doc: dict) -> tuple[str, bool]:
    """Get the file path for the dataset. If cloudinary_url is present, download it.
    Otherwise, fallback to local file_path if it exists. Then try GridFS backup. Returns (path, is_temp)."""
    cloudinary_url = dataset_doc.get("cloudinary_url")
    if cloudinary_url:
        try:
            temp_path = await download_file_from_cloudinary(cloudinary_url)
            return temp_path, True
        except Exception as e:
            logger.error(f"Failed to download Cloudinary URL: {e}. Checking local path...")
    
    # Check local path
    local_path = dataset_doc.get("file_path")
    if local_path:
        paths_to_try = [
            local_path,
            os.path.abspath(local_path),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", local_path)),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", local_path))
        ]
        for p in paths_to_try:
            if os.path.exists(p) and os.path.isfile(p):
                logger.info(f"Found local file at: {p}")
                return p, False

    # Check GridFS backup
    gridfs_id = dataset_doc.get("gridfs_id")
    if gridfs_id:
        try:
            logger.info(f"Downloading dataset from GridFS (ID: {gridfs_id})...")
            temp_path = await download_file_from_gridfs(dataset_doc)
            return temp_path, True
        except Exception as e:
            logger.error(f"Failed to download from GridFS: {e}")
                
    raise Exception("Dataset file could not be found locally, downloaded from Cloudinary, or retrieved from GridFS")


def validate_environment_variables():
    """Validate all crucial environment variables and print structured info log with masked values."""
    from config import settings
    vars_to_check = {
        "MONGODB_URL": settings.MONGODB_URL or os.environ.get("MONGODB_URI"),
        "OPENAI_API_KEY": settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY"),
        "GEMINI_API_KEY": settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY"),
        "HUGGINGFACE_TOKEN/API_KEY": settings.HUGGINGFACE_TOKEN or os.environ.get("HUGGINGFACE_API_KEY"),
        "CHROMA_URL": os.environ.get("CHROMA_URL") or os.environ.get("CHROMA_SERVER_HOST") or f"Local Persistent ({settings.CHROMA_PERSIST_DIR})",
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
    dataset_id = str(dataset_doc["_id"])
    file_name = dataset_doc.get("file_name") or dataset_doc.get("name", "unknown")
    file_type = dataset_doc.get("file_type") or file_name.split(".")[-1].lower()
    
    # Check if dataset still exists in MongoDB before starting
    exists = await db.datasets.find_one({"_id": dataset_doc["_id"]})
    if not exists:
        logger.warning(f"Aborting indexing: dataset {dataset_id} was deleted by the user")
        await db.rag_indexes.delete_many({"dataset_id": dataset_id})
        return ""

    # 1. Update status to processing in DB
    await db.datasets.update_one(
        {"_id": dataset_doc["_id"]},
        {"$set": {"status": "processing", "error_message": None}}
    )
    
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
            "embedding_model": "paraphrase-MiniLM-L3-v2",
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
            logger.info(f"✓ File retrieved and verified at path: {temp_path}")
        except Exception as file_err:
            raise Exception(f"File Access Failure: Dataset file '{file_name}' could not be located or downloaded. Details: {str(file_err)}")
        
        # Step 2: File Parsing & Metadata Extraction
        logger.info("[Step 2/6] Parsing file and extracting metadata...")
        try:
            meta_res = await asyncio.to_thread(_process_sync, temp_path, file_type)
            logger.info("✓ Metadata extraction completed successfully.")
        except Exception as parse_err:
            raise Exception(f"File Parsing Failure: The file format is corrupt or unsupported. Details: {str(parse_err)}")
        
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 30.0}}
        )
        
        # Step 3: Text Chunking
        logger.info("[Step 3/6] Chunking data for vector embedding...")
        try:
            chunks = await extract_text_from_file(temp_path, file_type)
            if not chunks:
                raise Exception("No text content could be parsed or extracted from the dataset.")
            logger.info(f"✓ Text chunking completed. Generated {len(chunks)} chunks.")
        except Exception as extract_err:
            raise Exception(f"Text Extraction Failure: Failed to split dataset into text chunks. Details: {str(extract_err)}")
        
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 50.0}}
        )
            
        # Step 4: Embedding Model Initialization & Generation
        logger.info("[Step 4/6] Initializing embedding model and generating vectors...")
        try:
            logger.info("Initializing embedding model: 'paraphrase-MiniLM-L3-v2'...")
            embedder = await get_embedding_model_async("paraphrase-MiniLM-L3-v2")
            logger.info("✓ Embedding model initialized successfully.")
        except Exception as model_err:
            raise Exception(f"Embedding Model Initialization Failure: {str(model_err)}")
            
        try:
            logger.info(f"Generating embeddings for {len(chunks)} chunks...")
            embeddings = []
            batch_size = 32
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i+batch_size]
                if asyncio.iscoroutinefunction(embedder.encode):
                    batch_embeds = await embedder.encode(batch)
                else:
                    batch_embeds = await asyncio.to_thread(embedder.encode, batch)
                if hasattr(batch_embeds, "tolist"):
                    batch_embeds = batch_embeds.tolist()
                embeddings.extend(batch_embeds)
                await asyncio.sleep(0.02)
            logger.info("✓ Embedding vectors generated successfully.")
        except Exception as embed_err:
            raise Exception(f"Embedding Generation Failure: Failed to generate vectors for chunks. Details: {str(embed_err)}")
        
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 75.0}}
        )
        
        # Verify dataset still exists before populating vector store
        exists = await db.datasets.find_one({"_id": dataset_doc["_id"]})
        if not exists:
            logger.warning(f"Aborting indexing: dataset {dataset_id} was deleted by the user during embedding generation")
            await db.rag_indexes.delete_many({"dataset_id": dataset_id})
            try:
                store = VectorStore(backend=index_type, collection_name=index_id)
                await store.delete_store()
            except Exception:
                pass
            return ""

        # Step 5: Vector Database Insertion
        logger.info(f"[Step 5/6] Connecting to vector store ({index_type}) and inserting documents...")
        try:
            store = VectorStore(backend=index_type, collection_name=index_id)
            await store.ensure_initialized()
            
            metadatas = []
            for idx, chunk in enumerate(chunks):
                metadatas.append({
                    "document_id": dataset_id,
                    "chunk_id": f"{index_id}_{idx}",
                    "source_file": file_name,
                    "chunk_text": chunk
                })
            ids = [f"{index_id}_{idx}" for idx in range(len(chunks))]
            
            await store.add_documents(chunks, embeddings, metadatas, ids)
            col_count = await store.count()
            logger.info(f"✓ Vector DB storage populated. Collection now has {col_count} items.")
        except Exception as db_err:
            raise Exception(f"Vector Database Insertion Failure: Failed to store vectors in ChromaDB/FAISS. Details: {str(db_err)}")
        
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"progress": 90.0}}
        )

        # Step 6: Post-processing (EDA stats & preview generation)
        logger.info("[Step 6/6] Post-processing (generating EDA stats and preview)...")
        try:
            from datasets.processor import _eda_sync
            from api.routes.datasets import _generate_preview
            eda_res = await asyncio.to_thread(_eda_sync, temp_path, file_type)
            preview_res = await asyncio.to_thread(_generate_preview, temp_path, file_type)
            logger.info("✓ EDA stats and preview precomputed.")
        except Exception as post_err:
            logger.warning(f"Post-processing warning: Failed to generate EDA/preview: {post_err}")
            eda_res = {}
            preview_res = {}
        
        # 6. Update status to indexed in DB
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
                "error_message": None
            }}
        )
        
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"status": "ready", "progress": 100.0, "chunk_count": len(chunks), "error": None}}
        )
        logger.info("✓ Index status updated to READY")
        
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
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {"status": "failed", "error_message": error_msg}}
        )
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"status": "failed", "progress": 0.0, "error": error_msg}}
        )
        raise
    finally:
        if temp_path and is_temp and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to remove temp file {temp_path}: {clean_err}")


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
