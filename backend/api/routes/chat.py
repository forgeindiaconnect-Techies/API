from fastapi import APIRouter, Depends, HTTPException
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
    """Helper to verify if a dataset file exists locally, and copy it from fallback directories if needed."""
    import shutil
    file_path = dataset.get("file_path")
    if not file_path:
        return False
        
    if os.path.exists(file_path):
        return True
        
    filename = dataset.get("name")
    if not filename:
        return False
        
    fallbacks = [
        os.path.join("C:\\Users\\Thiru T\\Desktop", filename),
        os.path.join("C:\\Users\\Thiru T\\Downloads", filename),
        os.path.join("c:\\Users\\Thiru T\\Desktop\\personal-ai-studio", filename),
        os.path.join("c:\\Users\\Thiru T\\Desktop\\personal-ai-studio\\backend", filename),
    ]
    
    for fb in fallbacks:
        if os.path.exists(fb):
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                shutil.copy2(fb, file_path)
                logger.info(f"Copied fallback dataset file from {fb} to {file_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to copy fallback file from {fb} to {file_path}: {e}")
                
    return False


async def read_dataset_context(dataset_id: str, db) -> str:
    """Reads dataset text/metadata to feed directly as immediate context"""
    dataset = await db.datasets.find_one({"_id": dataset_id})
    if not dataset:
        return ""
    
    # Ensure file is locally present
    ensure_file_locally_present(dataset)
    
    file_path = dataset.get("file_path")
    file_type = dataset.get("file_type")
    if not file_path or not os.path.exists(file_path):
        return ""
        
    try:
        if file_type in ("txt", "md"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(5000)
            return content
        elif file_type == "pdf":
            text_parts = []
            with open(file_path, "rb") as f:
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
                df = pd.read_csv(file_path, nrows=50)
            else:
                df = pd.read_excel(file_path, nrows=50)
            
            rows_str = []
            for _, row in df.iterrows():
                row_text = ", ".join([f"{col}: {val}" for col, val in row.items() if pd.notnull(val)])
                rows_str.append(row_text)
            return "\n".join(rows_str)[:5000]
        elif file_type == "json":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(5000)
            return content
        else:
            return f"[File type .{file_type} not directly readable as raw text context]"
    except Exception as e:
        logger.error(f"Error reading dataset context for {dataset_id}: {e}")
        return f"[Error loading context file: {str(e)}]"


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
            if store.count() > 0:
                return str(index["_id"])
            logger.info(f"Index {index['_id']} is ready in DB but empty in vector store (possibly process restart with mock). Rebuilding...")
        except Exception as e:
            logger.error(f"Error checking vector store count: {e}")

    # Find the dataset
    dataset = await db.datasets.find_one({"_id": dataset_id})
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    # Ensure file is locally present before building index
    ensure_file_locally_present(dataset)

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
    from api.routes.rag import _build_index
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

    return index_id


@router.post("/conversations/{conversation_id}/stream")
async def stream_message(
    conversation_id: str,
    data: StreamRequest,
    current_user=Depends(get_current_user)
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
            
            from api.routes.rag import query_vector_store
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
            from api.routes.rag import query_vector_store
            results = await query_vector_store(data.index_id, data.content, top_k=3, db=db)
        except Exception as e:
            logger.error(f"Error querying vector store: {e}")

    # Generate answer from context (ChromaDB similarity search matches)
    async def generate_response():
        # Check if context was selected at all
        if not data.dataset_id and not data.index_id:
            answer_content = "Please select a dataset file from the 'Add Context' dropdown above to begin searching."
        else:
            best_match = None
            if results:
                # Filter matches with score >= 0.30
                matches = [r for r in results if r.score >= 0.30]
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

    return StreamingResponse(generate_response(), media_type="text/event-stream")


async def get_ollama_response(prompt: str, conv_id: str, db) -> str:
    """Non-streaming fallback message removing Ollama dependency"""
    return "Dataset-Only RAG is active. Please use the streaming endpoint with a dataset selected."
