"""
RAG pipeline: document loading → chunking → embedding → vector store → retrieval → LLM answer
"""
from typing import List, Dict, Any, Optional
import logging
import os

from config import settings
from vector_db.store import VectorStore, get_embedding_model

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(
        self,
        index_id: str,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        backend: str = "chroma",
    ):
        self.index_id = index_id
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedder = get_embedding_model(embedding_model)
        self.vector_store = VectorStore(backend=backend, collection_name=f"index_{index_id}")

    async def ingest_file(self, file_path: str, file_type: str) -> int:
        """Load, chunk, embed and store a file. Returns chunk count."""
        text = await self._load_file(file_path, file_type)
        chunks = self._chunk_text(text)
        if not chunks:
            return 0

        logger.info(f"Embedding {len(chunks)} chunks for index {self.index_id}")
        embeddings = self.embedder.encode(chunks, show_progress_bar=False)

        ids = [f"{self.index_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"source": os.path.basename(file_path), "chunk_index": i, "file_type": file_type}
            for i in range(len(chunks))
        ]

        count = await self.vector_store.add_documents(
            documents=chunks,
            embeddings=embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings,
            metadatas=metadatas,
            ids=ids,
        )
        return count

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantic search over indexed documents"""
        query_embedding = self.embedder.encode(query)
        if hasattr(query_embedding, "tolist"):
            query_embedding = query_embedding.tolist()

        results = self.vector_store.query(query_embedding=query_embedding, top_k=top_k)
        return results

    async def answer(
        self,
        question: str,
        top_k: int = 5,
        model: str = "llama3",
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """RAG: retrieve + generate answer"""
        results = await self.search(question, top_k=top_k)
        context = "\n\n".join(
            [f"[Source: {r.get('metadata', {}).get('source', 'doc')}]\n{r['document']}"
             for r in results]
        )
        prompt = _build_rag_prompt(question, context)

        answer_text = await _call_llm(prompt, model=model, temperature=temperature)

        return {
            "answer": answer_text,
            "sources": results,
            "context_used": len(results),
            "model": model,
        }

    async def _load_file(self, file_path: str, file_type: str) -> str:
        """Load text from various file types"""
        if not os.path.exists(file_path):
            return ""

        try:
            if file_type in ("txt", "md"):
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()

            elif file_type == "pdf":
                try:
                    import PyPDF2
                    text = ""
                    with open(file_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            text += page.extract_text() + "\n"
                    return text
                except ImportError:
                    return "PDF content (install PyPDF2 for extraction)"

            elif file_type == "docx":
                try:
                    from docx import Document
                    doc = Document(file_path)
                    return "\n".join([p.text for p in doc.paragraphs])
                except ImportError:
                    return "DOCX content (install python-docx for extraction)"

            elif file_type in ("csv",):
                import pandas as pd
                df = pd.read_csv(file_path)
                return df.to_string(index=False)

            elif file_type in ("xlsx", "xls"):
                import pandas as pd
                df = pd.read_excel(file_path)
                return df.to_string(index=False)

        except Exception as e:
            logger.error(f"File loading error: {e}")

        return ""

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks"""
        if not text.strip():
            return []

        # Try langchain-text-splitters (standalone lightweight package)
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            return splitter.split_text(text)
        except ImportError:
            pass

        # Fallback: try legacy langchain import
        try:
            from langchain.text_splitter import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            return splitter.split_text(text)
        except ImportError:
            pass

        # Fallback: simple sliding window
        words = text.split()
        chunks = []
        step = self.chunk_size - self.chunk_overlap
        for i in range(0, len(words), step):
            chunk = " ".join(words[i : i + self.chunk_size])
            if chunk.strip():
                chunks.append(chunk)
        return chunks


def _build_rag_prompt(question: str, context: str) -> str:
    return f"""You are a helpful AI assistant. Use the following context to answer the question.
If the answer is not in the context, say so clearly.

Context:
{context}

Question: {question}

Answer:"""


async def _call_llm(
    prompt: str,
    model: str = "llama3",
    temperature: float = 0.3,
) -> str:
    """Call Ollama LLM with fallback"""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=60, headers={"bypass-tunnel-reminder": "true"}) as client:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False,
                      "options": {"temperature": temperature}},
            )
            if response.status_code == 200:
                return response.json().get("response", "")
    except Exception as e:
        logger.warning(f"Ollama LLM call failed in RAG pipeline: {e}. Trying OpenAI fallback...")

    # Fallback to OpenAI if configured
    if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-..."):
        try:
            from openai import AsyncOpenAI
            openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            res = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                stream=False
            )
            return res.choices[0].message.content or ""
        except Exception as openai_err:
            logger.error(f"OpenAI fallback in RAG pipeline failed: {openai_err}")

    # Final static fallback if all connections fail
    return (
        "Based on the retrieved context, I can provide the following answer: "
        "The documents contain relevant information about your query. "
        "Please connect Ollama or configure an OpenAI API key for full AI-powered answers."
    )
