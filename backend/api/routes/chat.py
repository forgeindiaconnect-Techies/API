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
    results = []

    if data.index_id:
        try:
            from api.routes.rag import query_vector_store
            results = await query_vector_store(data.index_id, data.content, top_k=3, db=db)
        except Exception as e:
            logger.error(f"Error querying vector store: {e}")
    elif data.dataset_id:
        try:
            from api.routes.rag import query_vector_store
            # Check if there is an index ready for this dataset
            index = await db.rag_indexes.find_one({"dataset_id": data.dataset_id, "status": "ready"})
            if index:
                results = await query_vector_store(str(index["_id"]), data.content, top_k=3, db=db)
            else:
                # Local dynamic text search fallback if no index is ready
                dataset = await db.datasets.find_one({"_id": data.dataset_id})
                dataset_name = dataset.get("name", "grounding_doc") if dataset else "grounding_doc"
                
                text_content = await read_dataset_context(data.dataset_id, db)
                if text_content:
                    # Segment file into overlapping chunks
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
                            source=dataset_name,
                            metadata={"source": dataset_name}
                        )
                        for m in matches[:3]
                    ]
        except Exception as e:
            logger.error(f"Error running dataset dynamic RAG search: {e}")

    # Build grounding context with matched scores and file name citations
    if results:
        context_str = "\n\n".join([f"[Source: {r.source} (Similarity Score: {r.score})]\n{r.content}" for r in results])

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
            client = AsyncClient(host=settings.OLLAMA_BASE_URL, headers={"bypass-tunnel-reminder": "true"})
            response_stream = await client.chat(
                model=data.model or "llama3",
                messages=history,
                stream=True,
                options={
                    "temperature": data.temperature,
                    "num_predict": data.max_tokens,
                }
            )

            async for chunk in response_stream:
                if "message" in chunk:
                    token = chunk["message"].get("content", "")
                    if token:
                        assistant_content += token
                        yield f"data: {json.dumps({'token': token})}\n\n"

        except Exception as ollama_err:
            err_str = str(ollama_err)
            logger.warning(f"Ollama streaming failed: {err_str}. Checking OpenAI fallback...")

            # Fall back to OpenAI if key is present
            if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-..."):
                try:
                    info_msg = "[System: Local Ollama is offline. Falling back to OpenAI (gpt-4o-mini)...]\n\n"
                    yield f"data: {json.dumps({'token': info_msg})}\n\n"

                    from openai import AsyncOpenAI
                    openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                    
                    openai_history = [{"role": m["role"], "content": m["content"]} for m in history]

                    stream = await openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=openai_history,
                        temperature=data.temperature,
                        max_tokens=data.max_tokens,
                        stream=True
                    )

                    async for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            token = chunk.choices[0].delta.content
                            assistant_content += token
                            yield f"data: {json.dumps({'token': token})}\n\n"

                except Exception as openai_err:
                    logger.error(f"OpenAI fallback failed: {openai_err}")
                    if results:
                        fallback_msg = (
                            "🤖 **Note: LLM server is currently offline. Here is the direct matching content retrieved from your dataset:**\n\n"
                        )
                        for idx, r in enumerate(results):
                            fallback_msg += f"**Chunk {idx+1} (Source: `{r.source}`, Similarity Score: `{r.score}`)**:\n> {r.content}\n\n"
                        assistant_content = fallback_msg
                        yield f"data: {json.dumps({'token': fallback_msg})}\n\n"
                    else:
                        err_msg = f"Connection Error: LLM server is offline, and no grounding context is available. Details: {str(openai_err)}"
                        yield f"data: {json.dumps({'token': err_msg})}\n\n"
            else:
                # If no OpenAI configured and Ollama fails, use dataset content as direct output
                if results:
                    fallback_msg = (
                        "🤖 **Note: LLM server is currently offline. Here is the direct matching content retrieved from your dataset:**\n\n"
                    )
                    for idx, r in enumerate(results):
                        fallback_msg += f"**Chunk {idx+1} (Source: `{r.source}`, Similarity Score: `{r.score}`)**:\n> {r.content}\n\n"
                    assistant_content = fallback_msg
                    yield f"data: {json.dumps({'token': fallback_msg})}\n\n"
                else:
                    if "ConnectionRefusedError" in err_str or "ConnectError" in err_str or "connect" in err_str.lower() or "attempts failed" in err_str.lower() or "503" in err_str:
                        err_msg = f"Connection Error: Local Ollama is offline at {settings.OLLAMA_BASE_URL}. Please start Ollama locally, or configure a valid OPENAI_API_KEY for automatic cloud fallback."
                    elif "not found" in err_str.lower():
                        err_msg = f"Model Error: Selected model '{data.model or 'llama3'}' was not found. Run 'ollama pull {data.model or 'llama3'}' to download it."
                    else:
                        err_msg = f"Ollama Error: {err_str}"
                    yield f"data: {json.dumps({'token': err_msg})}\n\n"

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

    return StreamingResponse(generate(), media_type="text/event-stream")


async def get_ollama_response(prompt: str, conv_id: str, db) -> str:
    """Non-streaming Ollama response using AsyncClient with OpenAI fallback"""
    try:
        client = AsyncClient(host=settings.OLLAMA_BASE_URL, headers={"bypass-tunnel-reminder": "true"})
        response = await client.chat(
            model="llama3",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        return response.get("message", {}).get("content", "")
    except Exception as e:
        logger.warning(f"Ollama non-streaming failed: {e}. Trying OpenAI fallback...")
        if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-..."):
            try:
                from openai import AsyncOpenAI
                openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                res = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
                )
                return res.choices[0].message.content or ""
            except Exception as openai_err:
                logger.error(f"OpenAI fallback failed: {openai_err}")

        return f"Error: Local Ollama is offline or model is not loaded. Details: {str(e)}"
