import asyncio
import os
import sys

# Add backend directory to path so we can import config/database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from database import connect_db, get_db
from bson import ObjectId

async def inspect_dataset():
    await connect_db()
    db = get_db()
    if db is None:
        print("Failed to connect to database.")
        return

    dataset_id = "6a31320941135333cd2aecd7"
    print(f"Querying dataset ID: {dataset_id}")
    
    # Try finding by ObjectId or string ID
    doc = await db.datasets.find_one({"_id": dataset_id})
    if not doc:
        try:
            doc = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
        except Exception:
            pass
            
    if doc:
        print("Dataset Document found:")
        for k, v in doc.items():
            print(f"  {k}: {v} (Type: {type(v).__name__})")
    else:
        print("Dataset Document NOT found in database.")

if __name__ == "__main__":
    asyncio.run(inspect_dataset())
