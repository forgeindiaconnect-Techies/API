from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from bson.errors import InvalidId
import os, shutil, uuid, logging

from models import DatasetResponse, ProcessingOptions, EDAResponse
from auth.utils import get_current_user
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


@router.get("")
async def list_datasets(current_user=Depends(get_current_user)):
    db = get_db()
    datasets = []
    async for d in db.datasets.find({"user_id": str(current_user["_id"])}):
        datasets.append(fmt_dataset(d))
    return sorted(datasets, key=lambda x: x["created_at"], reverse=True)


@router.post("/upload")
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    db = get_db()
    ext = file.filename.split(".")[-1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type .{ext} not supported")

    try:
        file_bytes = await file.read()
        file_size = len(file_bytes)
        
        if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large")
            
        cloudinary_res = None
        file_path = None

        # Try to upload to Cloudinary if keys are fully configured
        if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
            try:
                from services.cloudinary_service import upload_file_to_cloudinary
                cloudinary_res = await upload_file_to_cloudinary(file_bytes, file.filename)
                logger.info("Successfully uploaded dataset to Cloudinary.")
            except Exception as e:
                logger.warning(f"Cloudinary upload failed: {e}. Falling back to local storage.")

        # If Cloudinary is not configured or upload failed, save locally
        if not cloudinary_res:
            user_upload_dir = os.path.join(settings.UPLOAD_DIR, str(current_user["_id"]))
            os.makedirs(user_upload_dir, exist_ok=True)
            unique_id = str(uuid.uuid4())
            file_path = os.path.join(user_upload_dir, f"{unique_id}.{ext}")
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            logger.info(f"Saved dataset locally to: {file_path}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dataset upload storage failed: {e}")
        raise HTTPException(status_code=500, detail=f"Dataset storage failed: {str(e)}")

    doc = {
        "cloudinary_url": cloudinary_res["url"] if cloudinary_res else None,
        "public_id": cloudinary_res["public_id"] if cloudinary_res else None,
        "file_path": file_path,
        "file_name": file.filename,
        "name": file.filename,
        "file_type": ext,
        "size_bytes": file_size,
        "status": "processing",
        "user_id": str(current_user["_id"]),
        "created_at": datetime.utcnow(),
    }

    result = await db.datasets.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    doc["dataset_id"] = str(result.inserted_id)
    
    await db.datasets.update_one(
        {"_id": result.inserted_id},
        {"$set": {"dataset_id": str(result.inserted_id)}}
    )

    from services.dataset_service import build_index_for_dataset
    background_tasks.add_task(
        build_index_for_dataset,
        doc,
        db
    )

    return fmt_dataset(doc)


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, current_user=Depends(get_current_user)):
    try:
        oid = ObjectId(dataset_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid dataset ID format: {dataset_id}")
    db = get_db()
    d = await db.datasets.find_one({"_id": oid, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return fmt_dataset(d)


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str, current_user=Depends(get_current_user)):
    try:
        oid = ObjectId(dataset_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid dataset ID format: {dataset_id}")
    db = get_db()
    d = await db.datasets.find_one({"_id": oid, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Delete from Cloudinary
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

    await db.datasets.delete_one({"_id": oid})
    return {"message": "Dataset deleted"}


@router.post("/{dataset_id}/process")
async def reprocess_dataset(
    dataset_id: str,
    options: ProcessingOptions,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    try:
        oid = ObjectId(dataset_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid dataset ID format: {dataset_id}")
    db = get_db()
    d = await db.datasets.find_one({"_id": oid, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")

    await db.datasets.update_one({"_id": oid}, {"$set": {"status": "processing"}})
    from services.dataset_service import build_index_for_dataset
    background_tasks.add_task(
        build_index_for_dataset, d, db
    )
    return {"message": "Processing started"}


@router.get("/{dataset_id}/eda")
async def get_eda(dataset_id: str, current_user=Depends(get_current_user)):
    try:
        oid = ObjectId(dataset_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid dataset ID format: {dataset_id}")
    db = get_db()
    d = await db.datasets.find_one({"_id": oid, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if d.get("status") not in ("ready", "indexed"):
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
    try:
        oid = ObjectId(dataset_id)
    except (InvalidId, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid dataset ID format: {dataset_id}")
    db = get_db()
    d = await db.datasets.find_one({"_id": oid, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")

    temp_path = None
    is_temp = False
    try:
        from services.dataset_service import get_dataset_file
        temp_path, is_temp = await get_dataset_file(d)
        
        import pandas as pd
        ext = d["file_type"]
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
        return {"columns": [], "rows": [], "error": str(e)}
    finally:
        if temp_path and is_temp and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to delete temp file {temp_path}: {clean_err}")
