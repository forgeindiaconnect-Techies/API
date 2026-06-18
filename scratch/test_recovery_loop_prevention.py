import os
import sys
import asyncio
import logging
from bson import ObjectId
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_recovery_loop_prevention")

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ["MONGODB_URL"] = "mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0"
os.environ["MONGODB_DB_NAME"] = "personal_ai_studio"

from database import connect_db, get_db
from services.startup_rebuild import run_startup_recovery

async def main():
    logger.info("=== STARTING RECOVERY LOOP PREVENTION TEST ===")
    await connect_db()
    db = get_db()
    if not db:
        logger.error("Failed to connect to DB.")
        return

    test_name = "test_loop_prevention_dataset.csv"
    test_filepath = f"uploads/{test_name}"
    
    # 1. Insert a mock dataset document with 2 recovery attempts already registered
    dataset_doc = {
        "name": test_name,
        "file_name": test_name,
        "file_path": test_filepath,
        "file_type": "csv",
        "size": 100,
        "status": "processing",
        "recovery_attempts": 2, # Exceeds or meets threshold (>= 2)
        "gridfs_id": "6a326c66a92e442a38f061da", # Dummy backup exists so it would normally queue
        "created_at": datetime.utcnow(),
    }
    
    insert_res = await db.datasets.insert_one(dataset_doc)
    dataset_id = str(insert_res.inserted_id)
    logger.info(f"Inserted mock dataset with ID: {dataset_id}, recovery_attempts: 2")

    # 2. Trigger run_startup_recovery()
    logger.info("Triggering run_startup_recovery()...")
    await run_startup_recovery()
    
    # 3. Retrieve document and check status
    updated_doc = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    status = updated_doc.get("status")
    err_msg = updated_doc.get("error_message") or ""
    
    logger.info(f"Final status: {status}")
    logger.info(f"Final error message: {err_msg}")
    
    # Assertions
    assert status == "failed", f"Expected status 'failed', got '{status}'"
    assert "repeatedly" in err_msg.lower() or "loop" in err_msg.lower() or "limits" in err_msg.lower(), f"Unexpected error message: {err_msg}"
    
    logger.info("✓ Success! Recovery loop prevention works as expected.")
    
    # Cleanup
    await db.datasets.delete_one({"_id": ObjectId(dataset_id)})
    await db.rag_indexes.delete_many({"dataset_id": dataset_id})
    logger.info("Cleaned up database test records.")
    logger.info("=== TEST PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
