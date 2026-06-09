import asyncio
import logging
from fastapi import FastAPI
from database import get_db
from vector_db.store import VectorStore
from services.rag_service import _build_index

logger = logging.getLogger(__name__)

async def run_startup_checks(app: FastAPI):
    """Run database health check and startup RAG index validation/recovery checks"""
    logger.info("Initializing database connections and index validation checks...")
    
    # RAG index startup recovery check
    try:
        db = get_db()
        if db is None:
            logger.warning("Database not connected. Skipping startup RAG index check.")
            return

        # Clean up stale "building" indexes: reset them to "error" with an explanation
        result = await db.rag_indexes.update_many(
            {"status": "building"},
            {
                "$set": {
                    "status": "error",
                    "error": "Index build was interrupted (server restart or memory limit exceeded)."
                }
            }
        )
        if result.modified_count > 0:
            logger.info(f"Cleaned up {result.modified_count} stale 'building' indexes and set their status to 'error'.")

        cursor = db.rag_indexes.find({"status": "ready"})
        async for index in cursor:
            index_id = str(index["_id"])
            try:
                store = VectorStore(backend=index.get("index_type", "chroma"), collection_name=index_id)
                # Check vector store count
                count = await store.count()
                if count == 0:
                    logger.info(
                        f"Index verification: RAG Index {index_id} is marked 'ready' in MongoDB "
                        f"but has 0 chunks in ChromaDB. Starting recovery rebuild task..."
                    )
                    
                    config = {
                        "chunk_size": index.get("chunk_size", 512),
                        "chunk_overlap": index.get("chunk_overlap", 50),
                        "index_type": index.get("index_type", "chroma"),
                        "embedding_model": index.get("embedding_model", "paraphrase-MiniLM-L3-v2"),
                    }
                    asyncio.create_task(_build_index(index_id, config, db))
                else:
                    logger.info(f"Index verification: RAG Index {index_id} is verified healthy ({count} chunks).")
            except Exception as index_err:
                logger.error(f"Failed verification/rebuild check for RAG index {index_id}: {index_err}")
                
    except Exception as startup_err:
        logger.error(f"Error during RAG index startup validation: {startup_err}")
