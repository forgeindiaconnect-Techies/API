from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
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
        "status": "ready" if status in ("ready", "indexed") else status,
        "user_id": d.get("user_id", ""),
        "created_at": d.get("created_at", datetime.utcnow()),
        "processed_at": d.get("processed_at"),
        "metadata": d.get("metadata"),
        "error_message": d.get("error_message"),
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
    d = await db.datasets.find_one({"_id": id_query, "user_id": user_query})
    if not d:
        logger.warning(f"Dataset not found or unauthorized: ID={dataset_id}, User={current_user.get('_id')}")
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    logger.info(f"Successfully retrieved dataset: {d.get('name')} (ID: {d.get('_id')})")
    return d


@router.get("")
async def list_datasets(current_user=Depends(get_current_user)):
    db = get_db()
    if db is None:
        logger.error("list_datasets: Database connection wrapper is None")
        raise HTTPException(status_code=500, detail="Database connection unavailable")
    
    user_query = get_user_query(current_user)
    logger.info(f"list_datasets: querying datasets for user_query={user_query}")
    
    try:
        async def fetch_db_datasets():
            datasets = []
            async for d in db.datasets.find({"user_id": user_query}):
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

    def sort_key(x):
        val = x.get("created_at")
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.min

    try:
        return sorted(datasets, key=sort_key, reverse=True)
    except Exception as se:
        logger.error(f"Failed to sort datasets: {se}", exc_info=True)
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

    # 1. Read file bytes and verify size quickly
    try:
        file_bytes = await file.read()
        file_size = len(file_bytes)
    except Exception as e:
        logger.error(f"Failed to read upload file: {e}")
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    # 2. Write to local storage immediately to ensure background processing has a local file copy
    try:
        user_upload_dir = os.path.join(settings.UPLOAD_DIR, str(current_user["_id"]))
        os.makedirs(user_upload_dir, exist_ok=True)
        unique_id = str(uuid.uuid4())
        local_path = os.path.join(user_upload_dir, f"{unique_id}.{ext}")
        with open(local_path, "wb") as f:
            f.write(file_bytes)
        logger.info(f"Saved raw upload locally to: {local_path}")
    except Exception as e:
        logger.error(f"Failed to save temp file locally: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store file: {str(e)}")

    # 3. Create a pending dataset record in MongoDB
    doc = {
        "cloudinary_url": None,
        "public_id": None,
        "file_path": local_path,
        "file_name": file.filename,
        "name": file.filename,
        "file_type": ext,
        "size_bytes": file_size,
        "status": "pending",
        "user_id": str(current_user["_id"]),
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
    except Exception as e:
        logger.error(f"Failed to insert pending dataset document: {e}")
        if os.path.exists(local_path):
            os.remove(local_path)
        raise HTTPException(status_code=500, detail="Database insertion failed")

    # 4. Define background task for Cloudinary upload & RAG indexing
    async def process_upload_and_index_bg(dataset_doc: dict, file_content: bytes, filename: str, path: str):
        try:
            db_instance = get_db()
            
            # 1. Cloudinary upload
            cloudinary_res = None
            if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
                try:
                    logger.info(f"Background: Uploading {filename} to Cloudinary...")
                    from services.cloudinary_service import upload_file_to_cloudinary
                    cloudinary_res = await upload_file_to_cloudinary(file_content, filename)
                    logger.info("Background: Successfully uploaded dataset to Cloudinary.")
                except Exception as upload_err:
                    logger.warning(f"Background: Cloudinary upload failed: {upload_err}. Staying with local path.")

            # 2. GridFS upload (as a robust database persistence backup)
            gridfs_id = None
            try:
                logger.info(f"Background: Backing up {filename} to GridFS...")
                from services.dataset_service import upload_file_to_gridfs
                ext = filename.split(".")[-1].lower()
                content_type = "application/octet-stream"
                if ext == "txt":
                    content_type = "text/plain"
                elif ext == "csv":
                    content_type = "text/csv"
                elif ext == "pdf":
                    content_type = "application/pdf"
                elif ext == "json":
                    content_type = "application/json"
                
                gridfs_id = await upload_file_to_gridfs(file_content, filename, content_type)
            except Exception as gridfs_err:
                logger.error(f"Background: GridFS backup failed: {gridfs_err}")

            # Update DB document with Cloudinary URL and GridFS ID
            updates = {}
            if cloudinary_res:
                dataset_doc["cloudinary_url"] = cloudinary_res["url"]
                dataset_doc["public_id"] = cloudinary_res["public_id"]
                updates["cloudinary_url"] = cloudinary_res["url"]
                updates["public_id"] = cloudinary_res["public_id"]
                
            if gridfs_id:
                dataset_doc["gridfs_id"] = gridfs_id
                updates["gridfs_id"] = gridfs_id

            if updates:
                await db_instance.datasets.update_one(
                    {"_id": ObjectId(dataset_doc["_id"])},
                    {"$set": updates}
                )
            
            # Index the dataset
            from services.dataset_service import build_index_for_dataset
            await build_index_for_dataset(dataset_doc, db_instance)
        except Exception as bg_err:
            logger.error(f"Background upload processing failed for dataset {dataset_doc.get('_id')}: {bg_err}")
            db_instance = get_db()
            await db_instance.datasets.update_one(
                {"_id": ObjectId(dataset_doc["_id"])},
                {"$set": {"status": "failed", "error_message": f"Background processing failed: {str(bg_err)}"}}
            )

    background_tasks.add_task(
        process_upload_and_index_bg,
        doc,
        file_bytes,
        file.filename,
        local_path
    )

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

    # 3.5 Delete from GridFS
    gridfs_id = d.get("gridfs_id")
    if gridfs_id:
        try:
            from motor.motor_asyncio import AsyncIOMotorGridFSBucket
            fs = AsyncIOMotorGridFSBucket(db._db)
            await fs.delete(ObjectId(gridfs_id))
            logger.info(f"Deleted GridFS file {gridfs_id} for dataset {dataset_id}")
        except Exception as e:
            logger.error(f"Failed to delete GridFS file {gridfs_id}: {e}")

    # 4. Delete the dataset document from MongoDB
    await db.datasets.delete_one({"_id": d["_id"]})
    logger.info(f"Successfully deleted dataset document {dataset_id_str} from db.datasets")
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
    options: Optional[ProcessingOptions] = None,
    current_user=Depends(get_current_user),
):
    d = await fetch_user_dataset_or_raise(dataset_id, current_user)
    db = get_db()
    if db is None:
        logger.error("Database connection wrapper is None")
        raise HTTPException(status_code=500, detail="Database connection unavailable")
        
    await db.datasets.update_one({"_id": d["_id"]}, {"$set": {"status": "processing", "error_message": None}})
    
    # Reprocessing a failed/completed dataset should rebuild its RAG index as well to make it fully functional.
    from services.dataset_service import build_index_for_dataset
    background_tasks.add_task(build_index_for_dataset, d, db)
    
    # Return formatted info immediately with status 'processing'
    d["status"] = "processing"
    return fmt_dataset(d)



@router.get("/{dataset_id}/status")
async def get_dataset_status(
    dataset_id: str,
    current_user=Depends(get_current_user)
):
    d = await fetch_user_dataset_or_raise(dataset_id, current_user)
    
    # Progress estimation:
    # "completed" -> 100
    # "ready", "indexed" -> 100
    # "processing" -> 50
    # "failed", "error" -> 0
    # others -> 10
    status = d.get("status", "pending")
    progress = 0
    if status in ("completed", "ready", "indexed"):
        progress = 100
    elif status == "processing":
        progress = 50
    elif status in ("failed", "error"):
        progress = 0
    else:
        progress = 10
        
    return {
        "status": status,
        "progress": progress,
        "error_message": d.get("error_message")
    }


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
