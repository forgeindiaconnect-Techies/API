import asyncio
import os
import sys
from bson import ObjectId

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db, get_db
from services.dataset_service import build_index_for_dataset

async def main():
    await connect_db()
    db = get_db()
    
    if db is None:
        print("Failed to connect to database!")
        return

    dataset_id = "6a312095a69ee21d5f5fb024"
    logger_msg = f"Fetching dataset document for ID: {dataset_id}"
    print(logger_msg)
    
    doc = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not doc:
        doc = await db.datasets.find_one({"_id": dataset_id})
        
    if not doc:
        print("Dataset document not found!")
        return
        
    print(f"Current status: {doc.get('status')}")
    print(f"Current error_message: {doc.get('error_message')}")
    
    print("\nTriggering build_index_for_dataset...")
    try:
        await build_index_for_dataset(doc, db)
    except Exception as e:
        print(f"\nCaught expected error: {e}")
        
    # Query database to confirm the new error message was stored
    updated_doc = await db.datasets.find_one({"_id": doc["_id"]})
    print("\nUpdated Dataset status in DB:", updated_doc.get("status"))
    print("Updated Dataset error_message in DB:", updated_doc.get("error_message"))
    
    if "File Recovery Failure" in str(updated_doc.get("error_message")):
        print("\n✓ SUCCESS: User-friendly recovery error message successfully populated in MongoDB!")
    else:
        print("\nFAIL: Updated error message did not contain expected explanation.")

if __name__ == "__main__":
    asyncio.run(main())
