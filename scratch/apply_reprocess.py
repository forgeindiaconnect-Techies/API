import asyncio
import os
import sys
from datetime import datetime

# Add backend directory to sys.path so we can import modules
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db, get_db
from services.dataset_service import get_dataset_file
from datasets.processor import _process_sync, _eda_sync
from api.routes.datasets import _generate_preview
from bson import ObjectId

async def main():
    await connect_db()
    db = get_db()
    
    # Query the dataset document from DB
    d = await db.datasets.find_one({"_id": "6a2695fa1f1de9768349fdfe"})
    if not d:
        print("Dataset not found!")
        return
        
    print(f"Dataset current status: {d.get('status')}")
    
    temp_path = None
    is_temp = False
    try:
        temp_path, is_temp = await get_dataset_file(d)
        
        meta_res = _process_sync(temp_path, d.get("file_type", ""))
        eda_res = _eda_sync(temp_path, d.get("file_type", ""))
        preview_res = _generate_preview(temp_path, d.get("file_type", ""))
        
        rows = meta_res.get("rows")
        cols = meta_res.get("cols")
        columns = meta_res.get("columns", [])
        
        update_doc = {
            "status": "completed",
            "rows": rows,
            "cols": cols,
            "row_count": rows,
            "columns": columns,
            "stats": eda_res,
            "preview": preview_res,
            "processed_at": datetime.utcnow(),
            "error_message": None
        }
        
        await db.datasets.update_one({"_id": ObjectId("6a2695fa1f1de9768349fdfe")}, {"$set": update_doc})
        print("Successfully updated dataset status in DB to 'completed' with stats and preview!")
        
    except Exception as e:
        print("Failed to reprocess:", e)
    finally:
        if temp_path and is_temp and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(main())
