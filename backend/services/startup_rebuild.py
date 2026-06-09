import asyncio
import logging
from database import get_db
from services.chroma_service import collection_is_empty

logger = logging.getLogger(__name__)

def dispatch_rebuild_task(dataset_id: str):
    """Attempt to dispatch the rebuild task to Celery, with a local fallback."""
    try:
        from workers.tasks import rebuild_dataset_index_task
        # Dispatch to Celery background task queue
        rebuild_dataset_index_task.delay(dataset_id)
        logger.info(f"Successfully dispatched rebuild task to Celery for dataset: {dataset_id}")
    except Exception as e:
        logger.warning(
            f"Could not dispatch rebuild to Celery ({e}). "
            f"Spawning delayed local background asyncio task instead..."
        )
        asyncio.create_task(run_rebuild_locally(dataset_id))

async def run_rebuild_locally(dataset_id: str):
    """Local fallback runner that executes rebuilding after a warm-up delay."""
    # Delay to ensure main thread has completed startup and server is healthy
    await asyncio.sleep(20)
    try:
        logger.info(f"Local Rebuild: Starting RAG index rebuilding for dataset: {dataset_id}")
        db = get_db()
        if db is None:
            logger.error("Local Rebuild: Database not connected. Aborting rebuild.")
            return
            
        dataset = await db.datasets.find_one({"_id": dataset_id})
        if not dataset:
            logger.error(f"Local Rebuild: Dataset '{dataset_id}' not found in database.")
            return

        # Trigger indexing
        from services.dataset_service import build_index_for_dataset
        await build_index_for_dataset(dataset, db)
        logger.info(f"Local Rebuild: Completed RAG index rebuild for dataset: {dataset_id}")
    except Exception as e:
        logger.error(f"Local Rebuild: Failed to rebuild index for dataset {dataset_id}: {e}")

async def run_startup_recovery():
    """Verify all datasets in database, and queue their vector store indexes rebuild if empty."""
    logger.info("Starting startup RAG index recovery checks...")
    try:
        db = get_db()
        if db is None:
            logger.warning("Database not connected, skipping startup RAG index recovery.")
            return

        # Find all datasets with status 'indexed' or 'ready'
        datasets_cursor = db.datasets.find({"status": {"$in": ["indexed", "ready"]}})
        async for dataset in datasets_cursor:
            dataset_id = str(dataset["_id"])
            
            # Skip legacy datasets that do not have a Cloudinary URL
            if not dataset.get("cloudinary_url"):
                logger.warning(
                    f"Startup recovery: Dataset '{dataset.get('name') or dataset.get('file_name')}' ({dataset_id}) "
                    f"does not have a Cloudinary URL. Skipping automated index rebuild."
                )
                continue

            # Find RAG index document
            index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
            if not index_doc:
                logger.info(f"No RAG index document found for dataset {dataset_id}. Queueing index rebuild...")
                dispatch_rebuild_task(dataset_id)
                continue
                
            index_id = str(index_doc["_id"])
            
            # Check if ChromaDB collection is empty
            is_empty = await collection_is_empty(index_id)
            if is_empty:
                logger.warning(
                    f"Startup recovery: RAG Index {index_id} for dataset '{dataset.get('name') or dataset.get('file_name')}' "
                    f"is empty in ChromaDB. Queueing download and rebuild from Cloudinary..."
                )
                # Clean up status in index document so search doesn't query a building index
                await db.rag_indexes.update_one(
                    {"_id": index_doc["_id"]},
                    {"$set": {"status": "building", "error": None}}
                )
                # Dispatch index rebuilding to task queue
                dispatch_rebuild_task(dataset_id)
            else:
                logger.info(f"Startup recovery: Dataset '{dataset.get('name') or dataset.get('file_name')}' index {index_id} is verified healthy.")
                
    except Exception as e:
        logger.error(f"Error during RAG startup recovery check: {e}")
