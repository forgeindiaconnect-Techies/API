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
    
    dataset_id = "6a366cb07f339de977dc2248"
    print(f"Fetching dataset document for ID: {dataset_id}")
    d = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not d:
        print("Dataset not found!")
        return
        
    print("\n--- DATASET DOCUMENT ---")
    for k, v in d.items():
        print(f"  {k}: {v}")
            
    print("\n--- INDEXES ---")
    cursor = db.rag_indexes.find({"dataset_id": dataset_id})
    async for idx in cursor:
        for k, v in idx.items():
            print(f"  {k}: {v}")
        print("-" * 20)
        
    print("\n--- CHUNKS ---")
    chunk_count = await db.dataset_chunks.count_documents({"dataset_id": dataset_id})
    print(f"  Total chunks in MongoDB: {chunk_count}")

if __name__ == "__main__":
    asyncio.run(main())
