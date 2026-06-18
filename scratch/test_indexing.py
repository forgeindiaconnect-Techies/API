import asyncio
import os
import sys
import traceback

# Add backend directory to sys.path so we can import modules
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db, get_db
from services.dataset_service import build_index_for_dataset

async def main():
    await connect_db()
    db = get_db()
    
    # Fetch the dataset and index we saw in the database
    dataset = await db.datasets.find_one({"_id": "6a2695fa1f1de9768349fdfe"})
    if not dataset:
        print("Dataset not found in DB!")
        return
        
    print(f"Running build_index_for_dataset for dataset: {dataset['name']}")
    try:
        index_id = await build_index_for_dataset(dataset, db)
        print(f"Indexing completed successfully! Index ID: {index_id}")
    except Exception as e:
        print(f"Indexing failed with exception: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
