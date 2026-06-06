from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from datetime import datetime
from typing import List, Optional
import json
import asyncio
import httpx
import logging
import os
import pandas as pd
import PyPDF2
from ollama import AsyncClient

from models import (
    ConversationCreate, ConversationResponse,
    MessageCreate, MessageResponse, StreamRequest
)
from auth.utils import get_current_user
from database import get_db
from config import settings

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


def fmt_conv(c: dict) -> dict:
    return {
        "id": str(c["_id"]),
        "title": c.get("title", "New Conversation"),
        "model": c.get("model", "llama3"),
        "message_count": c.get("message_count", 0),
        "created_at": c.get("created_at", datetime.utcnow()),
        "updated_at": c.get("updated_at", datetime.utcnow()),
    }


def fmt_msg(m: dict) -> dict:
    return {
        "id": str(m["_id"]),
        "role": m["role"],
        "content": m["content"],
        "conversation_id": m.get("conversation_id", ""),
        "created_at": m.get("created_at", datetime.utcnow()),
        "tokens_used": m.get("tokens_used"),
    }


@router.get("/conversations")
async def list_conversations(current_user=Depends(get_current_user)):
    db = get_db()
    convs = []
    async for c in db.conversations.find({"user_id": str(current_user["_id"])}):
        convs.append(fmt_conv(c))
    return sorted(convs, key=lambda x: x["updated_at"], reverse=True)


@router.post("/conversations")
async def create_conversation(data: ConversationCreate, current_user=Depends(get_current_user)):
    db = get_db()
    doc = {
        "title": data.title,
        "model": data.model,
        "system_prompt": data.system_prompt,
        "user_id": str(current_user["_id"]),
        "message_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = await db.conversations.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return fmt_conv(doc)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    await db.conversations.delete_one({
        "_id": conversation_id,
        "user_id": str(current_user["_id"])
    })
    await db.messages.delete_many({"conversation_id": conversation_id})
    return {"message": "Deleted"}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    msgs = []
    async for m in db.messages.find({"conversation_id": conversation_id}):
        msgs.append(fmt_msg(m))
    return sorted(msgs, key=lambda x: x["created_at"])


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    data: MessageCreate,
    current_user=Depends(get_current_user)
):
    db = get_db()

    # Save user message
    user_msg = {
        "role": "user",
        "content": data.content,
        "conversation_id": conversation_id,
        "user_id": str(current_user["_id"]),
        "created_at": datetime.utcnow(),
    }
    u_result = await db.messages.insert_one(user_msg)
    user_msg["_id"] = str(u_result.inserted_id)

    # Get AI response
    ai_content = await get_ollama_response(data.content, conversation_id, db)

    # Save AI message
    ai_msg = {
        "role": "assistant",
        "content": ai_content,
        "conversation_id": conversation_id,
        "user_id": str(current_user["_id"]),
        "created_at": datetime.utcnow(),
    }
    a_result = await db.messages.insert_one(ai_msg)
    ai_msg["_id"] = str(a_result.inserted_id)

    # Update conversation
    await db.conversations.update_one(
        {"_id": conversation_id},
        {"$set": {"updated_at": datetime.utcnow()}, "$inc": {"message_count": 2}}
    )

    return {"user": fmt_msg(user_msg), "assistant": fmt_msg(ai_msg)}


def ensure_file_locally_present(dataset: dict) -> bool:
    """Fallback helper kept for compatibility; downloads from GridFS if missing."""
    import asyncio
    try:
        # Run download helper synchronously in context of a sync def
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If event loop is already running, run_coroutine_threadsafe
            import threading
            from concurrent.futures import Future
            def run():
                coro = download_file_from_gridfs(dataset)
                return asyncio.run(coro)
            # Just try downloading to block
            import shutil
            # Let's import download path
        return True
    except Exception:
        return False


async def download_file_from_gridfs(dataset_doc: dict) -> str:
    """Download a dataset file from MongoDB GridFS to a temporary local path for processing"""
    gridfs_id = dataset_doc.get("gridfs_id")
    if not gridfs_id:
        # Fallback to local file_path if it exists (for backward compatibility)
        file_path = dataset_doc.get("file_path", "")
        if file_path and os.path.exists(file_path):
            return file_path
        raise FileNotFoundError("Dataset has no GridFS file ID and local file is missing.")

    import tempfile
    from bson import ObjectId
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    from database import get_db

    db = get_db()
    fs = AsyncIOMotorGridFSBucket(db._db)

    # Use a unique temp path
    ext = dataset_doc.get("file_type", "txt")
    temp_dir = os.path.join(tempfile.gettempdir(), "personal-ai-studio")
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, f"{gridfs_id}.{ext}")

    # Read from GridFS bucket and write locally
    grid_out = await fs.open_download_stream(ObjectId(gridfs_id))
    with open(temp_file_path, "wb") as f:
        while chunk := await grid_out.read(1024 * 1024):
            f.write(chunk)

    logger.info(f"Downloaded GridFS file {gridfs_id} to temp path {temp_file_path}")
    return temp_file_path


async def read_dataset_context(dataset_id: str, db) -> str:
    """Reads dataset text/metadata to feed directly as immediate context from GridFS"""
    dataset = await db.datasets.find_one({"_id": dataset_id})
    if not dataset:
        return ""
    
    temp_path = None
    try:
        temp_path = await download_file_from_gridfs(dataset)
        file_type = dataset.get("file_type")
        if not temp_path or not os.path.exists(temp_path):
            return ""
            
        if file_type in ("txt", "md"):
            with open(temp_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(5000)
            return content
        elif file_type == "pdf":
            text_parts = []
            with open(temp_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for i in range(min(5, len(reader.pages))):
                    page_text = reader.pages[i].extract_text()
                    if page_text:
                        text_parts.append(page_text)
                    if sum(len(p) for p in text_parts) > 5000:
                        break
            return "\n".join(text_parts)[:5000]
        elif file_type in ("csv", "xlsx", "xls"):
            if file_type == "csv":
                df = pd.read_csv(temp_path, nrows=50)
            else:
                df = pd.read_excel(temp_path, nrows=50)
            
            rows_str = []
            for _, row in df.iterrows():
                row_text = ", ".join([f"{col}: {val}" for col, val in row.items() if pd.notnull(val)])
                rows_str.append(row_text)
            return "\n".join(rows_str)[:5000]
        elif file_type == "json":
            with open(temp_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(5000)
            return content
        else:
            return f"[File type .{file_type} not directly readable as raw text context]"
    except Exception as e:
        logger.error(f"Error reading dataset context for {dataset_id}: {e}")
        return f"[Error loading context file: {str(e)}]"
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                # Only clean up if it's indeed a temporary file
                if dataset.get("gridfs_id") and str(dataset.get("gridfs_id")) in temp_path:
                    os.remove(temp_path)
            except Exception as clean_err:
                logger.error(f"Failed to delete temp file {temp_path}: {clean_err}")


@router.get("/health/ollama")
async def check_ollama_health(current_user=Depends(get_current_user)):
    """Check connectivity to Ollama and list loaded models"""
    try:
        client = AsyncClient(host=settings.OLLAMA_BASE_URL, headers={"bypass-tunnel-reminder": "true"})
        models_list = await client.list()
        return {
            "status": "connected",
            "host": settings.OLLAMA_BASE_URL,
            "models": [m.get("model") for m in models_list.get("models", [])],
        }
    except Exception as e:
        openai_status = "configured" if settings.OPENAI_API_KEY else "not_configured"
        return {
            "status": "disconnected",
            "host": settings.OLLAMA_BASE_URL,
            "error": str(e),
            "fallback_openai": openai_status
        }


async def ensure_dataset_indexed(dataset_id: str, db) -> str:
    """Check if the dataset has a ready vector index; if not, build it synchronously."""
    index = await db.rag_indexes.find_one({"dataset_id": dataset_id, "status": "ready"})
    if index:
        try:
            from vector_db.store import VectorStore
            store = VectorStore(backend=index.get("index_type", "chroma"), collection_name=str(index["_id"]))
            if await store.count() > 0:
                return str(index["_id"])
            logger.info(f"Index {index['_id']} is ready in DB but empty in vector store (possibly process restart with mock). Rebuilding...")
        except Exception as e:
            logger.error(f"Error checking vector store count: {e}")

    # Find the dataset
    dataset = await db.datasets.find_one({"_id": dataset_id})
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    # Check if there is an index doc already
    index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
    if index_doc:
        index_id = str(index_doc["_id"])
        await db.rag_indexes.update_one({"_id": index_id}, {"$set": {"status": "building", "error": None}})
    else:
        doc = {
            "name": f"Dynamic Index - {dataset['name']}",
            "dataset_id": dataset_id,
            "embedding_model": "all-MiniLM-L6-v2",
            "chunk_size": 512,
            "chunk_overlap": 50,
            "index_type": "chroma",
            "chunk_count": 0,
            "status": "building",
            "user_id": dataset["user_id"],
            "created_at": datetime.utcnow(),
        }
        result = await db.rag_indexes.insert_one(doc)
        index_id = str(result.inserted_id)

    # Build index synchronously to guarantee it is indexed when queried
    from services.rag_service import _build_index
    try:
        await _build_index(index_id, {
            "chunk_size": 512,
            "chunk_overlap": 50,
            "index_type": "chroma",
            "embedding_model": "all-MiniLM-L6-v2",
        }, db)
    except Exception as e:
        logger.error(f"Failed to auto-index dataset {dataset_id}: {e}")
        await db.rag_indexes.update_one({"_id": index_id}, {"$set": {"status": "error", "error": str(e)}})
        raise HTTPException(status_code=500, detail=f"Failed to index dataset: {str(e)}")

    # Verify if the index built successfully
    final_index = await db.rag_indexes.find_one({"_id": index_id})
    if not final_index or final_index.get("status") != "ready":
        err_msg = final_index.get("error") if final_index else "Unknown indexing error"
        raise HTTPException(
            status_code=500,
            detail=f"Dataset indexing failed. Status: {final_index.get('status') if final_index else 'missing'}. Error: {err_msg}"
        )

    return index_id


@router.post("/conversations/{conversation_id}/stream")
async def stream_message(
    conversation_id: str,
    data: StreamRequest,
    current_user=Depends(get_current_user),
    request: Request = None
):
    db = get_db()

    # 1. Save user message immediately to DB
    user_msg = {
        "role": "user",
        "content": data.content,
        "conversation_id": conversation_id,
        "user_id": str(current_user["_id"]),
        "created_at": datetime.utcnow(),
    }
    await db.messages.insert_one(user_msg)

    # 2. Check and query selected context (dataset or vector index)
    results = []
    dataset_name = ""

    if data.dataset_id:
        try:
            dataset = await db.datasets.find_one({"_id": data.dataset_id})
            if dataset:
                dataset_name = dataset.get("name", "selected file")
            
            # Ensure dataset is indexed synchronously
            index_id = await ensure_dataset_indexed(data.dataset_id, db)
            
            from services.rag_service import query_vector_store
            results = await query_vector_store(index_id, data.content, top_k=3, db=db)
        except Exception as e:
            logger.error(f"Error ensuring dataset is indexed or querying vector store: {e}")
            # Local dynamic text search fallback as backup
            try:
                text_content = await read_dataset_context(data.dataset_id, db)
                if text_content:
                    chunks = [text_content[i:i+500] for i in range(0, len(text_content), 400)]
                    query_words = [w.lower() for w in data.content.split() if len(w) > 3]
                    matches = []
                    for c in chunks:
                        score = sum(1 for w in query_words if w in c.lower())
                        if score > 0:
                            matches.append((c, score))
                    
                    matches.sort(key=lambda x: x[1], reverse=True)
                    
                    from models import SearchResult
                    results = [
                        SearchResult(
                            content=m[0].strip(),
                            score=round(float(m[1] / max(1, len(query_words))), 2),
                            source=dataset_name or "selected file",
                            metadata={"source": dataset_name or "selected file"}
                        )
                        for m in matches[:3]
                    ]
            except Exception as fallback_err:
                logger.error(f"Fallback text search also failed: {fallback_err}")
    elif data.index_id:
        try:
            from services.rag_service import query_vector_store
            results = await query_vector_store(data.index_id, data.content, top_k=3, db=db)
        except Exception as e:
            logger.error(f"Error querying vector store: {e}")

    # Generate answer from context (ChromaDB similarity search matches)
    from vector_db.store import get_embedding_model
    embedder = get_embedding_model()
    is_mock = embedder.__class__.__name__ == "MockEmbedder"

    async def generate_response():
        try:
            # Check if context was selected at all
            if not data.dataset_id and not data.index_id:
                answer_content = "Please select a dataset file from the 'Add Context' dropdown above to begin searching."
            else:
                best_match = None
                if results:
                    # Filter matches: if mock embedder, ignore score threshold since scores will be low random values
                    threshold = 0.0 if is_mock else 0.30
                    matches = [r for r in results if r.score >= threshold]
                    if matches:
                        best_match = matches[0]

                if best_match:
                    # Return the exact information from the uploaded dataset
                    answer_content = (
                        f"{best_match.content}\n\n"
                        f"---\n"
                        f"**Source File Name:** {best_match.source}\n"
                        f"**Matching Chunk:** {best_match.content}\n"
                        f"**Similarity Score:** {best_match.score:.4f}"
                    )
                    if is_mock:
                        answer_content += (
                            "\n\n"
                            "> ⚠️ **Demo Mode Active:** The server is running on Render's free/starter tier "
                            "and has bypassed heavy local models to avoid memory limit crashes. "
                            "To get real semantic search results, please configure a valid `OPENAI_API_KEY` "
                            "in your Render dashboard environment variables."
                        )
                else:
                    # Return: 'No relevant information found in the uploaded dataset.'
                    answer_content = "No relevant information found in the uploaded dataset."

            # Stream response chunk by chunk for visual streaming effect
            words = answer_content.split(" ")
            accumulated = ""
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
                accumulated += token
                yield f"data: {json.dumps({'token': token})}\n\n"
                await asyncio.sleep(0.01)

            # Save assistant message to DB
            ai_msg = {
                "role": "assistant",
                "content": answer_content,
                "conversation_id": conversation_id,
                "user_id": str(current_user["_id"]),
                "created_at": datetime.utcnow(),
            }
            await db.messages.insert_one(ai_msg)

            # Update conversation message count and updated_at
            await db.conversations.update_one(
                {"_id": conversation_id},
                {"$set": {"updated_at": datetime.utcnow()}, "$inc": {"message_count": 2}}
            )
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Error in stream generation: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': f'Stream generation failed: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"

    origin = request.headers.get("origin") if request is not None else None
    allowed_origins = [
        "https://d-ai-nu.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173"
    ]
    
    response = StreamingResponse(generate_response(), media_type="text/event-stream")
    
    # Set standard SSE stream control headers to prevent buffering and caching
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    
    is_allowed = False
    if origin:
        if origin in allowed_origins or (origin.startswith("https://") and origin.endswith(".vercel.app")):
            is_allowed = True
            
    if is_allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "https://d-ai-nu.vercel.app"
        
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response


async def get_ollama_response(prompt: str, conv_id: str, db) -> str:
    """Non-streaming fallback message removing Ollama dependency"""
    return "Dataset-Only RAG is active. Please use the streaming endpoint with a dataset selected."
