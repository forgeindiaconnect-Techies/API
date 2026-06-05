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

    file_size = 0
    file_id = str(uuid.uuid4())

    try:
        from motor.motor_asyncio import AsyncIOMotorGridFSBucket
        fs = AsyncIOMotorGridFSBucket(db._db)
        grid_in = fs.open_upload_stream(file.filename)
        
        while chunk := await file.read(1024 * 1024):
            file_size += len(chunk)
            if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                await grid_in.abort()
                raise HTTPException(status_code=413, detail="File too large")
            await grid_in.write(chunk)
            
        await grid_in.close()
        gridfs_id = str(grid_in._id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    doc = {
        "name": file.filename,
        "file_type": ext,
        "file_path": f"./uploads/{file_id}.{ext}",
        "file_id": file_id,
        "gridfs_id": gridfs_id,
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
        doc["file_path"],
        ext,
        db
    )

    return fmt_dataset(doc)


async def _process_in_background(dataset_id: str, file_path: str, ext: str, db):
    temp_path = None
    try:
        dataset = await db.datasets.find_one({"_id": dataset_id})
        if not dataset:
            raise Exception("Dataset not found in DB")
            
        from api.routes.chat import download_file_from_gridfs
        temp_path = await download_file_from_gridfs(dataset)
        
        result = await process_dataset(temp_path, ext)
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
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to delete temp file {temp_path}: {clean_err}")


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

    # Delete local file fallback if it exists
    if os.path.exists(d.get("file_path", "")):
        try:
            os.remove(d["file_path"])
        except Exception:
            pass

    # Delete from GridFS bucket
    gridfs_id = d.get("gridfs_id")
    if gridfs_id:
        try:
            from motor.motor_asyncio import AsyncIOMotorGridFSBucket
            from bson import ObjectId
            fs = AsyncIOMotorGridFSBucket(db._db)
            await fs.delete(ObjectId(gridfs_id))
            logger.info(f"Deleted GridFS file {gridfs_id} for dataset {dataset_id}")
        except Exception as e:
            logger.error(f"Failed to delete GridFS file {gridfs_id}: {e}")

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

    temp_path = None
    try:
        from api.routes.chat import download_file_from_gridfs
        temp_path = await download_file_from_gridfs(d)
        eda = await run_eda(temp_path, d.get("file_type", ""))
        return eda
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                if d.get("gridfs_id") and str(d.get("gridfs_id")) in temp_path:
                    os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to delete temp file {temp_path}: {clean_err}")


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

    temp_path = None
    try:
        from api.routes.chat import download_file_from_gridfs
        temp_path = await download_file_from_gridfs(d)
        
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
        if temp_path and os.path.exists(temp_path):
            try:
                if d.get("gridfs_id") and str(d.get("gridfs_id")) in temp_path:
                    os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to delete temp file {temp_path}: {clean_err}")
