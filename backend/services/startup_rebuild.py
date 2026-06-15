import asyncio
import logging
from database import get_db
from auth.utils import get_id_query
from services.chroma_service import collection_is_empty

logger = logging.getLogger(__name__)

def dispatch_rebuild_task(dataset_id: str):
    """Always rebuild index locally since ChromaDB SQLite persistence is local to the web container."""
    logger.info(f"Startup recovery: Spawning local background task to rebuild index for dataset: {dataset_id}")
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
            
        dataset = await db.datasets.find_one({"_id": get_id_query(dataset_id)})
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

        # Clean up stale "building" indexes: reset them to "failed" with an explanation
        stale_indexes = await db.rag_indexes.update_many(
            {"status": "building"},
            {
                "$set": {
                    "status": "failed",
                    "progress": 0.0,
                    "error": "Index build was interrupted (server restart or memory limit exceeded)."
                }
            }
        )
        if stale_indexes.modified_count > 0:
            logger.info(f"Startup recovery: Cleaned up {stale_indexes.modified_count} stale 'building' indexes and set their status to 'failed'.")

        # Clean up stale "processing" datasets: reset them to "failed" with an explanation
        stale_datasets = await db.datasets.update_many(
            {"status": "processing"},
            {
                "$set": {
                    "status": "failed",
                    "error_message": "Dataset processing was interrupted (server restart or memory limit exceeded)."
                }
            }
        )
        if stale_datasets.modified_count > 0:
            logger.info(f"Startup recovery: Cleaned up {stale_datasets.modified_count} stale 'processing' datasets and set their status to 'failed'.")

        # Find all datasets with status 'indexed' or 'ready'
        rebuild_queue = []
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
                rebuild_queue.append(dataset_id)
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
                # Queue index rebuilding
                rebuild_queue.append(dataset_id)
            else:
                logger.info(f"Startup recovery: Dataset '{dataset.get('name') or dataset.get('file_name')}' index {index_id} is verified healthy.")
            
            # Cooperative yield to prevent event loop starvation
            await asyncio.sleep(0.1)

        # Dispatch sequential index rebuilding to prevent concurrent SQLite locks
        if rebuild_queue:
            logger.info(f"Startup recovery: Found {len(rebuild_queue)} empty vector stores to rebuild sequentially.")
            asyncio.create_task(run_sequential_rebuilds(rebuild_queue))
                
    except Exception as e:
        logger.error(f"Error during RAG startup recovery check: {e}")

async def run_sequential_rebuilds(dataset_ids: list):
    """Rebuild indexes sequentially with warm-up delay to prevent SQLite lock collisions."""
    logger.info(f"Sequential Rebuild: Waiting 20 seconds warm-up delay before starting {len(dataset_ids)} rebuilds...")
    await asyncio.sleep(20)
    
    db = get_db()
    if db is None:
        logger.error("Sequential Rebuild: Database connection not available.")
        return
        
    for dataset_id in dataset_ids:
        try:
            logger.info(f"Sequential Rebuild: Starting RAG index rebuilding for dataset {dataset_id}")
            dataset = await db.datasets.find_one({"_id": get_id_query(dataset_id)})
            if not dataset:
                logger.error(f"Sequential Rebuild: Dataset '{dataset_id}' not found in database.")
                continue
                
            # Trigger indexing
            from services.dataset_service import build_index_for_dataset
            await build_index_for_dataset(dataset, db)
            logger.info(f"Sequential Rebuild: Completed RAG index rebuild for dataset: {dataset_id}")
        except Exception as e:
            logger.error(f"Sequential Rebuild: Failed for dataset {dataset_id}: {e}")
        # Yield control between rebuilds to allow other event loop processes to run
        await asyncio.sleep(1.0)
