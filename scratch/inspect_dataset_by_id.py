import asyncio
import os
import sys
from bson import ObjectId

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db, get_db

async def main():
    await connect_db()
    db = get_db()
    
    # Query by ObjectId or string ID
    dataset_id = "6a312095a69ee21d5f5fb024"
    d = None
    try:
        d = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    except Exception:
        pass
    
    if not d:
        d = await db.datasets.find_one({"_id": dataset_id})
        
    if not d:
        print("Dataset not found by ObjectId or string!")
        # Let's list the latest datasets
        print("\nLast 5 datasets in db:")
        async for item in db.datasets.find().sort("created_at", -1).limit(5):
            print(f"ID: {item['_id']}, Name: {item.get('name')}, Status: {item.get('status')}, Error: {item.get('error_message')}")
        return
        
    print("Full Dataset Document:")
    for k, v in d.items():
        if k not in ["preview", "stats"]:
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: [length/size: {len(str(v))}]")

if __name__ == "__main__":
    asyncio.run(main())
