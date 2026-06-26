import asyncio
import logging
import os
from datetime import datetime
from database import get_db
from auth.utils import get_id_query
from services.chroma_service import collection_is_empty

logger = logging.getLogger(__name__)

# In-process cache to prevent infinite RAG index rebuild loops
_rebuilt_datasets = set()

# Maximum number of datasets to rebuild per startup (env-configurable, default 2)
_MAX_STARTUP_REBUILDS = int(os.environ.get("MAX_STARTUP_REBUILDS", "2"))

# Warm-up delay in seconds before starting sequential rebuilds (env-configurable, default 60s)
_REBUILD_WARMUP_SECONDS = int(os.environ.get("REBUILD_WARMUP_SECONDS", "60"))


def dispatch_rebuild_task(dataset_id: str):
    """Always rebuild index locally since ChromaDB SQLite persistence is local to the web container."""
    logger.info(f"Startup recovery: Spawning local background task to rebuild index for dataset: {dataset_id}")
    asyncio.create_task(run_rebuild_locally(dataset_id))

async def run_rebuild_locally(dataset_id: str):
    """Local fallback runner that executes rebuilding after a warm-up delay."""
    # Delay to ensure main thread has completed startup and server is healthy
    await asyncio.sleep(_REBUILD_WARMUP_SECONDS)
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
    """Verify all datasets in database, and queue their vector store indexes rebuild if empty or interrupted.
    
    Respects the following environment variables:
      - DISABLE_STARTUP_REBUILD=true  → Skip all rebuild tasks (recommended on Render)
      - MAX_STARTUP_REBUILDS=N        → Limit rebuilds per startup (default: 2)
      - REBUILD_WARMUP_SECONDS=N      → Seconds to wait before starting rebuilds (default: 60)
    """
    # Safety switch: disable all rebuild tasks on environments where disk is ephemeral (e.g. Render)
    if os.environ.get("DISABLE_STARTUP_REBUILD", "").lower() in ("true", "1", "yes"):
        logger.info(
            "Startup recovery: DISABLE_STARTUP_REBUILD=true is set. "
            "Skipping all automatic rebuild tasks. Datasets can be reprocessed manually from the UI."
        )
        return

    logger.info(f"Starting startup RAG index recovery checks (MAX_STARTUP_REBUILDS={_MAX_STARTUP_REBUILDS}, WARMUP={_REBUILD_WARMUP_SECONDS}s)...")
    try:
        db = get_db()
        if db is None:
            logger.warning("Database not connected, skipping startup RAG index recovery.")
            return

        rebuild_queue = []

        # 1. Check for stale "processing", "preprocessing", or "uploaded" status datasets
        stale_datasets_cursor = db.datasets.find({"status": {"$in": ["uploaded", "saved", "reading_file", "preprocessing", "chunking", "embedding", "embedded", "processing"]}})
        async for dataset in stale_datasets_cursor:
            dataset_id = str(dataset["_id"])
            dataset_name = dataset.get('name') or dataset.get('file_name') or 'unknown'
            
            # Check if dataset has any cloud backup (not just local path)
            has_cloud_backup = bool(
                dataset.get("cloudinary_url") or
                dataset.get("secure_url") or
                dataset.get("s3_key")
            )
            
            if has_cloud_backup:
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
                    f"status and has a cloud backup. Queueing for automatic reprocessing (Attempt {recovery_attempts + 1})."
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
                        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
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
                # No cloud backup available — on ephemeral disk environments (Render), local files are gone.
                # Mark as failed immediately to prevent an infinite recovery loop.
                logger.warning(
                    f"Startup recovery: Dataset '{dataset_name}' ({dataset_id}) was interrupted in 'processing' "
                    f"status, but does not have any cloud backup (Cloudinary/S3). "
                    f"Marking as failed to prevent crash loop. Re-upload the file to reprocess."
                )
                await db.datasets.update_one(
                    {"_id": dataset["_id"]},
                    {"$set": {
                        "status": "failed",
                        "error_message": (
                            "Dataset processing was interrupted (server restart) and no cloud backup was found. "
                            "Please re-upload the file to reprocess it."
                        )
                    }}
                )
                
                # Also mark index as failed if it exists
                await db.rag_indexes.update_many(
                    {"dataset_id": dataset_id},
                    {"$set": {
                        "status": "failed",
                        "progress": 0.0,
                        "error": "Dataset processing was interrupted and no cloud backup was found."
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
            if not dataset or dataset.get("status") not in ["indexed", "ready", "completed"]:
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

        # 3. Check for indexed or ready datasets with empty ChromaDB collections
        # Only queue datasets that have a CLOUD backup — local-only datasets cannot be recovered
        # after an ephemeral disk wipe (Render restart).
        datasets_cursor = db.datasets.find({"status": {"$in": ["indexed", "ready", "completed"]}})
        async for dataset in datasets_cursor:
            dataset_id = str(dataset["_id"])
            if dataset_id in rebuild_queue:
                continue
            
            # Cap total rebuild queue size to prevent server OOM crash
            if len(rebuild_queue) >= _MAX_STARTUP_REBUILDS:
                logger.warning(
                    f"Startup recovery: Rebuild queue is at MAX_STARTUP_REBUILDS={_MAX_STARTUP_REBUILDS}. "
                    f"Skipping remaining datasets. Increase MAX_STARTUP_REBUILDS env var to allow more."
                )
                break
            
            # Prevent infinite rebuild loops
            if dataset_id in _rebuilt_datasets:
                logger.info(f"Startup recovery: Dataset {dataset_id} already processed/rebuilt in this run. Skipping to prevent loop.")
                continue
            
            # Only queue datasets that have a cloud backup to prevent OOM from local-only re-reads
            has_cloud_backup = bool(
                dataset.get("cloudinary_url") or
                dataset.get("secure_url") or
                dataset.get("s3_key")
            )
            if not has_cloud_backup:
                logger.warning(
                    f"Startup recovery: Dataset '{dataset.get('name') or dataset.get('file_name')}' ({dataset_id}) "
                    f"does not have a cloud backup (Cloudinary/S3). "
                    f"Skipping automated index rebuild to prevent OOM crash on ephemeral disk environments."
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
            capped_queue = rebuild_queue[:_MAX_STARTUP_REBUILDS]
            logger.info(
                f"Startup recovery: Found {len(rebuild_queue)} datasets to rebuild. "
                f"Scheduling {len(capped_queue)} (cap={_MAX_STARTUP_REBUILDS}) sequentially with {_REBUILD_WARMUP_SECONDS}s warm-up delay."
            )
            asyncio.create_task(run_sequential_rebuilds(capped_queue))
        else:
            logger.info("Startup recovery: No datasets require rebuilding. All indexes are healthy.")
                
    except Exception as e:
        logger.error(f"Error during RAG startup recovery check: {e}", exc_info=True)

async def run_sequential_rebuilds(dataset_ids: list):
    """Rebuild indexes sequentially with warm-up delay to prevent SQLite lock collisions and OOM."""
    logger.info(f"Sequential Rebuild: Waiting {_REBUILD_WARMUP_SECONDS}s warm-up delay before starting {len(dataset_ids)} rebuilds...")
    await asyncio.sleep(_REBUILD_WARMUP_SECONDS)
    
    db = get_db()
    if db is None:
        logger.error("Sequential Rebuild: Database connection not available.")
        return
        
    for idx, dataset_id in enumerate(dataset_ids):
        try:
            logger.info(f"Sequential Rebuild [{idx + 1}/{len(dataset_ids)}]: Starting RAG index rebuild for dataset {dataset_id}")
            dataset = await db.datasets.find_one({"_id": get_id_query(dataset_id)})
            if not dataset:
                logger.error(f"Sequential Rebuild: Dataset '{dataset_id}' not found in database.")
                continue

            # Verify a cloud backup is still available before attempting rebuild
            has_cloud_backup = bool(
                dataset.get("cloudinary_url") or
                dataset.get("secure_url") or
                dataset.get("s3_key")
            )
            if not has_cloud_backup:
                logger.warning(
                    f"Sequential Rebuild: Dataset '{dataset_id}' has no cloud backup at rebuild time. "
                    f"Skipping to prevent OOM. Mark as failed."
                )
                await db.datasets.update_one(
                    {"_id": dataset["_id"]},
                    {"$set": {
                        "status": "failed",
                        "error_message": "Cannot rebuild: no cloud backup available after server restart. Please re-upload."
                    }}
                )
                await db.rag_indexes.update_many(
                    {"dataset_id": dataset_id},
                    {"$set": {
                        "status": "failed",
                        "progress": 0.0,
                        "error": "No cloud backup available for rebuild after server restart."
                    }}
                )
                continue
                
            # Trigger indexing
            from services.dataset_service import build_index_for_dataset
            await build_index_for_dataset(dataset, db)
            logger.info(f"Sequential Rebuild [{idx + 1}/{len(dataset_ids)}]: Completed RAG index rebuild for dataset: {dataset_id}")
        except Exception as e:
            logger.error(f"Sequential Rebuild: Failed for dataset {dataset_id}: {e}")
        # Yield control between rebuilds to allow other event loop processes to run
        # Wait 30s between rebuilds to allow memory to be freed by GC
        if idx < len(dataset_ids) - 1:
            logger.info(f"Sequential Rebuild: Waiting 30s before next rebuild to allow memory to be freed...")
            await asyncio.sleep(30.0)
