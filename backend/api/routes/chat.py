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


async def read_dataset_context(dataset_id: str, db) -> str:
    """Reads dataset text/metadata to feed directly as immediate context"""
    dataset = await db.datasets.find_one({"_id": dataset_id})
    if not dataset:
        return ""
    
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

    # 2. Build history
    history = []
    conv = await db.conversations.find_one({"_id": conversation_id})
    if conv and conv.get("system_prompt"):
        history.append({"role": "system", "content": conv["system_prompt"]})

    messages_cursor = db.messages.find({"conversation_id": conversation_id}).sort("created_at", 1)
    db_messages = []
    async for m in messages_cursor:
        db_messages.append(m)

    # Context window sizing
    context_window_size = data.context_window if data.context_window > 0 else 10
    recent_messages = db_messages[-context_window_size:] if len(db_messages) > context_window_size else db_messages

    # Add historical messages (excluding the last one which we will modify with context)
    for m in recent_messages:
        if m["_id"] == db_messages[-1]["_id"]:
            continue
        history.append({"role": m["role"], "content": m["content"]})

    # 3. Fetch context if index_id (RAG) or dataset_id (File) is provided
    latest_content = data.content
    context_str = ""

    if data.index_id:
        try:
            from api.routes.rag import query_vector_store
            results = await query_vector_store(data.index_id, data.content, top_k=3, db=db)
            if results:
                context_str = "\n\n".join([f"[Source: {r.source}]\n{r.content}" for r in results])
        except Exception as e:
            logger.error(f"Error querying vector store: {e}")
            context_str = f"[Error querying vector index: {str(e)}]"
    elif data.dataset_id:
        context_str = await read_dataset_context(data.dataset_id, db)

    if context_str:
        latest_content = f"""Use the following context to answer the question. If the context does not contain the answer, use your general knowledge but prioritize the context.

Context:
{context_str}

Question: {data.content}
Answer:"""

    history.append({"role": "user", "content": latest_content})

    async def generate():
        assistant_content = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": data.model or "llama3",
                        "messages": history,
                        "stream": True,
                        "options": {
                            "temperature": data.temperature,
                            "num_predict": data.max_tokens,
                        }
                    }
                ) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        err_msg = f"Ollama Error (HTTP {response.status_code}): {err_text.decode('utf-8', errors='ignore')}"
                        logger.error(err_msg)
                        yield f"data: {json.dumps({'token': f'Error calling model: {err_msg}'})}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    async for line in response.aiter_lines():
                        if line:
                            try:
                                chunk = json.loads(line)
                                if "message" in chunk:
                                    token = chunk["message"].get("content", "")
                                    if token:
                                        assistant_content += token
                                        yield f"data: {json.dumps({'token': token})}\n\n"
                                if chunk.get("done"):
                                    break
                            except json.JSONDecodeError:
                                pass

            # 4. Save AI Response to MongoDB
            if assistant_content:
                ai_msg = {
                    "role": "assistant",
                    "content": assistant_content,
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

        except httpx.ConnectError:
            err_msg = f"Connection Error: Local Ollama is offline at {settings.OLLAMA_BASE_URL}. Please start Ollama or verify it is running."
            logger.error(err_msg)
            yield f"data: {json.dumps({'token': err_msg})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            err_msg = f"Ollama streaming error: {str(e)}"
            logger.error(err_msg)
            yield f"data: {json.dumps({'token': f'System Error: {err_msg}'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


async def get_ollama_response(prompt: str, conv_id: str, db) -> str:
    """Non-streaming Ollama response with fallback"""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": "llama3",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                }
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("message", {}).get("content", "")
    except Exception as e:
        logger.warning(f"Ollama not available: {e}")

    # Fallback response
    return f"Thank you for your message. I've received: '{prompt[:100]}'. This is a demo response - connect Ollama for full AI capability."
