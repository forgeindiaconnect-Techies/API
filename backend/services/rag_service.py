import logging
import os
import asyncio
from datetime import datetime
from database import get_db

logger = logging.getLogger(__name__)

# In-memory tracking of active index rebuild tasks to avoid concurrent builds in this process
rebuilding_indexes = set()

async def _build_index(index_id: str, config: dict, db):
    """Build vector index from dataset with safety checks to avoid duplicate concurrent runs"""
    if index_id in rebuilding_indexes:
        logger.info(f"Rebuild task for RAG Index {index_id} is already in progress. Skipping duplicate execution.")
        return
        
    rebuilding_indexes.add(index_id)
    logger.info(f"Lock acquired: starting index build for {index_id}")
    
    temp_path = None
    dataset = None
    try:
        index_doc = await db.rag_indexes.find_one({"_id": index_id})
        if not index_doc:
            logger.warning(f"Index document {index_id} not found in DB.")
            return
            
        dataset_id = index_doc["dataset_id"]
        dataset = await db.datasets.find_one({"_id": dataset_id})
        if not dataset:
            raise Exception("Dataset not found")

        # Set status to building in database
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"status": "building", "error": None}}
        )

        from api.routes.chat import download_file_from_gridfs
        import os

        # Download from GridFS (happens only once per build)
        temp_path = await download_file_from_gridfs(dataset)
        file_type = dataset.get("file_type")

        # 1. Extract text / rows using the shared service logic
        from services.dataset_service import extract_text_from_file
        chunks = await extract_text_from_file(temp_path, file_type)

        # 2. Create embeddings & save to VectorStore
        if chunks:
            from vector_db.store import VectorStore, get_embedding_model
            embedder = get_embedding_model(config.get("embedding_model", "paraphrase-MiniLM-L3-v2"))

            embeddings = []
            batch_size = 32
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i+batch_size]
                if asyncio.iscoroutinefunction(embedder.encode):
                    batch_embeds = await embedder.encode(batch)
                else:
                    batch_embeds = await asyncio.to_thread(embedder.encode, batch)
                if hasattr(batch_embeds, "tolist"):
                    batch_embeds = batch_embeds.tolist()
                embeddings.extend(batch_embeds)

            index_type = config.get("index_type", "chroma")
            store = VectorStore(backend=index_type, collection_name=index_id)
            
            # Format proper metadata structure
            metadatas = []
            for idx, chunk in enumerate(chunks):
                metadatas.append({
                    "document_id": dataset_id,
                    "chunk_id": f"{index_id}_{idx}",
                    "source_file": dataset["name"],
                    "chunk_text": chunk
                })
            ids = [f"{index_id}_{idx}" for idx in range(len(chunks))]
            await store.add_documents(chunks, embeddings, metadatas, ids)

            await db.rag_indexes.update_one(
                {"_id": index_id},
                {"$set": {"status": "ready", "chunk_count": len(chunks), "error": None}}
            )
            logger.info(f"Rebuild status: Index {index_id} built successfully with {len(chunks)} chunks.")
        else:
            raise Exception("No chunks extracted from dataset")

    except Exception as e:
        logger.error(f"Failed to build index {index_id}: {e}")
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"status": "error", "error": str(e)}}
        )
    finally:
        rebuilding_indexes.discard(index_id)
        logger.info(f"Lock released: index build task for {index_id} completed.")
        if temp_path and os.path.exists(temp_path) and dataset:
            try:
                if dataset.get("gridfs_id") and str(dataset.get("gridfs_id")) in temp_path:
                    os.remove(temp_path)
                    logger.info(f"Cleaned up temp file used for indexing: {temp_path}")
            except Exception as clean_err:
                logger.error(f"Failed to delete temp file {temp_path}: {clean_err}")

async def query_vector_store(index_id: str, query: str, top_k: int, db) -> list:
    index = await db.rag_indexes.find_one({"_id": index_id})
    if not index:
        return []

    from vector_db.store import VectorStore, get_embedding_model
    embedder = get_embedding_model(index.get("embedding_model", "paraphrase-MiniLM-L3-v2"))
    if hasattr(embedder, "encode"):
        if asyncio.iscoroutinefunction(embedder.encode):
            query_emb = await embedder.encode(query)
        else:
            query_emb = await asyncio.to_thread(embedder.encode, query)
    else:
        query_emb = []
    if hasattr(query_emb, "tolist"):
        query_emb = query_emb.tolist()

    store = VectorStore(backend=index.get("index_type", "chroma"), collection_name=index_id)
    raw_results = await store.query(query_emb, top_k=top_k)

    from models import SearchResult
    results = []
    for r in raw_results:
        results.append(SearchResult(
            content=r["document"],
            score=r["score"],
            source=r["metadata"].get("source", "unknown"),
            metadata=r["metadata"],
        ))
    return results
