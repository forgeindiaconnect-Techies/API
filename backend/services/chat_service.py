import logging
from typing import Optional, List, Dict, Any
from database import get_db
from auth.utils import get_id_query
from vector_db.store import VectorStore, get_embedding_model, get_embedding_model_async
from ollama import AsyncClient
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

import time

# Cache Ollama connection status to prevent connection request hangs when offline
_ollama_online = True
_last_ollama_check = 0.0

def generate_fallback_answer(question: str, valid_sources: list) -> str:
    """
    Generate a natural language fallback response by extracting sentences
    that match the user question from the retrieved chunks rather than returning
    raw paragraphs directly.
    """
    import re
    
    # 1. Extract query words/keywords (supporting words >= 2 chars)
    stopwords = {
        "who", "what", "where", "when", "why", "how", "is", "are", "was", "were", 
        "the", "a", "an", "and", "or", "to", "in", "of", "for", "on", "with", "at", "by",
        "i", "me", "my", "we", "our", "you", "your", "he", "him", "his", "she", "her", 
        "it", "its", "they", "them", "their", "am", "be", "been", "do", "did", "does",
        "go", "goes", "went", "has", "have", "had", "will", "would", "shall", "should",
        "can", "could", "may", "might", "must", "us", "so", "as", "if", "but"
    }
    q_words = re.findall(r'\b\w{2,}\b', question.lower())
    keywords = {w for w in q_words if w not in stopwords}
    
    # 2. Extract sentences from source text chunks
    sentences = []
    for s in valid_sources:
        text = s["content"]
        chunks = re.split(r'(?<=[.!?])\s+', text)
        for chunk in chunks:
            if chunk.strip():
                sentences.append((chunk.strip(), s["source"]))
                
    best_sentences = []
    for sentence, source in sentences:
        s_words = re.findall(r'\b\w{2,}\b', sentence.lower())
        overlap = len(keywords.intersection(s_words))
        if overlap > 0:
            best_sentences.append((sentence, overlap, source))
            
    if not best_sentences:
        return "No relevant information found in the dataset"
        
    best_sentences.sort(key=lambda x: x[1], reverse=True)
    top_matches = [b[0] for b in best_sentences[:2]]
    joined_text = " ".join(top_matches)
    
    return f"According to the dataset, {joined_text}"


async def generate_chat_response(messages: list, db, model: str = None, valid_sources: list = None) -> str:
    """
    Unified chat generator that interfaces with LLMs (Custom, Ollama, Gemini, OpenAI).
    Falls back gracefully if models are offline.
    """
    llm_connected = False
    answer_text = ""

    # Extract last user prompt
    last_prompt = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            last_prompt = msg["content"]
            break

    # Format prompt for custom model / Gemini
    formatted_prompt = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            formatted_prompt += f"System: {content}\n\n"
        elif role == "user":
            formatted_prompt += f"User: {content}\n\n"
        elif role == "assistant":
            formatted_prompt += f"Assistant: {content}\n\n"
    formatted_prompt += "Assistant: "

    # 1. Custom trained model inference
    is_custom_model = False
    custom_model_id = None
    if model:
        try:
            m_doc = await db.models.find_one({"_id": get_id_query(model)})
            if m_doc:
                base_name = m_doc.get("base_model", "")
                if base_name.startswith("custom-") or base_name.startswith("gpt-"):
                    is_custom_model = True
                    custom_model_id = str(m_doc["_id"])
        except Exception as e:
            logger.warning(f"Error checking custom model: {e}")

    if is_custom_model and custom_model_id:
        try:
            logger.info(f"Routing to custom model {custom_model_id}")
            from models import PredictRequest
            from api.routes.models_router import perform_model_inference
            
            predict_req = PredictRequest(
                model_id=custom_model_id,
                input={"prompt": formatted_prompt},
                parameters={"max_new_tokens": 150, "temperature": 0.7, "top_k": 20}
            )
            
            class DummyRequest:
                class State:
                    api_key = None
                state = State()
                
            pred_response = await perform_model_inference(
                model_id=custom_model_id,
                predict_request=predict_req,
                http_request=DummyRequest(),
                db=db
            )
            ans = pred_response.prediction.get("text", "").strip()
            if ans:
                answer_text = ans
                llm_connected = True
                logger.info("Custom model prediction successful")
        except Exception as e:
            logger.error(f"Custom model inference failed: {e}")

    # 2. Ollama Chat
    if not llm_connected:
        global _ollama_online, _last_ollama_check
        current_time = time.time()
        if not _ollama_online and (current_time - _last_ollama_check > 300):
            _ollama_online = True

        if _ollama_online:
            try:
                client = AsyncClient(
                    host=settings.OLLAMA_BASE_URL,
                    headers={"bypass-tunnel-reminder": "true"},
                    timeout=1.5
                )
                ollama_model = model if model and not is_custom_model else settings.DEFAULT_MODEL or "llama3"
                res = await client.chat(
                    model=ollama_model,
                    messages=messages,
                    options={"temperature": 0.7}
                )
                answer_text = res.get("message", {}).get("content", "").strip()
                if answer_text:
                    llm_connected = True
                    logger.info("Ollama response generated successfully")
            except Exception as ollama_err:
                _ollama_online = False
                _last_ollama_check = current_time
                logger.warning(f"Ollama chat failed: {ollama_err}")

    # 3. Google Gemini fallback
    if not llm_connected:
        import os
        gemini_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        if gemini_key and not gemini_key.startswith("your-"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                model_instance = genai.GenerativeModel("gemini-2.5-flash")
                
                try:
                    res = await model_instance.generate_content_async(formatted_prompt)
                    answer_text = res.text.strip()
                except Exception:
                    res = await asyncio.to_thread(model_instance.generate_content, formatted_prompt)
                    answer_text = res.text.strip()
                
                if answer_text:
                    llm_connected = True
                    logger.info("Gemini response generated successfully")
            except Exception as gemini_err:
                logger.error(f"Gemini generation failed: {gemini_err}")

    # 4. OpenAI fallback
    if not llm_connected:
        import os
        openai_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
        if openai_key and not openai_key.startswith("sk-..."):
            try:
                openai_client = AsyncOpenAI(api_key=openai_key)
                res = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.7,
                    stream=False
                )
                answer_text = res.choices[0].message.content.strip()
                if answer_text:
                    llm_connected = True
                    logger.info("OpenAI response generated successfully")
            except Exception as openai_err:
                logger.error(f"OpenAI generation failed: {openai_err}")

    # 5. Local/Offline fallback responder
    if not llm_connected:
        if valid_sources:
            logger.info("LLM offline. Generating local keyword matches from retrieved sources.")
            answer_text = generate_fallback_answer(last_prompt, valid_sources)
        else:
            # Check user name request
            if "what is my name" in last_prompt.lower() or "who am i" in last_prompt.lower():
                for m in messages:
                    if m["role"] == "system" and "User Profile Memory" in m["content"]:
                        for line in m["content"].split("\n"):
                            if line.startswith("- Name:"):
                                name = line.replace("- Name:", "").strip()
                                return f"Your name is {name}."
                return "I don't know your name yet. You can tell me by saying 'I am [name]'."
            
            # Simple chitchat fallbacks
            clean_prompt = last_prompt.strip().lower().rstrip("?.!")
            if clean_prompt in {"hi", "hello", "hey", "greetings"}:
                return "Hello! How can I help you today?"
            elif clean_prompt in {"how are you", "how's it going"}:
                return "I'm doing great, thank you! How are you?"
            elif clean_prompt in {"thanks", "thank you"}:
                return "You're very welcome!"
                
            return "I'm currently running in offline fallback mode and couldn't reach the AI model."

    return answer_text


async def query_dataset_rag(
    index_id: Optional[str],
    question: str,
    top_k: int = 5,
    db = None,
    model: str = None,
    chat_history: list = None,
    user_id: str = None
) -> dict:
    """
    Retrieve matching context chunks from vector DB if available.
    Generates response using chat history, user memory, and optionally RAG context.
    Falls back to normal LLM conversation if RAG has low confidence.
    """
    import asyncio
    
    # 1. Fetch user's memory (e.g. name) and extract/save if stated in the current question
    user_name = None
    if user_id and db:
        try:
            import re
            from datetime import datetime
            # First, check if user states their name in the current question
            patterns = [
                r"\bi\s+am\s+([A-Za-z]+)",
                r"\bi'm\s+([A-Za-z]+)",
                r"\bmy\s+name\s+is\s+([A-Za-z]+)"
            ]
            name_found = None
            for pattern in patterns:
                match = re.search(pattern, question, re.IGNORECASE)
                if match:
                    name_found = match.group(1).strip().capitalize()
                    break
            
            if name_found:
                await db.user_memory.update_one(
                    {"user_id": str(user_id)},
                    {"$set": {"name": name_found, "updated_at": datetime.utcnow()}},
                    upsert=True
                )
                user_name = name_found
                logger.info(f"Extracted and saved name '{name_found}' for user_id '{user_id}'")
            else:
                user_mem = await db.user_memory.find_one({"user_id": str(user_id)})
                if user_mem:
                    user_name = user_mem.get("name")
        except Exception as e:
            logger.warning(f"Failed to fetch or save user memory: {e}")

    valid_sources = []
    source_name = "unknown"

    # 2. Fetch RAG context if index_id is provided
    if index_id and db:
        try:
            index = await db.rag_indexes.find_one({"_id": get_id_query(index_id)})
            if index:
                status = index.get("status", "building")
                if status not in ("building", "processing"):
                    dataset_id = index.get("dataset_id")
                    dataset = await db.datasets.find_one({"_id": get_id_query(dataset_id)})
                    if dataset:
                        source_name = dataset.get("file_name") or dataset.get("name", "unknown")

                    embedder = await get_embedding_model_async(index.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2"))
                    is_local_search = embedder.__class__.__name__ == "HashingTFIDFEmbedder"

                    if hasattr(embedder, "encode"):
                        if asyncio.iscoroutinefunction(embedder.encode):
                            query_emb = await embedder.encode(question)
                        else:
                            query_emb = await asyncio.to_thread(embedder.encode, question)
                    else:
                        query_emb = []
                        
                    if hasattr(query_emb, "tolist"):
                        query_emb = query_emb.tolist()

                    index_type = index.get("index_type", "chroma")
                    store = VectorStore(backend=index_type, collection_name=index_id)
                    raw_results = await store.query(query_emb, top_k=top_k)

                    sources = []
                    for r in raw_results:
                        sources.append({
                            "content": r["document"],
                            "score": float(r["score"]),
                            "source": r["metadata"].get("source_file") or r["metadata"].get("source", source_name),
                            "metadata": r["metadata"]
                        })

                    sources.sort(key=lambda x: x["score"], reverse=True)

                    threshold = 0.0 if is_local_search else 0.30
                    valid_sources = [s for s in sources if s["score"] >= threshold]
                    logger.info(f"RAG search found {len(valid_sources)} valid sources above threshold {threshold}")
        except Exception as e:
            logger.error(f"RAG search error: {e}", exc_info=True)

    # 3. Construct system prompt
    system_prompt = "You are a helpful AI assistant. You behave like ChatGPT."
    if user_name:
        system_prompt += f"\nUser Profile Memory:\n- Name: {user_name}\nAlways use this name when asked about their name or who they are."

    if valid_sources:
        retrieved_chunks = "\n\n".join([f"Source: {s['source']}\nContent: {s['content']}" for s in valid_sources])
        system_prompt += f"\n\nUse the following context from the uploaded dataset to answer the user's question. If the question is not related to the context, answer using your general knowledge.\n\nContext:\n{retrieved_chunks}"

    # 4. Prepare message list
    if not chat_history:
        chat_history = [{"role": "user", "content": question}]

    messages = [{"role": "system", "content": system_prompt}] + chat_history

    # 5. Generate LLM response
    answer_text = await generate_chat_response(messages, db, model, valid_sources)

    from models import SearchResult
    pydantic_sources = [
        SearchResult(
            content=s["content"],
            score=s["score"],
            source=s["source"],
            metadata=s["metadata"]
        ) for s in valid_sources
    ]

    return {
        "answer": answer_text,
        "sources": pydantic_sources
    }

