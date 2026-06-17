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
logger = logging.getLogger("test_batch_processing")

# Mock User class
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
        
    logger.info("Connected to MongoDB successfully.")
    
    user_id = "6a2bcb589670afa5956d7759"
    current_user = MockUser(user_id)
    
    # Generate CSV with exactly 1018 text chunks
    logger.info("Generating a test CSV with exactly 1018 rows...")
    csv_header = "prompt,response\n"
    csv_rows = [f"prompt {i},response {i}" for i in range(1018)]
    csv_content = (csv_header + "\n".join(csv_rows)).encode("utf-8")
    
    filename = "large_batch_test.csv"
    dummy_file = UploadFile(
        file=io.BytesIO(csv_content),
        filename=filename
    )
    
    logger.info("Uploading dataset...")
    bg_tasks = BackgroundTasks()
    
    res = await upload_dataset(
        background_tasks=bg_tasks,
        file=dummy_file,
        current_user=current_user
    )
    
    dataset_id = res["id"]
    logger.info(f"Dataset created with ID: {dataset_id}")
    
    # Run background tasks (upload & indexing)
    logger.info("Running the background tasks (including batched embedding/indexing)...")
    for task in bg_tasks.tasks:
        logger.info(f"Executing task: {task.func.__name__}")
        await task.func(*task.args)
        
    # Check status and error message
    doc = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    status = doc.get("status")
    error_msg = doc.get("error_message")
    
    logger.info(f"Final status in DB: {status}")
    logger.info(f"Final error_message in DB: {error_msg}")
    
    if status == "indexed":
        logger.info("✓ SUCCESS: Dataset was processed and indexed successfully using batched flow!")
    else:
        logger.error(f"FAIL: Status is {status}. Error: {error_msg}")
        
    # Check item count in ChromaDB collection
    index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
    if index_doc:
        index_id = str(index_doc["_id"])
        from vector_db.store import VectorStore
        store = VectorStore(backend="chroma", collection_name=index_id)
        await store.ensure_initialized()
        count = await store.count()
        logger.info(f"ChromaDB verified collection count: {count} items.")
        if count == 1018:
            logger.info("✓ SUCCESS: ChromaDB contains exactly 1018 items!")
        else:
            logger.error(f"FAIL: Collection count is {count}, expected 1018.")
    
    # Cleanup
    logger.info("Cleaning up database, GridFS, and ChromaDB collection...")
    from api.routes.datasets import delete_dataset
    await delete_dataset(dataset_id, current_user)
    logger.info("Cleanup complete.")
    
    if status == "indexed" and count == 1018:
        logger.info("ALL BATCH PROCESSING VERIFICATION TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        logger.error("Some tests failed.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
