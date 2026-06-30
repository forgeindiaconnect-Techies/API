from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Body
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from bson.errors import InvalidId
import os, shutil, uuid, logging, asyncio

from models import DatasetResponse, ProcessingOptions, EDAResponse
from auth.utils import get_current_user, validate_object_id, get_id_query
from database import get_db
from config import settings
from datasets.processor import process_dataset, run_eda
from utils.cache import cache_get, cache_set, cache_clear_user

router = APIRouter(prefix="/datasets", tags=["Datasets"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {
    "csv", "xlsx", "xls", "pdf", "txt", "docx",
    "jpg", "jpeg", "png", "webp",
    "mp3", "wav", "m4a",
    "zip", "json"
}


def fmt_dataset(d: dict) -> dict:
    status = d.get("status", "pending")
    return {
        "id": str(d["_id"]),
        "name": d.get("name") or d.get("file_name", ""),
        "file_type": d.get("file_type") or d.get("file_name", "").split(".")[-1].lower() if d.get("file_name") else "txt",
        "size_bytes": d.get("size_bytes", 0),
        "rows": d.get("rows"),
        "cols": d.get("cols"),
        "status": "ready" if status in ("ready", "indexed", "completed") else status,
        "user_id": d.get("user_id", ""),
        "created_at": d.get("created_at", d.get("created_at", datetime.utcnow())),
        "processed_at": d.get("processed_at"),
        "metadata": d.get("metadata"),
        "error_message": d.get("error_message"),
        "chunk_count": d.get("chunk_count", 0),
        "embedding_count": d.get("embedding_count", 0),
        "processing_time": d.get("processing_time", 0.0),
    }


def get_user_query(current_user: dict) -> dict:
    user_id_str = str(current_user["_id"])
    if len(user_id_str) == 24:
        try:
            return {"$in": [user_id_str, ObjectId(user_id_str)]}
        except Exception:
            return user_id_str
    return user_id_str


async def fetch_user_dataset_or_raise(dataset_id: str, current_user: dict) -> dict:
    logger.info(f"Fetching dataset details for ID: {dataset_id} | User: {current_user.get('_id')}")
    
    id_query = get_id_query(dataset_id)

    db = get_db()
    if db is None:
        logger.error("Database connection wrapper is None")
        raise HTTPException(status_code=500, detail="Database connection unavailable")

    user_query = get_user_query(current_user)
    try:
        async def fetch_doc():
            return await db.datasets.find_one({"_id": id_query, "user_id": user_query})
            
        d = await asyncio.wait_for(fetch_doc(), timeout=4.0)
    except asyncio.TimeoutError:
        logger.error(f"Timeout (4s) exceeded while fetching dataset {dataset_id} for user: {current_user.get('_id')}")
        raise HTTPException(status_code=504, detail="Database query timed out. Please try again.")
    except Exception as e:
        logger.error(f"Database query failed in fetch_user_dataset_or_raise: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    if not d:
        logger.warning(f"Dataset not found or unauthorized: ID={dataset_id}, User={current_user.get('_id')}")
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    logger.info(f"Successfully retrieved dataset: {d.get('name')} (ID: {d.get('_id')})")
    return d


@router.get("")
async def list_datasets(
    limit: Optional[int] = None,
    skip: int = 0,
    current_user=Depends(get_current_user)
):
    user_id = str(current_user["_id"])
    cache_key = f"datasets:user:{user_id}:limit:{limit}:skip:{skip}"
    cached_val = await cache_get(cache_key)
    if cached_val is not None:
        return cached_val

    db = get_db()
    if db is None:
        logger.error("list_datasets: Database connection wrapper is None")
        raise HTTPException(status_code=500, detail="Database connection unavailable")
    
    user_query = get_user_query(current_user)
    logger.info(f"list_datasets: querying datasets for user_query={user_query}")
    
    try:
        async def fetch_db_datasets():
            datasets = []
            cursor = db.datasets.find({"user_id": user_query}).sort("created_at", -1)
            if skip > 0:
                cursor = cursor.skip(skip)
            if limit is not None:
                cursor = cursor.limit(limit)
            async for d in cursor:
                try:
                    datasets.append(fmt_dataset(d))
                except Exception as fe:
                    logger.error(f"Error formatting dataset document {d.get('_id')}: {fe}", exc_info=True)
                    continue
            return datasets

        # Wrap in a 4-second timeout to prevent API hangs
        datasets = await asyncio.wait_for(fetch_db_datasets(), timeout=4.0)
    except asyncio.TimeoutError:
        logger.error(f"Timeout (4s) exceeded while listing datasets for user: {current_user.get('_id')}")
        raise HTTPException(status_code=504, detail="Database query timed out. Please try again.")
    except Exception as e:
        logger.error(f"Failed to query datasets from MongoDB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    await cache_set(cache_key, datasets, ttl=300)
    return datasets


@router.post("/upload", status_code=202)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    db = get_db()
    if db is None:
        logger.error("upload_dataset: Database connection wrapper is None")
        raise HTTPException(status_code=500, detail="Database connection unavailable")

    ext = file.filename.split(".")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type .{ext} not supported")

    # 1. Stream write to local storage immediately in chunks to avoid loading all bytes in memory
    import hashlib
    import uuid
    
    unique_id = str(uuid.uuid4())
    user_upload_dir = os.path.join(settings.UPLOAD_DIR, str(current_user["_id"]))
    os.makedirs(user_upload_dir, exist_ok=True)
    local_path = os.path.join(user_upload_dir, f"{unique_id}.{ext}")
    
    sha256_hash = hashlib.sha256()
    file_size = 0
    chunk_size = 1024 * 1024  # 1MB chunk size
    
    try:
        logger.info(f"Starting streaming upload of file {file.filename} to local path {local_path}...")
        with open(local_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                    f.close()
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    logger.warning(f"File upload size {file_size} bytes exceeds limit {settings.MAX_UPLOAD_SIZE_MB}MB.")
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum upload size of {settings.MAX_UPLOAD_SIZE_MB}MB."
                    )
                f.write(chunk)
                sha256_hash.update(chunk)
                
        # Validate file existence on disk and size match
        if not os.path.exists(local_path) or not os.path.isfile(local_path) or os.path.getsize(local_path) != file_size:
            raise Exception("File stream write validation failed: File on disk is missing or size is inconsistent.")
            
        if file_size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
            
        logger.info(f"Successfully streamed upload locally: {local_path} ({file_size} bytes)")
        
        # 1.5. Validate CSV, Excel, ZIP, Text, Image, PDF, or DOCX files before processing
        if ext in ("csv", "txt", "md", "json"):
            with open(local_path, "rb") as f:
                header = f.read(1024)
                if b"\x00" in header:
                    raise HTTPException(status_code=400, detail="Invalid text file: Binary data detected.")
                    
        if ext == "csv":
            import pandas as pd
            validated = False
            for enc in ["utf-8", "latin-1", "utf-8-sig", "cp1252"]:
                try:
                    pd.read_csv(local_path, nrows=5, encoding=enc)
                    validated = True
                    break
                except Exception:
                    continue
            if not validated:
                try:
                    pd.read_csv(local_path, nrows=5)
                except Exception as csv_err:
                    raise HTTPException(status_code=400, detail=f"Invalid or corrupt CSV file: {str(csv_err)}")
        elif ext in ("xlsx", "xls"):
            import pandas as pd
            try:
                pd.read_excel(local_path, nrows=5)
            except Exception as excel_err:
                raise HTTPException(status_code=400, detail=f"Invalid or corrupt Excel file: {str(excel_err)}")
        elif ext == "zip":
            import zipfile
            if not zipfile.is_zipfile(local_path):
                raise HTTPException(status_code=400, detail="Invalid or corrupt ZIP archive.")
            try:
                with zipfile.ZipFile(local_path, "r") as zf:
                    bad_file = zf.testzip()
                    if bad_file is not None:
                        raise Exception(f"First corrupt file inside zip: {bad_file}")
            except Exception as zip_err:
                raise HTTPException(status_code=400, detail=f"Corrupt or invalid ZIP archive: {str(zip_err)}")
        elif ext in ("jpg", "jpeg", "png", "webp"):
            from PIL import Image
            try:
                with Image.open(local_path) as img:
                    img.verify()
                with Image.open(local_path) as img:
                    img.load()
            except Exception as img_err:
                raise HTTPException(status_code=400, detail=f"Corrupt or invalid Image file: {str(img_err)}")
        elif ext == "pdf":
            import PyPDF2
            try:
                with open(local_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    if len(reader.pages) == 0:
                        raise Exception("PDF file has 0 pages.")
                    _ = reader.pages[0].extract_text()
            except Exception as pdf_err:
                raise HTTPException(status_code=400, detail=f"Corrupt or invalid PDF file: {str(pdf_err)}")
        elif ext == "docx":
            from docx import Document
            try:
                Document(local_path)
            except Exception as docx_err:
                raise HTTPException(status_code=400, detail=f"Corrupt or invalid DOCX file: {str(docx_err)}")
                
    except HTTPException:
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
        raise
    except Exception as e:
        logger.error(f"Failed to stream and validate file locally: {e}", exc_info=True)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to store file on server: {str(e)}")

    file_hash = sha256_hash.hexdigest()
    user_id_str = str(current_user["_id"])
    
    # 2. Check for duplicate upload
    duplicate = await db.datasets.find_one({"file_hash": file_hash, "user_id": user_id_str})
    if duplicate:
        logger.info(f"Duplicate upload detected: User {user_id_str} uploaded file '{file.filename}' which already exists as ID {duplicate['_id']}")
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
        raise HTTPException(status_code=409, detail="This file has already been uploaded.")

    # 3. Create a dataset record in MongoDB (initially with only local_path)
    doc = {
        "cloudinary_url": None,
        "secure_url": None,
        "public_id": None,
        "gridfs_id": None,
        "s3_key": None,
        "s3_url": None,
        "file_path": local_path,
        "file_name": file.filename,
        "name": file.filename,
        "file_type": ext,
        "size_bytes": file_size,
        "file_hash": file_hash,
        "status": "uploaded",
        "user_id": user_id_str,
        "created_at": datetime.utcnow(),
    }

    try:
        result = await db.datasets.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        doc["dataset_id"] = str(result.inserted_id)
        
        await db.datasets.update_one(
            {"_id": result.inserted_id},
            {"$set": {"dataset_id": str(result.inserted_id)}}
        )
        logger.info(f"Successfully created dataset document in MongoDB: {doc['_id']} with status 'processing'")
    except Exception as e:
        logger.error(f"Failed to insert dataset document: {e}", exc_info=True)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail="Database insertion failed")

    # 4. Immediately upload file to AWS S3 BEFORE returning response.
    #    This guarantees the file survives a server restart.
    try:
        # Read the freshly saved local file once for S3 upload
        with open(local_path, "rb") as fh:
            file_bytes = fh.read()

        content_type_map = {
            "txt": "text/plain", "csv": "text/csv", "pdf": "application/pdf",
            "json": "application/json", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "zip": "application/zip", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp", "mp3": "audio/mpeg", "wav": "audio/wav",
        }
        content_type = content_type_map.get(ext, "application/octet-stream")

        # --- S3 upload (Mandatory) ---
        from services.s3_service import upload_file_to_s3
        import time
        timestamp = int(time.time())
        
        logger.info(f"Upload: Staging file for S3 upload: {file.filename}")
        s3_res = await upload_file_to_s3(file_bytes, file.filename, doc["_id"], content_type, timestamp)
        
        if not s3_res.get("s3_key"):
            raise Exception("S3 upload failed: s3_key is empty.")
            
        s3_key = s3_res["s3_key"]
        s3_url = s3_res.get("s3_url")
        logger.info(f"Upload: AWS S3 upload succeeded: key={s3_key}")
        
        # --- Cloudinary upload (Optional Backup) ---
        cloudinary_url = None
        public_id = None
        if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
            try:
                from services.cloudinary_service import upload_file_to_cloudinary
                cl_res = await upload_file_to_cloudinary(file_bytes, file.filename)
                cloudinary_url = cl_res.get("secure_url") or cl_res.get("url")
                public_id = cl_res.get("public_id")
            except Exception as cl_err:
                logger.warning(f"Upload: Cloudinary backup failed: {cl_err}")

        # 4.5 Save S3 info and required camelCase + snake_case metadata to MongoDB dataset document
        update_data = {
            "s3_key": s3_key,
            "s3_url": s3_url,
            "secure_url": s3_url if not cloudinary_url else cloudinary_url,
            "cloudinary_url": cloudinary_url,
            "public_id": public_id,
            # Required camelCase fields:
            "fileName": file.filename,
            "s3Key": s3_key,
            "s3Url": s3_url,
            "mimeType": content_type,
            "size": file_size,
            "userId": user_id_str,
            "datasetId": doc["_id"],
            "uploadedAt": datetime.utcnow()
        }
        
        await db.datasets.update_one(
            {"_id": result.inserted_id},
            {"$set": update_data}
        )
        doc.update(update_data)
        logger.info(f"Upload: S3 metadata successfully saved to MongoDB for dataset {doc['_id']}")
        
    except Exception as upload_err:
        logger.error(f"Upload: AWS S3 upload failed for dataset {doc['_id']}: {upload_err}", exc_info=True)
        # Cleanup local file on failure
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
        # Delete dataset doc if upload failed to avoid orphan/broken datasets
        try:
            await db.datasets.delete_one({"_id": result.inserted_id})
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"AWS S3 upload failed: {str(upload_err)}. Verify AWS credentials and S3_BUCKET."
        )

    # 5. Queue indexing task (Try Celery first, fallback to FastAPI BackgroundTasks)
    redis_available = False
    if settings.REDIS_URL:
        try:
            import redis
            client = redis.from_url(settings.REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5)
            client.ping()
            redis_available = True
        except Exception as redis_err:
            logger.warning(f"Redis is not available: {redis_err}. Fallback to BackgroundTasks.")
            
    if redis_available:
        try:
            from workers.tasks import rebuild_dataset_index_task
            rebuild_dataset_index_task.delay(doc["_id"])
            logger.info(f"Queued initial indexing task via Celery for dataset {doc['_id']}")
        except Exception as celery_err:
            logger.warning(f"Failed to queue task via Celery: {celery_err}. Falling back to FastAPI BackgroundTasks.")
            from services.dataset_service import build_index_for_dataset
            background_tasks.add_task(build_index_for_dataset, doc, db)
    else:
        from services.dataset_service import build_index_for_dataset
        background_tasks.add_task(build_index_for_dataset, doc, db)

    await cache_clear_user(user_id_str)
    return fmt_dataset(doc)


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, current_user=Depends(get_current_user)):
    d = await fetch_user_dataset_or_raise(dataset_id, current_user)
    return fmt_dataset(d)


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str, current_user=Depends(get_current_user)):
    d = await fetch_user_dataset_or_raise(dataset_id, current_user)
    db = get_db()
    if db is None:
        logger.error("Database connection wrapper is None")
        raise HTTPException(status_code=500, detail="Database connection unavailable")

    dataset_id_str = str(d["_id"])

    # 1. Clean up associated RAG indexes and vector stores (ChromaDB/FAISS)
    try:
        from vector_db.store import VectorStore
        # Find all RAG indexes for this dataset
        async for idx in db.rag_indexes.find({"dataset_id": dataset_id_str}):
            index_id = str(idx["_id"])
            index_type = idx.get("index_type", "chroma")
            logger.info(f"Cleaning up vector store collection for RAG index {index_id} of type {index_type}")
            try:
                store = VectorStore(backend=index_type, collection_name=index_id)
                await store.delete_store()
            except Exception as ve:
                logger.error(f"Failed to delete vector store '{index_id}': {ve}")

        # Delete all RAG index documents from MongoDB
        del_indexes_res = await db.rag_indexes.delete_many({"dataset_id": dataset_id_str})
        logger.info(f"Deleted {del_indexes_res.deleted_count} RAG index documents from MongoDB for dataset {dataset_id_str}")
    except Exception as ie:
        logger.error(f"Error occurred during RAG index/vector store cleanup for dataset {dataset_id_str}: {ie}")

    # 2. Delete raw local file from disk
    local_path = d.get("file_path")
    if local_path:
        try:
            paths_to_try = [
                local_path,
                os.path.abspath(local_path),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", local_path)),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", local_path))
            ]
            for p in paths_to_try:
                if os.path.exists(p) and os.path.isfile(p):
                    os.remove(p)
                    logger.info(f"Deleted local file at: {p}")
                    break
        except Exception as fe:
            logger.error(f"Failed to delete local file '{local_path}': {fe}")

    # 3. Delete from Cloudinary
    public_id = d.get("public_id")
    if public_id:
        try:
            import cloudinary.uploader
            ext = d.get("file_type", "")
            resource_type = "image" if ext in ("jpg", "jpeg", "png", "webp", "gif") else "raw"
            cloudinary.uploader.destroy(public_id, resource_type=resource_type)
            logger.info(f"Deleted Cloudinary file {public_id} for dataset {dataset_id}")
        except Exception as e:
            logger.error(f"Failed to delete Cloudinary file {public_id}: {e}")

    # 3.5 (GridFS cleanup — no longer used for new uploads, skip deletion)

    # 3.6 Delete from AWS S3
    s3_key = d.get("s3_key")
    if s3_key:
        try:
            from services.s3_service import delete_file_from_s3
            await delete_file_from_s3(s3_key)
            logger.info(f"Deleted AWS S3 file {s3_key} for dataset {dataset_id}")
        except Exception as e:
            logger.error(f"Failed to delete AWS S3 file {s3_key}: {e}")

    # 3.7 Delete chunks from AWS S3
    try:
        from services.s3_service import delete_chunks_from_s3
        await delete_chunks_from_s3(dataset_id_str)
        logger.info(f"Deleted AWS S3 chunks for dataset {dataset_id}")
    except Exception as e:
        logger.error(f"Failed to delete AWS S3 chunks for dataset {dataset_id}: {e}")

    # 4. Delete the dataset document from MongoDB
    await db.datasets.delete_one({"_id": d["_id"]})
    logger.info(f"Successfully deleted dataset document {dataset_id_str} from db.datasets")
    await cache_clear_user(str(current_user["_id"]))
    return {"message": "Dataset and all associated indexes/files deleted successfully"}


def _generate_preview(temp_path: str, ext: str, rows: int = 20) -> dict:
    try:
        import pandas as pd
        if not os.path.exists(temp_path):
            return {"columns": [], "rows": []}

        if ext == "csv":
            df = None
            for enc in ["utf-8", "latin-1", "utf-8-sig", "cp1252"]:
                try:
                    df = pd.read_csv(temp_path, nrows=rows, encoding=enc)
                    break
                except Exception:
                    continue
            if df is None:
                df = pd.read_csv(temp_path, nrows=rows)
            return {
                "columns": list(df.columns),
                "rows": df.fillna("").head(rows).to_dict("records")
            }
        elif ext in ["xlsx", "xls"]:
            df = pd.read_excel(temp_path, nrows=rows)
            return {
                "columns": list(df.columns),
                "rows": df.fillna("").head(rows).to_dict("records")
            }
        elif ext in ["txt", "md"]:
            lines = []
            with open(temp_path, "r", encoding="utf-8", errors="ignore") as f:
                for i in range(rows):
                    line = f.readline()
                    if not line:
                        break
                    lines.append({"Line": i + 1, "Content": line.strip()})
            return {
                "columns": ["Line", "Content"],
                "rows": lines
            }
        elif ext == "pdf":
            import PyPDF2
            pages = []
            with open(temp_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = min(len(reader.pages), rows)
                for page_num in range(num_pages):
                    text = reader.pages[page_num].extract_text()
                    pages.append({
                        "Page": page_num + 1,
                        "Content": text[:1000] + "..." if text and len(text) > 1000 else (text or "")
                    })
            return {
                "columns": ["Page", "Content"],
                "rows": pages
            }
        elif ext == "json":
            import json
            with open(temp_path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            if isinstance(data, list):
                if data and isinstance(data[0], dict):
                    df = pd.DataFrame(data[:rows])
                    return {
                        "columns": list(df.columns),
                        "rows": df.fillna("").to_dict("records")
                    }
                else:
                    return {
                        "columns": ["Value"],
                        "rows": [{"Value": str(item)} for item in data[:rows]]
                    }
            elif isinstance(data, dict):
                return {
                    "columns": ["Key", "Value"],
                    "rows": [{"Key": k, "Value": str(v)} for k, v in list(data.items())[:rows]]
                }
            else:
                return {
                    "columns": ["Value"],
                    "rows": [{"Value": str(data)}]
                }
        else:
            return {"columns": [], "rows": [], "message": f"Preview not available for file type .{ext}"}
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        return {"columns": [], "rows": [], "error": str(e)}


@router.post("/{dataset_id}/process")
async def reprocess_dataset(
    dataset_id: str,
    background_tasks: BackgroundTasks,
    options: Optional[ProcessingOptions] = Body(None),
    current_user=Depends(get_current_user),
):
    d = await fetch_user_dataset_or_raise(dataset_id, current_user)
    db = get_db()
    if db is None:
        logger.error("Database connection wrapper is None")
        raise HTTPException(status_code=500, detail="Database connection unavailable")
        
    await db.datasets.update_one(
        {"_id": d["_id"]},
        {"$set": {
            "status": "processing",
            "error_message": None,
            "recovery_attempts": 0
        }}
    )
    
    # Reprocessing a failed/completed dataset should rebuild its RAG index as well to make it fully functional.
    redis_available = False
    if settings.REDIS_URL:
        try:
            import redis
            client = redis.from_url(settings.REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5)
            client.ping()
            redis_available = True
        except Exception as redis_err:
            logger.warning(f"Redis is not available: {redis_err}. Fallback to BackgroundTasks.")
            
    if redis_available:
        try:
            from workers.tasks import rebuild_dataset_index_task
            rebuild_dataset_index_task.delay(str(d["_id"]))
            logger.info(f"Queued reprocess indexing task via Celery for dataset {d['_id']}")
        except Exception as celery_err:
            logger.warning(f"Failed to queue task via Celery: {celery_err}. Falling back to FastAPI BackgroundTasks.")
            from services.dataset_service import build_index_for_dataset
            background_tasks.add_task(build_index_for_dataset, d, db)
    else:
        from services.dataset_service import build_index_for_dataset
        background_tasks.add_task(build_index_for_dataset, d, db)
    
    await cache_clear_user(str(current_user["_id"]))
    # Return formatted info immediately with status 'processing'
    d["status"] = "processing"
    return fmt_dataset(d)



@router.get("/{dataset_id}/status")
async def get_dataset_status(
    dataset_id: str,
    current_user=Depends(get_current_user)
):
    logger.info(f"Checking dataset status: {dataset_id}")
    
    mongodb_connected = False
    chromadb_connected = False
    
    # 1. Verify MongoDB Connection with a strict 2-second timeout
    db = get_db()
    if db is not None:
        try:
            await asyncio.wait_for(db.command("ping"), timeout=2.0)
            mongodb_connected = True
        except Exception as db_err:
            logger.warning(f"MongoDB connection check failed: {db_err}")
            
    # 2. Verify ChromaDB Connection with a strict 2-second timeout
    try:
        from services.chroma_service import ChromaManager
        async def check_chroma():
            chroma_client = await asyncio.to_thread(ChromaManager.get_client)
            if chroma_client is not None:
                await asyncio.to_thread(chroma_client.heartbeat)
                return True
            return False
        chromadb_connected = await asyncio.wait_for(check_chroma(), timeout=2.0)
    except Exception as chroma_err:
        logger.warning(f"ChromaDB connection check failed: {chroma_err}")
        chromadb_connected = False

    # If MongoDB is down, we cannot fetch dataset document. We return a clean JSON response instead of 500.
    if not mongodb_connected:
        return {
            "status": "error",
            "progress": 0,
            "error_message": "MongoDB connection unavailable",
            "mongodb_connected": False,
            "chromadb_connected": chromadb_connected
        }

    try:
        # Fetch dataset record
        d = await fetch_user_dataset_or_raise(dataset_id, current_user)
    except HTTPException as he:
        # Let standard HTTPExceptions (like 404 Not Found) pass through
        raise he
    except Exception as e:
        logger.error(f"Error fetching dataset for status endpoint: {e}", exc_info=True)
        return {
            "status": "error",
            "progress": 0,
            "error_message": f"Failed to fetch dataset record: {str(e)}",
            "mongodb_connected": mongodb_connected,
            "chromadb_connected": chromadb_connected
        }

    # Query the indexing job document
    index_doc = None
    try:
        async def fetch_index():
            return await db.rag_indexes.find_one({"dataset_id": dataset_id})
        index_doc = await asyncio.wait_for(fetch_index(), timeout=2.0)
    except Exception as index_err:
        logger.warning(f"Failed to fetch rag index document: {index_err}")

    status = d.get("status", "pending")
    progress = 0
    error_message = d.get("error_message")
    error_source = d.get("error_source") or "UNKNOWN"

    # Timeout check: if the status is active and elapsed time > 10 minutes, fail the dataset
    if status in ("uploaded", "saved", "reading_file", "preprocessing", "chunking", "embedding", "embedded", "processing"):
        created_at = d.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:
                    created_at = None
            if created_at:
                elapsed = (datetime.utcnow() - created_at).total_seconds()
                if elapsed > 600:  # 10 minutes
                    timeout_msg = "Processing Timeout"
                    status = "failed"
                    error_message = timeout_msg
                    error_source = "UNKNOWN"
                    # Update database records so it stops polling and shows failure permanently
                    try:
                        await db.datasets.update_one(
                            {"_id": d["_id"]},
                            {"$set": {
                                "status": "failed",
                                "progress": 0.0,
                                "error_message": timeout_msg,
                                "error": timeout_msg,
                                "error_source": "UNKNOWN"
                            }}
                        )
                        await db.rag_indexes.update_many(
                            {"dataset_id": dataset_id},
                            {"$set": {
                                "status": "failed",
                                "progress": 0.0,
                                "error": timeout_msg,
                                "error_source": "UNKNOWN"
                            }}
                        )
                    except Exception as upd_err:
                        logger.error(f"Failed to update timed out dataset: {upd_err}")

    if index_doc:
        index_status = index_doc.get("status")
        index_progress = index_doc.get("progress", 0.0)
        index_error = index_doc.get("error")

        if status in ("processing", "preprocessing", "uploaded", "saved", "reading_file", "chunking", "extracted", "embedding", "embedded"):
            progress = index_progress if index_progress is not None else 50
            if index_status == "failed":
                status = "failed"
                error_message = index_error or "Background indexing task failed."
                error_source = index_doc.get("error_source") or error_source
        elif status in ("completed", "ready", "indexed") or index_status == "ready":
            progress = 100
        elif status in ("failed", "error") or index_status == "failed":
            progress = 0
            status = "failed"
            error_message = error_message or index_error or "Indexing task failed."
            error_source = index_doc.get("error_source") or error_source
    else:
        if status in ("completed", "ready", "indexed"):
            progress = 100
        elif status in ("processing", "preprocessing", "uploaded", "saved", "reading_file", "chunking", "extracted", "embedding", "embedded"):
            progress = 50
        elif status in ("failed", "error"):
            progress = 0
            status = "failed"
        else:
            progress = 10

    # Map status to stage label
    stage_map = {
        "uploaded": "Uploaded",
        "saved": "Saved",
        "reading_file": "Reading File",
        "preprocessing": "Preprocessing",
        "chunking": "Chunking",
        "embedding": "Embedding",
        "embedded": "Embedded",
        "completed": "Completed",
        "ready": "Completed",
        "indexed": "Completed",
        "failed": "Failed",
        "error": "Failed",
        "processing": "Processing"
    }
    current_stage = d.get("current_stage") or d.get("currentStage") or stage_map.get(status, status.replace("_", " ").title())

    # Calculate elapsed time
    elapsed_time = 0.0
    started_at = d.get("startedAt") or d.get("started_at") or d.get("created_at")
    if started_at:
        if isinstance(started_at, str):
            try:
                started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            except Exception:
                started_at = None
        if started_at:
            completed_at = d.get("completedAt") or d.get("completed_at")
            if completed_at:
                if isinstance(completed_at, str):
                    try:
                        completed_at = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                    except Exception:
                        completed_at = None
            if completed_at:
                elapsed_time = (completed_at - started_at).total_seconds()
            else:
                now = datetime.utcnow()
                if started_at.tzinfo is not None:
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                elapsed_time = (now - started_at).total_seconds()

    # Calculate estimated remaining time
    estimated_time_remaining = 0.0
    if progress > 0 and progress < 100:
        estimated_time_remaining = (elapsed_time / progress) * (100 - progress)

    # Determine error source if failed
    if status == "failed":
        if error_source not in ("LOCAL", "CLOUDINARY", "AWS_S3", "GRIDFS", "UNKNOWN"):
            err_msg_lower = (error_message or "").lower()
            if "cloudinary" in err_msg_lower:
                error_source = "CLOUDINARY"
            elif "s3" in err_msg_lower:
                error_source = "AWS_S3"
            elif "gridfs" in err_msg_lower:
                error_source = "GRIDFS"
            elif "local" in err_msg_lower:
                error_source = "LOCAL"
            else:
                error_source = "UNKNOWN"

    response_data = {
        "datasetId": dataset_id,
        "dataset_id": dataset_id,
        "status": status,
        "progress": progress,
        "currentStage": current_stage,
        "current_stage": current_stage,
        "rows": d.get("rows"),
        "cols": d.get("cols"),
        "chunks": d.get("chunks") or d.get("chunk_count", 0),
        "chunk_count": d.get("chunks") or d.get("chunk_count", 0),
        "elapsedTime": round(elapsed_time, 2) if elapsed_time else 0.0,
        "elapsed_time": round(elapsed_time, 2) if elapsed_time else 0.0,
        "estimatedTimeRemaining": round(estimated_time_remaining, 2) if estimated_time_remaining else 0.0,
        "estimated_time_remaining": round(estimated_time_remaining, 2) if estimated_time_remaining else 0.0,
        "error": error_message,
        "error_message": error_message,
        "mongodb_connected": mongodb_connected,
        "chromadb_connected": chromadb_connected,
        "embedding_count": d.get("embedding_count") or d.get("embeddingCount", 0),
        "processing_time": d.get("processing_time") or d.get("processingTime", 0.0),
    }

    if status == "failed":
        response_data.update({
            "error_source": error_source,
            "recovery_attempts": ["local", "cloudinary", "s3", "gridfs"]
        })

    return response_data


@router.get("/{dataset_id}/eda")
async def get_eda(dataset_id: str, current_user=Depends(get_current_user)):
    d = await fetch_user_dataset_or_raise(dataset_id, current_user)
    
    # Return pre-computed stats if available
    if d.get("stats"):
        return d["stats"]
        
    if d.get("status") not in ("ready", "indexed", "completed"):
        raise HTTPException(status_code=400, detail="Dataset not processed yet")

    temp_path = None
    is_temp = False
    try:
        from services.dataset_service import get_dataset_file
        temp_path, is_temp = await get_dataset_file(d)
        eda = await run_eda(temp_path, d.get("file_type", ""))
        return eda
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and is_temp and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to delete temp file {temp_path}: {clean_err}")


@router.get("/{dataset_id}/preview")
async def get_preview(
    dataset_id: str,
    rows: int = 20,
    current_user=Depends(get_current_user)
):
    d = await fetch_user_dataset_or_raise(dataset_id, current_user)
    
    # Return pre-computed preview if available
    if d.get("preview"):
        preview_data = d["preview"]
        if "rows" in preview_data and isinstance(preview_data["rows"], list):
            return {
                "columns": preview_data.get("columns", []),
                "rows": preview_data["rows"][:rows]
            }
        return preview_data

    temp_path = None
    is_temp = False
    try:
        from services.dataset_service import get_dataset_file
        temp_path, is_temp = await get_dataset_file(d)
        return _generate_preview(temp_path, d.get("file_type", ""), rows)
    except Exception as e:
        return {"columns": [], "rows": [], "error": str(e)}
    finally:
        if temp_path and is_temp and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to delete temp file {temp_path}: {clean_err}")


@router.get("/{dataset_id}/download")
async def download_preprocessed_dataset(
    dataset_id: str,
    current_user=Depends(get_current_user)
):
    d = await fetch_user_dataset_or_raise(dataset_id, current_user)
    
    # 1. Check if S3 key is available (either preprocessed_s3_key or s3_key)
    preprocessed_s3_key = d.get("preprocessed_s3_key") or d.get("preprocessedS3Key")
    if preprocessed_s3_key:
        from fastapi.responses import StreamingResponse
        from services.s3_service import get_s3_object_stream
        try:
            stream = await get_s3_object_stream(preprocessed_s3_key)
            
            async def stream_s3():
                def _read_chunk():
                    return stream.read(256 * 1024) # 256KB chunk
                while True:
                    chunk = await asyncio.to_thread(_read_chunk)
                    if not chunk:
                        break
                    yield chunk
                    
            return StreamingResponse(
                stream_s3(),
                media_type="application/zip",
                headers={"Content-Disposition": f"attachment; filename=preprocessed_{d.get('name', 'dataset.zip')}"}
            )
        except Exception as e:
            logger.error(f"Failed to stream preprocessed ZIP from S3 key '{preprocessed_s3_key}': {e}")
            raise HTTPException(status_code=500, detail=f"S3 download failed: {str(e)}")

    # 2. (GridFS fallback removed — GridFS is deprecated, skip to local fallback)

    # 3. Fallback to local preprocessed file if any
    local_path = d.get("preprocessed_zip_path") or d.get("file_path")
    if local_path and os.path.exists(local_path):
        from fastapi.responses import FileResponse
        return FileResponse(
            local_path,
            media_type="application/zip",
            filename=f"preprocessed_{d.get('name', 'dataset.zip')}"
        )
        
    raise HTTPException(status_code=404, detail="Preprocessed ZIP file not found.")
