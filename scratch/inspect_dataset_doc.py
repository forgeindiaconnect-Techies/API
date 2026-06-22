import sys
import os
import asyncio
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add backend to path so we can import things
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db
from bson import ObjectId

async def main():
    print("Connecting to DB...")
    await connect_db()
    db = get_db()
    
    dataset_id = "6a362af6333372d856fbc413"
    print(f"Fetching dataset document for ID: {dataset_id}")
    d = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not d:
        print("Dataset not found!")
        return
        
    print("Dataset doc fields:")
    for k, v in d.items():
        if k not in ("stats", "preview"):
            print(f"  {k}: {v}")
            
    print("\n--- Simulating get_dataset_file ---")
    from services.dataset_service import get_dataset_file
    temp_path, is_temp = await get_dataset_file(d)
    print(f"File retrieved at: {temp_path} (is_temp: {is_temp})")
    
    try:
        from datasets.processor import _process_sync, _eda_sync
        from api.routes.datasets import _generate_preview
        
        print("\n--- Running _process_sync ---")
        meta_res = _process_sync(temp_path, d.get("file_type", ""))
        print(f"Metadata result: {meta_res}")
        
        print("\n--- Running _eda_sync ---")
        eda_res = _eda_sync(temp_path, d.get("file_type", ""))
        print(f"EDA result keys: {list(eda_res.keys())}")
        
        print("\n--- Running _generate_preview ---")
        preview_res = _generate_preview(temp_path, d.get("file_type", ""))
        print(f"Preview result columns: {preview_res.get('columns')}")
        print(f"Preview rows count: {len(preview_res.get('rows', []))}")
        
    except Exception as e:
        logger.exception(f"Error running processing steps:")
    finally:
        if temp_path and is_temp and os.path.exists(temp_path):
            os.remove(temp_path)
            print("Temp file cleaned up.")

if __name__ == "__main__":
    asyncio.run(main())
