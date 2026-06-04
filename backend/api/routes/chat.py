from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime
from typing import List
import json
import asyncio
import httpx
import logging

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


@router.post("/conversations/{conversation_id}/stream")
async def stream_message(
    conversation_id: str,
    data: StreamRequest,
    current_user=Depends(get_current_user)
):
    async def generate():
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": data.model or "llama3",
                        "messages": [{"role": "user", "content": data.content}],
                        "stream": True,
                        "options": {
                            "temperature": data.temperature,
                            "num_predict": data.max_tokens,
                        }
                    }
                ) as response:
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                chunk = json.loads(line)
                                if "message" in chunk:
                                    token = chunk["message"].get("content", "")
                                    if token:
                                        yield f"data: {json.dumps({'token': token})}\n\n"
                                if chunk.get("done"):
                                    yield "data: [DONE]\n\n"
                                    return
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            # Fallback: simulate response
            fallback = f"I understand your question about: {data.content[:50]}... Let me help you with that. This is a demo response since Ollama is not connected."
            for word in fallback.split():
                yield f"data: {json.dumps({'token': word + ' '})}\n\n"
                await asyncio.sleep(0.05)
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
