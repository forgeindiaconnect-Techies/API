import asyncio
import os
import sys
import traceback
from datetime import datetime

# Add backend directory to sys.path so we can import modules
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db, get_db
from services.dataset_service import get_dataset_file
from datasets.processor import _process_sync, _eda_sync
from api.routes.datasets import _generate_preview

async def main():
    await connect_db()
    db = get_db()
    
    # Query the dataset document from DB
    d = await db.datasets.find_one({"_id": "6a2695fa1f1de9768349fdfe"})
    if not d:
        print("Dataset not found!")
        return
        
    print(f"Dataset name: {d.get('name')}, type: {d.get('file_type')}")
    
    temp_path = None
    is_temp = False
    try:
        print("1. Downloading/getting dataset file...")
        temp_path, is_temp = await get_dataset_file(d)
        print(f"File path: {temp_path}, is_temp: {is_temp}")
        
        print("2. Extracting metadata...")
        meta_res = _process_sync(temp_path, d.get("file_type", ""))
        print("Metadata extraction completed. Result rows:", meta_res.get("rows"))
        
        print("3. Generating EDA...")
        eda_res = _eda_sync(temp_path, d.get("file_type", ""))
        print("EDA generation completed. Word frequency count:", len(eda_res.get("word_frequency", {})))
        
        print("4. Generating preview...")
        preview_res = _generate_preview(temp_path, d.get("file_type", ""))
        print("Preview generation completed. Preview columns:", preview_res.get("columns"))
        
        print("All steps completed successfully!")
    except Exception as e:
        print("ERROR occurred during reprocessing:")
        traceback.print_exc()
    finally:
        if temp_path and is_temp and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print("Temp file cleaned up.")
            except Exception as e:
                print("Failed to clean up temp file:", e)

if __name__ == "__main__":
    asyncio.run(main())
