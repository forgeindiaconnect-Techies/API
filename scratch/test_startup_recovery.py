import os
import sys
import asyncio
import logging
from bson import ObjectId
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_startup_recovery")

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ["MONGODB_URL"] = "mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0"
os.environ["MONGODB_DB_NAME"] = "personal_ai_studio"

from database import connect_db, get_db
from config import settings
from services.startup_rebuild import run_startup_recovery
from services.dataset_service import upload_file_to_gridfs, get_dataset_file
from services.chroma_service import collection_is_empty
from vector_db.store import VectorStore

async def main():
    logger.info("=== STARTING ROBUST STARTUP RECOVERY TEST ===")
    await connect_db()
    db = get_db()
    if not db:
        logger.error("Failed to connect to DB.")
        return

    test_name = "test_recovery_interrupted"
    test_filename = "test_recovery_interrupted.csv"
    test_filepath = f"uploads/{test_filename}"

    # Clean up previous test runs
    logger.info("Cleaning up previous test data...")
    # Delete test dataset and associated indexes
    cursor = db.datasets.find({"name": test_name})
    async for dataset in cursor:
        dataset_id = str(dataset["_id"])
        logger.info(f"Removing dataset {dataset_id}")
        
        # Get index ID to clean up chroma collection
        index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
        if index_doc:
            index_id = str(index_doc["_id"])
            try:
                store = VectorStore(backend="chroma", collection_name=index_id)
                await store.ensure_initialized()
                await store.delete_store()
                logger.info(f"Deleted collection {index_id} from Chroma")
            except Exception as e:
                logger.warning(f"Could not delete collection from Chroma: {e}")
                
        await db.datasets.delete_one({"_id": dataset["_id"]})
        await db.rag_indexes.delete_many({"dataset_id": dataset_id})

    # Remove local file if it exists in uploads directory
    local_abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", test_filepath))
    if os.path.exists(local_abs_path):
        os.remove(local_abs_path)
        logger.info(f"Removed local file at {local_abs_path}")

    # 1. Upload dummy file content to GridFS
    dummy_csv_content = b"id,text\n1,Artificial Intelligence and Machine Learning are growing rapidly.\n2,Retrieval Augmented Generation helps LLMs query custom datasets.\n3,FastAPI combined with MongoDB and ChromaDB provides a solid stack for AI APIs.\n"
    gridfs_id = await upload_file_to_gridfs(dummy_csv_content, test_filename, "text/csv")
    if not gridfs_id:
        logger.error("Failed to upload dummy file to GridFS.")
        return
    logger.info(f"Uploaded dummy file to GridFS, ID: {gridfs_id}")

    # 2. Create simulated interrupted dataset document with status 'processing'
    dataset_doc = {
        "name": test_name,
        "file_name": test_filename,
        "file_path": test_filepath,
        "file_type": "csv",
        "size": len(dummy_csv_content),
        "status": "processing",
        "gridfs_id": gridfs_id,
        "created_at": datetime.utcnow(),
    }
    
    insert_res = await db.datasets.insert_one(dataset_doc)
    dataset_id = str(insert_res.inserted_id)
    logger.info(f"Inserted dummy dataset with ID: {dataset_id} and status: 'processing'")

    # 3. Verify that the local file does not exist (forcing GridFS recovery fallback)
    assert not os.path.exists(local_abs_path), "Local file should not exist, to verify GridFS fallback recovery works!"

    # 4. Trigger run_startup_recovery()
    logger.info("Triggering run_startup_recovery()...")
    await run_startup_recovery()

    # 5. Poll the database and wait for indexing to complete (status should change to 'indexed')
    # Because sequential rebuild waits 20 seconds warm-up, we poll for up to 120 seconds.
    logger.info("Waiting for automatic recovery and index rebuilding to complete...")
    success = False
    for attempt in range(120):
        await asyncio.sleep(1)
        updated_dataset = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
        if not updated_dataset:
            logger.error("Dataset document went missing during processing!")
            break
        status = updated_dataset.get("status")
        err_msg = updated_dataset.get("error_message")
        
        # Check index document too
        index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
        index_status = index_doc.get("status") if index_doc else "missing"
        progress = index_doc.get("progress") if index_doc else 0.0
        
        if status == "indexed" and index_status == "ready":
            logger.info(f"✓ Success! Dataset status: {status}, Index status: {index_status}, Progress: {progress}%")
            success = True
            break
        elif status == "failed" or index_status == "failed":
            logger.error(f"✗ Rebuild failed! Dataset status: {status}, Index status: {index_status}, Error: {err_msg or (index_doc.get('error') if index_doc else '')}")
            break
        else:
            if attempt % 5 == 0:
                logger.info(f"Polled status: Dataset: {status}, Index: {index_status} (Progress: {progress}%)")

    # 6. Verify that vectors are actually present in ChromaDB
    if success:
        # Get index_id to check count in vector store
        try:
            index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
            if index_doc:
                index_id = str(index_doc["_id"])
                store = VectorStore(backend="chroma", collection_name=index_id)
                await store.ensure_initialized()
                count = await store.count()
                logger.info(f"✓ Verified collection count: {count} chunks present in vector store.")
                if count > 0:
                    logger.info("=== TEST PASSED SUCCESSFULLY ===")
                else:
                    logger.error("Test failed: Collection count is 0.")
            else:
                logger.error("Test failed: No RAG index document found after successful run.")
        except Exception as e:
            logger.error(f"Failed to query ChromaDB collection: {e}")
    else:
        logger.error("=== TEST FAILED ===")

    # 7. Cleanup after test
    logger.info("Cleaning up test records from database...")
    index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
    if index_doc:
        index_id = str(index_doc["_id"])
        try:
            store = VectorStore(backend="chroma", collection_name=index_id)
            await store.ensure_initialized()
            await store.delete_store()
            logger.info(f"Deleted test ChromaDB collection {index_id}.")
        except Exception as e:
            logger.warning(f"Could not delete collection from Chroma: {e}")
            
    await db.datasets.delete_one({"_id": ObjectId(dataset_id)})
    await db.rag_indexes.delete_many({"dataset_id": dataset_id})

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
