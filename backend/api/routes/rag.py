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
    try:
        index_doc = await db.rag_indexes.find_one({"_id": index_id})
        if not index_doc:
            return
        dataset_id = index_doc["dataset_id"]
        dataset = await db.datasets.find_one({"_id": dataset_id})
        if not dataset:
            raise Exception("Dataset not found")

        file_path = dataset.get("file_path")
        file_type = dataset.get("file_type")

        # 1. Extract text / rows
        chunks = []
        if file_type in ("csv", "xlsx", "xls"):
            import pandas as pd
            if file_type == "csv":
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            for i, row in df.iterrows():
                row_str = ", ".join([f"{col}: {val}" for col, val in row.items() if pd.notnull(val)])
                chunks.append(row_str)
        elif file_type == "pdf":
            import PyPDF2
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page_num in range(len(reader.pages)):
                    page_text = reader.pages[page_num].extract_text()
                    if page_text:
                        chunks.append(page_text)
        elif file_type in ("txt", "md"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            chunk_size = config.get("chunk_size", 512)
            chunk_overlap = config.get("chunk_overlap", 50)
            step = chunk_size - chunk_overlap
            for i in range(0, len(text), step):
                chunks.append(text[i:i+chunk_size])
        else:
            raise Exception(f"File type {file_type} not indexable for RAG")

        # 2. Create embeddings & save to VectorStore
        if chunks:
            from vector_db.store import VectorStore, get_embedding_model
            embedder = get_embedding_model(config.get("embedding_model", "all-MiniLM-L6-v2"))

            embeddings = []
            batch_size = 32
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i+batch_size]
                batch_embeds = embedder.encode(batch)
                if hasattr(batch_embeds, "tolist"):
                    batch_embeds = batch_embeds.tolist()
                embeddings.extend(batch_embeds)

            store = VectorStore(backend=config.get("index_type", "chroma"), collection_name=index_id)
            metadatas = [{"source": dataset["name"], "chunk": idx} for idx in range(len(chunks))]
            ids = [f"{index_id}_{idx}" for idx in range(len(chunks))]
            store.add_documents(chunks, embeddings, metadatas, ids)

            await db.rag_indexes.update_one(
                {"_id": index_id},
                {"$set": {"status": "ready", "chunk_count": len(chunks)}}
            )
        else:
            raise Exception("No chunks extracted from dataset")

    except Exception as e:
        logger.error(f"Failed to build index {index_id}: {e}")
        await db.rag_indexes.update_one(
            {"_id": index_id},
            {"$set": {"status": "error", "error": str(e)}}
        )


async def query_vector_store(index_id: str, query: str, top_k: int, db) -> list:
    index = await db.rag_indexes.find_one({"_id": index_id})
    if not index:
        return []

    from vector_db.store import VectorStore, get_embedding_model
    embedder = get_embedding_model(index.get("embedding_model", "all-MiniLM-L6-v2"))
    query_emb = embedder.encode(query)
    if hasattr(query_emb, "tolist"):
        query_emb = query_emb.tolist()

    store = VectorStore(backend=index.get("index_type", "chroma"), collection_name=index_id)
    raw_results = store.query(query_emb, top_k=top_k)

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

    results = await query_vector_store(data.index_id, data.query, data.top_k, db)
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
    results = await query_vector_store(data.index_id, data.question, data.top_k, db)

    # Generate answer using context
    context = "\n\n".join([r.content for r in results])
    prompt = f"""Use the following pieces of context to answer the user question. If you do not know the answer, say you do not know.

Context:
{context}

Question: {data.question}
Answer:"""

    from ollama import AsyncClient
    from config import settings
    try:
        client = AsyncClient(host=settings.OLLAMA_BASE_URL)
        res = await client.generate(
            model=data.model or "llama3",
            prompt=prompt,
            stream=False
        )
        answer = res.get("response", "")
    except Exception as e:
        answer = f"Ollama is not running locally. Details: {str(e)}\n\nHere is the retrieved document context:\n\n{context}\n\n(Note: Connect locally running Ollama model to generate a compiled response)"

    return {
        "answer": answer,
        "sources": results,
        "model": data.model,
        "tokens_used": len(answer.split()) + len(context.split()),
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
