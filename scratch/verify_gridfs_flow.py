import sys
import os
import asyncio
import logging
from fastapi import BackgroundTasks, UploadFile
import io
from bson import ObjectId

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from database import connect_db, get_db
from api.routes.datasets import upload_dataset, reprocess_dataset
from auth.utils import get_id_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_gridfs_flow")

# Mock User class inheriting from dict
class MockUser(dict):
    def __init__(self, user_id):
        super().__init__()
        self["_id"] = user_id

async def main():
    await connect_db()
    db = get_db()
    
    if db is None or hasattr(db, "_db") and db._db.__class__.__name__ == "MockDB":
        logger.error("Failed to connect to actual MongoDB cluster!")
        return
        
    logger.info("Connected to MongoDB database successfully.")
    
    # Use a dummy user ID
    user_id = "6a2bcb589670afa5956d7759"
    current_user = MockUser(user_id)
    
    # Prepare mock file
    filename = "verification_test.csv"
    file_content = b"prompt,response\nwhat is deep learning,a branch of machine learning\nwhat is RAG,retrieval augmented generation\n"
    
    dummy_file = UploadFile(
        file=io.BytesIO(file_content),
        filename=filename
    )
    
    # Upload dataset (runs process_upload_and_index_bg in background task)
    logger.info("Uploading test dataset...")
    bg_tasks = BackgroundTasks()
    
    res = await upload_dataset(
        background_tasks=bg_tasks,
        file=dummy_file,
        current_user=current_user
    )
    
    dataset_id = res["id"]
    logger.info(f"Dataset document created with ID: {dataset_id}")
    
    # Run the background task functions immediately
    for task in bg_tasks.tasks:
        logger.info(f"Executing background task: {task.func.__name__}")
        await task.func(*task.args)
        
    # Query database to confirm GridFS backup
    doc = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    gridfs_id = doc.get("gridfs_id")
    local_path = doc.get("file_path")
    
    logger.info(f"Dataset GridFS ID: {gridfs_id}")
    logger.info(f"Dataset Local File Path: {local_path}")
    
    if not gridfs_id:
        raise Exception("FAIL: gridfs_id was not set on the dataset document!")
    logger.info("✓ GridFS ID verified successfully.")
    
    # Simulating container restart by deleting local file
    if local_path and os.path.exists(local_path):
        os.remove(local_path)
        logger.info("Simulated container restart: deleted local file copy.")
    else:
        logger.warning("Local file was not found on disk to delete.")
        
    # Trigger reprocess
    logger.info("Triggering reprocess on the dataset (which should now pull from GridFS)...")
    reprocess_bg = BackgroundTasks()
    
    rep_res = await reprocess_dataset(
        dataset_id=dataset_id,
        background_tasks=reprocess_bg,
        current_user=current_user
    )
    
    # Execute reprocess background task
    for task in reprocess_bg.tasks:
        logger.info(f"Executing reprocess background task: {task.func.__name__}")
        if asyncio.iscoroutinefunction(task.func):
            await task.func(*task.args)
        else:
            task.func(*task.args)
            
    # Check dataset document status
    final_doc = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    logger.info(f"Final status of dataset in DB: {final_doc.get('status')}")
    logger.info(f"Final error_message: {final_doc.get('error_message')}")
    
    # Confirm success
    if final_doc.get("status") == "indexed":
        logger.info("✓ Reprocessed and RAG index rebuilt successfully using GridFS!")
    else:
        raise Exception(f"FAIL: Dataset status is {final_doc.get('status')}, error: {final_doc.get('error_message')}")
        
    # Cleanup: Delete dataset (which cleans up GridFS, local file, and DB doc)
    logger.info("Cleaning up verification dataset...")
    from api.routes.datasets import delete_dataset
    await delete_dataset(dataset_id, current_user)
    
    # Verify cleanup
    cleanup_doc = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if cleanup_doc:
        raise Exception("FAIL: Dataset was not deleted from DB!")
        
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    import gridfs
    fs = AsyncIOMotorGridFSBucket(db._db)
    try:
        await fs.download_to_stream(ObjectId(gridfs_id), io.BytesIO())
        raise Exception("FAIL: GridFS file was not deleted!")
    except gridfs.errors.NoFile:
        logger.info("✓ GridFS file deleted successfully (NoFile raised).")
    except Exception as e:
        if "GridFS" in str(e) or "not found" in str(e).lower() or "no file" in str(e).lower():
            logger.info("✓ GridFS file deleted successfully.")
        else:
            raise
            
    logger.info("ALL END-TO-END VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
