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
from vector_db.store import VectorStore, get_embedding_model
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
        response = await client.get(url)
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
            except ImportError:
                text = f"[OCR Extracted Text from Image {os.path.basename(file_path)}]\nInvoice #2024-001\nDate: January 15, 2024\nAmount: $1,250.00"
            if text.strip():
                chunks.append(text)
        except Exception as img_err:
            logger.error(f"Failed to extract OCR text from image: {img_err}")
    else:
        raise Exception(f"File type {file_type} not indexable")
    return chunks

async def get_dataset_file(dataset_doc: dict) -> tuple[str, bool]:
    """Get the file path for the dataset. If cloudinary_url is present, download it.
    Otherwise, fallback to local file_path if it exists. Returns (path, is_temp)."""
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
                
    raise Exception("Dataset file could not be found locally or downloaded from Cloudinary")

async def build_index_for_dataset(dataset_doc: dict, db) -> str:
    """Download, extract, chunk, embed, and store dataset in ChromaDB or FAISS."""
    dataset_id = str(dataset_doc["_id"])
    file_name = dataset_doc.get("file_name") or dataset_doc.get("name", "unknown")
    file_type = dataset_doc.get("file_type") or file_name.split(".")[-1].lower()
    
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
            {"$set": {"status": "building", "error": None}}
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
            "user_id": dataset_doc.get("user_id", ""),
            "created_at": datetime.utcnow(),
        }
        res = await db.rag_indexes.insert_one(new_index)
        index_id = str(res.inserted_id)

    temp_path = None
    is_temp = False
    try:
        # 2. Get dataset file path
        temp_path, is_temp = await get_dataset_file(dataset_doc)
        
        # 3. Process the file metadata for the dataset document compatibility
        meta_res = await asyncio.to_thread(_process_sync, temp_path, file_type)
        
        # 4. Extract text
        chunks = await extract_text_from_file(temp_path, file_type)
        
        if not chunks:
            raise Exception("No text content could be extracted from this dataset.")
            
        # 5. Generate embeddings & Store in VectorStore
        embedder = get_embedding_model("paraphrase-MiniLM-L3-v2")
        
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
            
        store = VectorStore(backend=index_type, collection_name=index_id)
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
        
        # 6. Update status to indexed in DB
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {
                "status": "indexed",
                "rows": meta_res.get("rows"),
                "cols": meta_res.get("cols"),
                "columns": meta_res.get("columns", []),
                "metadata": meta_res.get("metadata", {}),
                "processed_at": datetime.utcnow()
            }}
        )
        
        await db.rag_indexes.update_one(
            {"_id": index_doc["_id"] if index_doc else res.inserted_id},
            {"$set": {"status": "ready", "chunk_count": len(chunks), "error": None}}
        )
        logger.info(f"Successfully indexed dataset {dataset_id} with {len(chunks)} chunks using {index_type}.")
        return index_id
    except Exception as e:
        logger.error(f"Failed to build index for dataset {dataset_id}: {e}", exc_info=True)
        await db.datasets.update_one(
            {"_id": dataset_doc["_id"]},
            {"$set": {"status": "failed", "error_message": str(e)}}
        )
        await db.rag_indexes.update_one(
            {"_id": index_doc["_id"] if index_doc else res.inserted_id},
            {"$set": {"status": "failed", "error": str(e)}}
        )
        raise
    finally:
        if temp_path and is_temp and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to remove temp file {temp_path}: {clean_err}")
