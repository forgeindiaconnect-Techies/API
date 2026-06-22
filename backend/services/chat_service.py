import logging
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


async def query_dataset_rag(index_id: str, question: str, top_k: int = 5, db = None, model: str = None) -> dict:
    """
    Retrieve matching context chunks from vector DB (Chroma/FAISS) and answer the user question.
    Falls back to a smart local context matcher if Ollama/OpenAI is offline.
    """
    # Detect simple greetings/chitchat/thanks to avoid returning forced database answers
    clean_question = question.strip().lower().rstrip("?.!")
    greetings = {"hi", "hello", "hey", "greetings", "good morning", "good afternoon", "howdy", "hola", "yo"}
    if clean_question in greetings:
        return {"answer": "Hello! How can I help you today?", "sources": []}
        
    how_are_you = {"how are you", "how is it going", "how's it going", "how are you doing", "how do you do"}
    if clean_question in how_are_you:
        return {"answer": "I'm doing great, thank you! How can I help you analyze your dataset today?", "sources": []}

    thanks = {"thanks", "thank you", "thank you so much", "ty", "cheers"}
    if clean_question in thanks:
        return {"answer": "You're very welcome! Let me know if you have any other questions.", "sources": []}
    # 1. Fetch index and dataset documents from DB
    index = await db.rag_indexes.find_one({"_id": get_id_query(index_id)})
    if not index:
        return {"answer": "Index not found.", "sources": []}

    # Verify indexing status
    status = index.get("status", "building")
    if status in ("building", "processing"):
        return {"answer": "Dataset indexing in progress...", "sources": []}
    
    logger.info("[OK] Dataset indexed")
        
    dataset_id = index.get("dataset_id")
    dataset = await db.datasets.find_one({"_id": get_id_query(dataset_id)})
    source_name = dataset.get("file_name") or dataset.get("name", "unknown")

    # 2. Get active embedder model (tiered fallback)
    try:
        embedder = await get_embedding_model_async(index.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2"))
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")
        return {"answer": "Embedding generation failed.", "sources": []}
        
    is_local_search = embedder.__class__.__name__ == "HashingTFIDFEmbedder"

    # 3. Generate query embedding
    import asyncio
    try:
        if hasattr(embedder, "encode"):
            if asyncio.iscoroutinefunction(embedder.encode):
                query_emb = await embedder.encode(question)
            else:
                query_emb = await asyncio.to_thread(embedder.encode, question)
        else:
            query_emb = []
            
        if hasattr(query_emb, "tolist"):
            query_emb = query_emb.tolist()
        logger.info("[OK] Embeddings generated")
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return {"answer": "Embedding generation failed.", "sources": []}

    # 4. Search dynamic persistent store (ChromaDB / FAISS)
    index_type = index.get("index_type", "chroma")
    try:
        store = VectorStore(backend=index_type, collection_name=index_id)
        logger.info("[OK] Chroma populated")
        raw_results = await store.query(query_emb, top_k=top_k)
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return {"answer": "No relevant context found.", "sources": []}

    sources = []
    for r in raw_results:
        sources.append({
            "content": r["document"],
            "score": float(r["score"]),
            "source": r["metadata"].get("source_file") or r["metadata"].get("source", source_name),
            "metadata": r["metadata"]
        })

    # Sort sources by similarity score descending
    sources.sort(key=lambda x: x["score"], reverse=True)

    # Log retrieved chunks count and similarity scores
    logger.info(f"Retrieved chunks count: {len(sources)}")
    logger.info(f"Similarity scores: {[s['score'] for s in sources]}")

    # Filter with similarity score threshold: 0.0 for TF-IDF keyword matching (fallback responder filters via exact text overlap), 0.30 for semantic
    threshold = 0.0 if is_local_search else 0.30
    valid_sources = [s for s in sources if s["score"] >= threshold]

    logger.info(f"Valid chunks count (above threshold {threshold}): {len(valid_sources)}")

    if not valid_sources:
        logger.info("LLM response status: Low Confidence. Returning: 'No relevant information found in the dataset'")
        return {
            "answer": "No relevant information found in the dataset",
            "sources": []
        }

    logger.info("[OK] Retrieval successful")

    # Construct clean prompt exactly as requested
    retrieved_chunks = "\n\n".join([f"Source: {s['source']}\nContent: {s['content']}" for s in valid_sources])
    
    prompt = f"""Context:
{retrieved_chunks}

Question:
{question}

Instructions:
Answer only using the context.
Do not return raw chunks.
Generate a natural language response."""

    # Log prompt sent to LLM
    logger.info(f"Prompt sent to LLM:\n{prompt}")
    logger.info("[OK] Context sent to LLM")

    answer_text = ""
    llm_connected = False

    # A: Try Ollama first
    global _ollama_online, _last_ollama_check
    current_time = time.time()
    if not _ollama_online and (current_time - _last_ollama_check > 300):
        # Retry connection status check every 5 minutes
        _ollama_online = True
        logger.info("Retrying Ollama connection check...")

    if _ollama_online:
        try:
            client = AsyncClient(
                host=settings.OLLAMA_BASE_URL,
                headers={"bypass-tunnel-reminder": "true"},
                timeout=1.5  # Fast 1.5 seconds connection timeout
            )
            res = await client.generate(
                model=model or settings.DEFAULT_MODEL or "llama3",
                prompt=prompt,
                stream=False
            )
            answer_text = res.get("response", "").strip()
            if answer_text:
                llm_connected = True
                logger.info("LLM response status: Success (Ollama)")
                logger.info("[OK] LLM response received")
        except Exception as ollama_err:
            _ollama_online = False
            _last_ollama_check = current_time
            logger.warning(f"Ollama connection failed (offline): {ollama_err}. Bypassing for subsequent requests. Trying fallback...")
    else:
        logger.info("Ollama is cached offline. Skipping connection attempt and trying fallbacks immediately.")
        
    # B: Try Google Gemini fallback if Ollama is unavailable (only when external APIs are enabled)
    if not llm_connected and settings.USE_EXTERNAL_APIS:
        import os
        gemini_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        if gemini_key and not gemini_key.startswith("your-"):
            try:
                logger.info("Attempting Google Gemini fallback (gemini-2.5-flash)...")
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                model_instance = genai.GenerativeModel("gemini-2.5-flash")
                
                try:
                    logger.info("Calling Gemini API asynchronously...")
                    res = await model_instance.generate_content_async(prompt)
                    answer_text = res.text.strip()
                except Exception as gemini_async_err:
                    logger.warning(f"Gemini async call failed: {gemini_async_err}. Trying synchronous call in executor...")
                    res = await asyncio.to_thread(model_instance.generate_content, prompt)
                    answer_text = res.text.strip()
                
                if answer_text:
                    llm_connected = True
                    logger.info("LLM response status: Success (Gemini)")
                    logger.info("[OK] LLM response received")
            except Exception as gemini_err:
                logger.error(f"Google Gemini fallback failed for RAG: {gemini_err}")
                logger.info(f"LLM response status: Failed (Gemini error: {gemini_err})")
        else:
            logger.info("LLM response status: GEMINI_API_KEY is missing or placeholder. Skipping Gemini fallback.")
    elif not llm_connected and not settings.USE_EXTERNAL_APIS:
        logger.info("LLM response status: Gemini fallback skipped (USE_EXTERNAL_APIS=false).")

    # C: Try OpenAI fallback if Gemini is unavailable or fails (only when external APIs are enabled)
    if not llm_connected and settings.USE_EXTERNAL_APIS:
        import os
        openai_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
        if openai_key and not openai_key.startswith("sk-..."):
            try:
                openai_client = AsyncOpenAI(api_key=openai_key)
                res = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
                )
                answer_text = res.choices[0].message.content.strip()
                if answer_text:
                    llm_connected = True
                    logger.info("LLM response status: Success (OpenAI)")
                    logger.info("[OK] LLM response received")
            except Exception as openai_err:
                logger.error(f"OpenAI fallback failed for RAG: {openai_err}")
                logger.info(f"LLM response status: Failed (OpenAI error: {openai_err})")
        else:
            logger.info("LLM response status: OpenAI API key is missing or invalid. Skipping OpenAI fallback.")
    elif not llm_connected and not settings.USE_EXTERNAL_APIS:
        logger.info("LLM response status: OpenAI fallback skipped (USE_EXTERNAL_APIS=false).")

    # D: If all are unavailable, fall back to Dataset-Only RAG Mode with natural language responder
    if not llm_connected:
        logger.info("LLM response status: Fallback (Offline contextual responder)")
        answer_text = generate_fallback_answer(question, valid_sources)
        logger.info("[OK] LLM response received")

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
