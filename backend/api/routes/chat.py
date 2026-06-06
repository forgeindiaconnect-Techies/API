from fastapi import APIRouter, Depends, HTTPException, Request, Response
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


async def ensure_dataset_indexed(dataset_id: str, db) -> str:
    """Check if the dataset has a ready vector index; if not, build it synchronously."""
    index = await db.rag_indexes.find_one({"dataset_id": dataset_id, "status": "ready"})
    if index:
        try:
            from services.chroma_service import collection_is_empty
            is_empty = await collection_is_empty(str(index["_id"]))
            if not is_empty:
                return str(index["_id"])
            logger.info(f"Index {index['_id']} is ready in DB but empty in vector store. Rebuilding...")
        except Exception as e:
            logger.error(f"Error checking vector store count: {e}")

    # Find the dataset
    dataset = await db.datasets.find_one({"_id": dataset_id})
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    from services.dataset_service import build_index_for_dataset
    try:
        index_id = await build_index_for_dataset(dataset, db)
        return index_id
    except Exception as e:
        logger.error(f"Failed to auto-index dataset {dataset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to index dataset: {str(e)}")


@router.options("/conversations/{conversation_id}/stream")
async def options_stream_message(conversation_id: str, response: Response):
    response.headers["Access-Control-Allow-Origin"] = "https://d-ai-nu.vercel.app"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response


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

    async def generate_response():
        try:
            # Check if context was selected
            if not data.dataset_id and not data.index_id:
                answer_content = "Please select a dataset file from the 'Add Context' dropdown above to begin searching."
                sources = []
            else:
                index_id = data.index_id
                if data.dataset_id:
                    # Enforce that the dataset is indexed
                    index_id = await ensure_dataset_indexed(data.dataset_id, db)
                
                from services.chat_service import query_dataset_rag
                rag_res = await query_dataset_rag(index_id, data.content, top_k=3, db=db)
                answer_content = rag_res["answer"]
                sources = rag_res.get("sources", [])

            # Stream response chunk by chunk for visual streaming effect
            words = answer_content.split(" ")
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
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

