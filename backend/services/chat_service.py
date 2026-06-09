import logging
from database import get_db
from vector_db.store import VectorStore, get_embedding_model
from ollama import AsyncClient
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

def generate_fallback_answer(question: str, valid_sources: list) -> str:
    """
    Generate a natural language fallback response by extracting sentences
    that match the user question from the retrieved chunks rather than returning
    raw paragraphs directly.
    """
    import re
    
    # 1. Extract query words/keywords
    stopwords = {"who", "what", "where", "when", "why", "how", "is", "are", "was", "were", "the", "a", "an", "and", "or", "to", "in", "of", "for", "on", "with", "at", "by"}
    q_words = re.findall(r'\b\w{3,}\b', question.lower())
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
        s_words = re.findall(r'\b\w{3,}\b', sentence.lower())
        overlap = len(keywords.intersection(s_words))
        if overlap > 0:
            best_sentences.append((sentence, overlap, source))
            
    if not best_sentences:
        return "No relevant information found in the dataset"
        
    best_sentences.sort(key=lambda x: x[1], reverse=True)
    top_matches = [b[0] for b in best_sentences[:2]]
    joined_text = " ".join(top_matches)
    
    return f"According to the dataset, {joined_text}"


async def query_dataset_rag(index_id: str, question: str, top_k: int = 5, db = None) -> dict:
    """
    Retrieve matching context chunks from vector DB (Chroma/FAISS) and answer the user question.
    Falls back to a smart local context matcher if Ollama/OpenAI is offline.
    """
    # 1. Fetch index and dataset documents from DB
    index = await db.rag_indexes.find_one({"_id": index_id})
    if not index:
        return {"answer": "Index not found.", "sources": []}

    # Verify indexing status
    status = index.get("status", "building")
    if status in ("building", "processing"):
        return {"answer": "Dataset indexing in progress...", "sources": []}
    
    logger.info("✓ Dataset indexed")
        
    dataset_id = index.get("dataset_id")
    dataset = await db.datasets.find_one({"_id": dataset_id})
    source_name = dataset.get("file_name") or dataset.get("name", "unknown")

    # 2. Get active embedder model (tiered fallback)
    try:
        embedder = get_embedding_model(index.get("embedding_model", "paraphrase-MiniLM-L3-v2"))
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
        logger.info("✓ Embeddings generated")
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return {"answer": "Embedding generation failed.", "sources": []}

    # 4. Search dynamic persistent store (ChromaDB / FAISS)
    index_type = index.get("index_type", "chroma")
    try:
        store = VectorStore(backend=index_type, collection_name=index_id)
        logger.info("✓ Chroma populated")
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

    # Filter with similarity score threshold: 0.20 for TF-IDF keyword matching, 0.30 for semantic
    threshold = 0.20 if is_local_search else 0.30
    valid_sources = [s for s in sources if s["score"] >= threshold]

    logger.info(f"Valid chunks count (above threshold {threshold}): {len(valid_sources)}")

    if not valid_sources:
        logger.info("LLM response status: Low Confidence. Returning: 'No relevant information found in the dataset'")
        return {
            "answer": "No relevant information found in the dataset",
            "sources": []
        }

    logger.info("✓ Retrieval successful")

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
    logger.info("✓ Context sent to LLM")

    answer_text = ""
    llm_connected = False

    # A: Try Ollama first
    try:
        client = AsyncClient(host=settings.OLLAMA_BASE_URL, headers={"bypass-tunnel-reminder": "true"})
        res = await client.generate(
            model=settings.DEFAULT_MODEL or "llama3",
            prompt=prompt,
            stream=False
        )
        answer_text = res.get("response", "").strip()
        if answer_text:
            llm_connected = True
            logger.info("LLM response status: Success (Ollama)")
            logger.info("✓ LLM response received")
    except Exception as ollama_err:
        logger.warning(f"Ollama RAG generate failed: {ollama_err}. Trying OpenAI fallback...")
        
    # B: Try OpenAI fallback if Ollama is unavailable
    if not llm_connected:
        if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-..."):
            try:
                openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                res = await openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
                )
                answer_text = res.choices[0].message.content.strip()
                if answer_text:
                    llm_connected = True
                    logger.info("LLM response status: Success (OpenAI)")
                    logger.info("✓ LLM response received")
            except Exception as openai_err:
                logger.error(f"OpenAI fallback failed for RAG: {openai_err}")
                logger.info(f"LLM response status: Failed (OpenAI error: {openai_err})")
        else:
            logger.info("LLM response status: OpenAI API key is missing or invalid. Skipping OpenAI fallback.")

    # C: If both are unavailable, fall back to Dataset-Only RAG Mode with natural language responder
    if not llm_connected:
        logger.info("LLM response status: Fallback (Offline contextual responder)")
        answer_text = generate_fallback_answer(question, valid_sources)
        logger.info("✓ LLM response received")

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
