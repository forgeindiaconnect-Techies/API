from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from datetime import datetime
from typing import List, Optional
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
    return {
        "id": str(d["_id"]),
        "name": d["name"],
        "file_type": d["file_type"],
        "size_bytes": d.get("size_bytes", 0),
        "rows": d.get("rows"),
        "cols": d.get("cols"),
        "status": d.get("status", "pending"),
        "user_id": d.get("user_id", ""),
        "created_at": d.get("created_at", datetime.utcnow()),
        "processed_at": d.get("processed_at"),
        "metadata": d.get("metadata"),
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

    file_size = 0
    file_id = str(uuid.uuid4())
    user_dir = os.path.join(settings.UPLOAD_DIR, str(current_user["_id"]))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, f"{file_id}.{ext}")

    try:
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                    os.remove(file_path)
                    raise HTTPException(status_code=413, detail="File too large")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    doc = {
        "name": file.filename,
        "file_type": ext,
        "file_path": file_path,
        "file_id": file_id,
        "size_bytes": file_size,
        "status": "processing",
        "user_id": str(current_user["_id"]),
        "created_at": datetime.utcnow(),
    }

    result = await db.datasets.insert_one(doc)
    doc["_id"] = str(result.inserted_id)

    # Process in background
    background_tasks.add_task(
        _process_in_background,
        str(result.inserted_id),
        file_path,
        ext,
        db
    )

    return fmt_dataset(doc)


async def _process_in_background(dataset_id: str, file_path: str, ext: str, db):
    try:
        result = await process_dataset(file_path, ext)
        await db.datasets.update_one(
            {"_id": dataset_id},
            {"$set": {
                "status": "ready",
                "rows": result.get("rows"),
                "cols": result.get("cols"),
                "columns": result.get("columns", []),
                "metadata": result.get("metadata", {}),
                "processed_at": datetime.utcnow(),
            }}
        )
    except Exception as e:
        logger.error(f"Processing failed for {dataset_id}: {e}")
        await db.datasets.update_one(
            {"_id": dataset_id},
            {"$set": {"status": "error", "error_message": str(e)}}
        )


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    d = await db.datasets.find_one({"_id": dataset_id, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return fmt_dataset(d)


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    d = await db.datasets.find_one({"_id": dataset_id, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Delete file
    if os.path.exists(d.get("file_path", "")):
        os.remove(d["file_path"])

    await db.datasets.delete_one({"_id": dataset_id})
    return {"message": "Dataset deleted"}


@router.post("/{dataset_id}/process")
async def reprocess_dataset(
    dataset_id: str,
    options: ProcessingOptions,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    db = get_db()
    d = await db.datasets.find_one({"_id": dataset_id, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")

    await db.datasets.update_one({"_id": dataset_id}, {"$set": {"status": "processing"}})
    background_tasks.add_task(
        _process_in_background, dataset_id, d["file_path"], d["file_type"], db
    )
    return {"message": "Processing started"}


@router.get("/{dataset_id}/eda")
async def get_eda(dataset_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    d = await db.datasets.find_one({"_id": dataset_id, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if d.get("status") != "ready":
        raise HTTPException(status_code=400, detail="Dataset not processed yet")

    eda = await run_eda(d.get("file_path", ""), d.get("file_type", ""))
    return eda


@router.get("/{dataset_id}/preview")
async def get_preview(
    dataset_id: str,
    rows: int = 20,
    current_user=Depends(get_current_user)
):
    db = get_db()
    d = await db.datasets.find_one({"_id": dataset_id, "user_id": str(current_user["_id"])})
    if not d:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        import pandas as pd
        ext = d["file_type"]
        path = d.get("file_path", "")
        if not os.path.exists(path):
            return {"columns": [], "rows": []}

        if ext == "csv":
            df = pd.read_csv(path, nrows=rows)
        elif ext in ["xlsx", "xls"]:
            df = pd.read_excel(path, nrows=rows)
        else:
            return {"columns": [], "rows": [], "message": "Preview not available for this file type"}

        return {
            "columns": list(df.columns),
            "rows": df.fillna("").head(rows).to_dict("records")
        }
    except Exception as e:
        return {"columns": [], "rows": [], "error": str(e)}
