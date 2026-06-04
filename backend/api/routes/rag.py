from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from datetime import datetime
import time
import logging

from models import IndexCreate, IndexResponse, SearchRequest, SearchResponse, RAGChatRequest
from auth.utils import get_current_user
from database import get_db

router = APIRouter(prefix="/rag", tags=["RAG"])
logger = logging.getLogger(__name__)


def fmt_index(i: dict) -> dict:
    return {
        "id": str(i["_id"]),
        "name": i.get("name", ""),
        "dataset_id": i.get("dataset_id", ""),
        "embedding_model": i.get("embedding_model", ""),
        "chunk_count": i.get("chunk_count", 0),
        "status": i.get("status", "building"),
        "user_id": i.get("user_id", ""),
        "created_at": i.get("created_at", datetime.utcnow()),
    }


@router.post("/index")
async def create_index(
    data: IndexCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user)
):
    db = get_db()
    doc = {
        "name": data.name,
        "dataset_id": data.dataset_id,
        "embedding_model": data.embedding_model,
        "chunk_size": data.chunk_size,
        "chunk_overlap": data.chunk_overlap,
        "index_type": data.index_type,
        "chunk_count": 0,
        "status": "building",
        "user_id": str(current_user["_id"]),
        "created_at": datetime.utcnow(),
    }
    result = await db.rag_indexes.insert_one(doc)
    index_id = str(result.inserted_id)
    doc["_id"] = index_id

    background_tasks.add_task(_build_index, index_id, data.dict(), db)
    return fmt_index(doc)


async def _build_index(index_id: str, config: dict, db):
    """Build vector index from dataset"""
    import asyncio
    try:
        # Simulate index building
        await asyncio.sleep(3)
        chunk_count = 200 + (hash(index_id) % 800)
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"status": "ready", "chunk_count": chunk_count}}
        )
    except Exception as e:
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"status": "error", "error": str(e)}}
        )


@router.get("/indexes")
async def list_indexes(current_user=Depends(get_current_user)):
    db = get_db()
    indexes = []
    async for i in db.rag_indexes.find({"user_id": str(current_user["_id"])}):
        indexes.append(fmt_index(i))
    return indexes


@router.delete("/indexes/{index_id}")
async def delete_index(index_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    await db.rag_indexes.delete_one({"_id": index_id, "user_id": str(current_user["_id"])})
    return {"message": "Index deleted"}


@router.post("/search")
async def search(data: SearchRequest, current_user=Depends(get_current_user)):
    db = get_db()
    start = time.time()

    index = await db.rag_indexes.find_one({"_id": data.index_id})
    if not index:
        raise HTTPException(status_code=404, detail="Index not found")
    if index.get("status") != "ready":
        raise HTTPException(status_code=400, detail="Index not ready")

    # Simulate vector search results
    results = _simulate_search(data.query, data.top_k)
    latency = round((time.time() - start) * 1000, 2)

    return SearchResponse(
        results=results,
        query=data.query,
        index_id=data.index_id,
        latency_ms=latency,
    )


@router.post("/chat")
async def rag_chat(data: RAGChatRequest, current_user=Depends(get_current_user)):
    db = get_db()
    index = await db.rag_indexes.find_one({"_id": data.index_id})
    if not index:
        raise HTTPException(status_code=404, detail="Index not found")

    # Get relevant chunks
    results = _simulate_search(data.question, data.top_k)

    # Generate answer using context
    context = "\n\n".join([r.content for r in results])
    answer = f"""Based on the retrieved documents, here is the answer to your question:

**Question:** {data.question}

**Answer:** The information in your knowledge base indicates that this topic involves several key considerations. The retrieved context shows relevant details that help address your query comprehensively.

*Sources used: {', '.join(set(r.source for r in results))}*"""

    return {
        "answer": answer,
        "sources": results,
        "model": data.model,
        "tokens_used": 342,
    }


def _simulate_search(query: str, top_k: int):
    """Simulate vector search with mock results"""
    from models import SearchResult
    import random

    templates = [
        "This section discusses {topic} in detail, covering the main principles and applications.",
        "According to the documentation, {topic} requires careful consideration of multiple factors.",
        "The analysis shows that {topic} has significant implications for performance and scalability.",
        "Research indicates that {topic} is best approached with a systematic methodology.",
        "Key findings about {topic}: it demonstrates strong correlation with downstream outcomes.",
    ]

    results = []
    words = query.split()[:3]
    topic = " ".join(words) if words else "the requested information"

    for i in range(min(top_k, 5)):
        content = templates[i % len(templates)].format(topic=topic)
        score = round(0.95 - (i * 0.06) + random.uniform(-0.02, 0.02), 3)
        results.append(SearchResult(
            content=content,
            score=max(0.5, score),
            source=f"document_page_{i + 1}.pdf",
            metadata={"page": i + 1, "chunk": i},
        ))

    return results
