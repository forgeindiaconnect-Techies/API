import asyncio
import logging
from database import get_db
from services.chroma_service import collection_is_empty
from services.dataset_service import build_index_for_dataset

logger = logging.getLogger(__name__)

async def run_startup_recovery():
    """Verify all datasets in database, and rebuild their vector store indexes if empty."""
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
                logger.info(f"No RAG index document found for dataset {dataset_id}. Triggering build...")
                try:
                    await build_index_for_dataset(dataset, db)
                except Exception as e:
                    logger.error(f"Failed to auto-build index for dataset {dataset_id} on startup: {e}")
                continue
                
            index_id = str(index_doc["_id"])
            
            # Check if ChromaDB collection is empty
            is_empty = await collection_is_empty(index_id)
            if is_empty:
                logger.warning(
                    f"Startup recovery: RAG Index {index_id} for dataset '{dataset.get('name') or dataset.get('file_name')}' "
                    f"is empty in ChromaDB. Automatically downloading from Cloudinary and rebuilding..."
                )
                try:
                    # Clean up status in index document so search doesn't query a building index
                    await db.rag_indexes.update_one(
                        {"_id": index_doc["_id"]},
                        {"$set": {"status": "building", "error": None}}
                    )
                    # Trigger indexing synchronously to verify everything is indexed
                    await build_index_for_dataset(dataset, db)
                except Exception as e:
                    logger.error(f"Failed to rebuild index for dataset {dataset_id} on startup: {e}")
            else:
                logger.info(f"Startup recovery: Dataset '{dataset.get('name') or dataset.get('file_name')}' index {index_id} is verified healthy.")
                
    except Exception as e:
        logger.error(f"Error during RAG startup recovery check: {e}")
