import asyncio
import logging
from datetime import datetime
from database import get_db
from auth.utils import get_id_query
from services.chroma_service import collection_is_empty

logger = logging.getLogger(__name__)

# In-process cache to prevent infinite RAG index rebuild loops
_rebuilt_datasets = set()

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
    """Verify all datasets in database, and queue their vector store indexes rebuild if empty or interrupted."""
    logger.info("Starting startup RAG index recovery checks...")
    try:
        db = get_db()
        if db is None:
            logger.warning("Database not connected, skipping startup RAG index recovery.")
            return

        rebuild_queue = []

        # 1. Check for stale "processing" status datasets
        stale_datasets_cursor = db.datasets.find({"status": "processing"})
        async for dataset in stale_datasets_cursor:
            dataset_id = str(dataset["_id"])
            dataset_name = dataset.get('name') or dataset.get('file_name') or 'unknown'
            
            # Check if dataset has any backup
            has_backup = bool(dataset.get("cloudinary_url") or dataset.get("secure_url") or dataset.get("gridfs_id"))
            
            if has_backup:
                recovery_attempts = dataset.get("recovery_attempts", 0)
                if recovery_attempts >= 2:
                    logger.error(
                        f"Startup recovery: Dataset '{dataset_name}' ({dataset_id}) has failed recovery "
                        f"{recovery_attempts} times. Marking as failed to prevent infinite crash loop."
                    )
                    await db.datasets.update_one(
                        {"_id": dataset["_id"]},
                        {"$set": {
                            "status": "failed",
                            "error_message": "Dataset processing failed repeatedly due to container resource limits (OOM/CPU timeout)."
                        }}
                    )
                    # Also mark index as failed if it exists
                    await db.rag_indexes.update_many(
                        {"dataset_id": dataset_id},
                        {"$set": {
                            "status": "failed",
                            "progress": 0.0,
                            "error": "Dataset processing failed repeatedly due to container resource limits."
                        }}
                    )
                    continue

                logger.info(
                    f"Startup recovery: Dataset '{dataset_name}' ({dataset_id}) was interrupted in 'processing' "
                    f"status, but has backup. Queueing for automatic reprocessing (Attempt {recovery_attempts + 1})."
                )
                
                # Reset dataset to "processing", increment recovery_attempts
                await db.datasets.update_one(
                    {"_id": dataset["_id"]},
                    {
                        "$set": {"status": "processing", "error_message": None},
                        "$inc": {"recovery_attempts": 1}
                    }
                )
                
                # Update or create RAG index document
                index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
                if index_doc:
                    await db.rag_indexes.update_one(
                        {"_id": index_doc["_id"]},
                        {"$set": {"status": "building", "progress": 10.0, "error": None}}
                    )
                else:
                    file_name = dataset.get("file_name") or dataset.get("name", "unknown")
                    file_type = dataset.get("file_type") or file_name.split(".")[-1].lower()
                    new_index = {
                        "name": f"{file_name} index",
                        "dataset_id": dataset_id,
                        "embedding_model": "paraphrase-MiniLM-L3-v2",
                        "chunk_size": 500 if file_type in ("txt", "md", "docx") else 512,
                        "chunk_overlap": 100 if file_type in ("txt", "md", "docx") else 50,
                        "index_type": "chroma",
                        "chunk_count": 0,
                        "status": "building",
                        "progress": 10.0,
                        "user_id": dataset.get("user_id", ""),
                        "created_at": datetime.utcnow(),
                    }
                    await db.rag_indexes.insert_one(new_index)
                
                rebuild_queue.append(dataset_id)
            else:
                logger.warning(
                    f"Startup recovery: Dataset '{dataset_name}' ({dataset_id}) was interrupted in 'processing' "
                    f"status, but does not have any backup. Marking as failed."
                )
                await db.datasets.update_one(
                    {"_id": dataset["_id"]},
                    {"$set": {
                        "status": "failed",
                        "error_message": "Dataset processing was interrupted (server restart or memory limit exceeded) and no backup was found."
                    }}
                )
                
                # Also mark index as failed if it exists
                await db.rag_indexes.update_many(
                    {"dataset_id": dataset_id},
                    {"$set": {
                        "status": "failed",
                        "progress": 0.0,
                        "error": "Dataset processing was interrupted and no backup was found."
                    }}
                )

        # 2. Check for stale "building" indexes for other datasets
        stale_indexes_cursor = db.rag_indexes.find({"status": "building"})
        async for index_doc in stale_indexes_cursor:
            dataset_id = index_doc.get("dataset_id")
            if not dataset_id:
                continue
            if dataset_id in rebuild_queue:
                continue
                
            dataset = await db.datasets.find_one({"_id": get_id_query(dataset_id)})
            if not dataset or dataset.get("status") not in ["indexed", "ready"]:
                logger.info(f"Startup recovery: Cleaned up stale 'building' index {index_doc['_id']} (associated dataset status is not active).")
                await db.rag_indexes.update_one(
                    {"_id": index_doc["_id"]},
                    {
                        "$set": {
                            "status": "failed",
                            "progress": 0.0,
                            "error": "Index build was interrupted (server restart or memory limit exceeded)."
                        }
                    }
                )

        # 3. Check for indexed or ready datasets
        datasets_cursor = db.datasets.find({"status": {"$in": ["indexed", "ready"]}})
        async for dataset in datasets_cursor:
            dataset_id = str(dataset["_id"])
            if dataset_id in rebuild_queue:
                continue
            
            # Prevent infinite rebuild loops
            if dataset_id in _rebuilt_datasets:
                logger.info(f"Startup recovery: Dataset {dataset_id} already processed/rebuilt in this run. Skipping to prevent loop.")
                continue
            
            # Skip legacy datasets that do not have a Cloudinary or GridFS backup
            if not dataset.get("cloudinary_url") and not dataset.get("secure_url") and not dataset.get("gridfs_id"):
                logger.warning(
                    f"Startup recovery: Dataset '{dataset.get('name') or dataset.get('file_name')}' ({dataset_id}) "
                    f"does not have a Cloudinary URL or GridFS backup. Skipping automated index rebuild."
                )
                continue

            # Find RAG index document
            index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
            if not index_doc:
                logger.info(f"No RAG index document found for dataset {dataset_id}. Queueing index rebuild...")
                rebuild_queue.append(dataset_id)
                _rebuilt_datasets.add(dataset_id)
                continue
                
            index_id = str(index_doc["_id"])
            
            # Check if ChromaDB collection is empty
            is_empty = await collection_is_empty(index_id)
            if is_empty:
                logger.warning(
                    f"Startup recovery: RAG Index {index_id} for dataset '{dataset.get('name') or dataset.get('file_name')}' "
                    f"is empty in ChromaDB. Queueing download and rebuild..."
                )
                await db.rag_indexes.update_one(
                    {"_id": index_doc["_id"]},
                    {"$set": {"status": "building", "error": None}}
                )
                rebuild_queue.append(dataset_id)
                _rebuilt_datasets.add(dataset_id)
            else:
                logger.info(f"Startup recovery: Dataset '{dataset.get('name') or dataset.get('file_name')}' index {index_id} is verified healthy.")
            
            # Cooperative yield to prevent event loop starvation
            await asyncio.sleep(0.1)

        # Dispatch sequential index rebuilding to prevent concurrent SQLite locks
        if rebuild_queue:
            logger.info(f"Startup recovery: Found {len(rebuild_queue)} empty vector stores/interrupted datasets to rebuild sequentially.")
            asyncio.create_task(run_sequential_rebuilds(rebuild_queue))
                
    except Exception as e:
        logger.error(f"Error during RAG startup recovery check: {e}", exc_info=True)

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
