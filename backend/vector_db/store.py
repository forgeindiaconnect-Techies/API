"""
Vector database abstraction supporting ChromaDB and FAISS.
"""
from typing import List, Dict, Any, Optional, Tuple
import logging
import os
import asyncio

from config import settings

logger = logging.getLogger(__name__)


def sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize metadata for ChromaDB: allow only str, int, float, bool. Remove None."""
    sanitized = {}
    for k, v in metadata.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            sanitized[k] = v
        else:
            sanitized[k] = str(v)
    return sanitized


class DummyEmbeddingFunction:
    """A dummy embedding function to prevent ChromaDB from initializing its heavy default ONNX model."""
    def __call__(self, texts: List[str]) -> List[List[float]]:
        # We compute embeddings ourselves and pass them explicitly, so this is never called
        return [[0.0] * 384 for _ in texts]


class VectorStore:
    """Unified interface for vector databases"""


    def __init__(self, backend: str = "chroma", collection_name: str = "default"):
        self.backend = backend
        self.collection_name = collection_name
        self._store = None
        self._initialized = False
        self._init_lock = None

    async def ensure_initialized(self):
        if self._initialized:
            return
        if not hasattr(self, "_init_lock") or self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._init_store)
            self._initialized = True

    def _init_store(self):
        if self.backend == "chroma":
            self._init_chroma()
        elif self.backend == "faiss":
            self._init_faiss()

    def _init_chroma(self):
        try:
            from services.chroma_service import ChromaManager
            self._client = ChromaManager.get_client()
        except (ImportError, ModuleNotFoundError) as e:
            logger.warning(f"ChromaDB not installed or unavailable ({e}). Falling back to FAISS/Mock.")
            self._client = None
            self._collection = None
            self.backend = "faiss"
            self._init_faiss()
            return
        
        # get_or_create_collection can also trigger database lock, run with sync retry loop
        max_attempts = 5
        delay = 2.0
        import time
        for attempt in range(max_attempts):
            try:
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                    embedding_function=DummyEmbeddingFunction()
                )
                logger.info(f"ChromaDB collection '{self.collection_name}' ready")
                return
            except Exception as e:
                err_msg = str(e).lower()
                if "database is locked" in err_msg or "db is locked" in err_msg or "code: 5" in err_msg or "locked" in err_msg:
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"ChromaDB collection init locked (attempt {attempt + 1}/{max_attempts}). "
                            f"Retrying in {delay} seconds..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"ChromaDB collection init locked. Max attempts reached. Error: {e}")
                        raise
                else:
                    raise

    def _init_faiss(self):
        self._faiss_dir = os.path.join(os.path.dirname(settings.CHROMA_PERSIST_DIR), "faiss_db")
        os.makedirs(self._faiss_dir, exist_ok=True)
        self._index_path = os.path.join(self._faiss_dir, f"{self.collection_name}.index")
        self._docs_path = os.path.join(self._faiss_dir, f"{self.collection_name}.json")

        try:
            import faiss  # type: ignore
            import json
            import numpy as np
            self._dimension = 384
            
            if os.path.exists(self._index_path) and os.path.exists(self._docs_path):
                self._index = faiss.read_index(self._index_path)
                with open(self._docs_path, "r", encoding="utf-8") as f:
                    self._docs = json.load(f)
                logger.info(f"Loaded FAISS index '{self.collection_name}' from disk with {len(self._docs)} documents.")
            else:
                self._index = faiss.IndexFlatL2(self._dimension)
                self._docs = []
                logger.info(f"Initialized new FAISS index '{self.collection_name}'")
        except ImportError:
            logger.warning("FAISS not installed; using mock")
            self._index = None
            self._docs = []

    async def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None,
    ) -> int:
        await self.ensure_initialized()
        if not ids:
            ids = [f"doc_{i}" for i in range(len(documents))]
        if not metadatas:
            metadatas = [{} for _ in documents]
        else:
            metadatas = [sanitize_metadata(meta) for meta in metadatas]

        if self.backend == "chroma" and self._collection:
            from services.chroma_service import run_with_retry_async
            def op():
                try:
                    self._collection.add(
                        documents=documents,
                        embeddings=embeddings,
                        metadatas=metadatas,
                        ids=ids,
                    )
                except Exception as add_err:
                    logger.warning(
                        f"ChromaDB add failed ({add_err}). Attempting fallback to upsert..."
                    )
                    try:
                        self._collection.upsert(
                            documents=documents,
                            embeddings=embeddings,
                            metadatas=metadatas,
                            ids=ids,
                        )
                    except Exception as upsert_err:
                        logger.error(f"ChromaDB upsert fallback failed: {upsert_err}")
                        raise
            await run_with_retry_async(op)
        elif self.backend == "faiss" and self._index is not None:
            import numpy as np
            import faiss  # type: ignore
            import json
            if embeddings and len(embeddings[0]) != self._dimension:
                self._dimension = len(embeddings[0])
                self._index = faiss.IndexFlatL2(self._dimension)
                logger.info(f"Re-initialized FAISS index with dimension {self._dimension}")
            arr = np.array(embeddings, dtype="float32")
            self._index.add(arr)
            self._docs.extend(
                [{"id": ids[i], "document": documents[i], "metadata": metadatas[i]}
                 for i in range(len(documents))]
            )
            # Persist FAISS to disk
            faiss.write_index(self._index, self._index_path)
            with open(self._docs_path, "w", encoding="utf-8") as f:
                json.dump(self._docs, f, ensure_ascii=False, indent=2)
        return len(documents)

    async def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        await self.ensure_initialized()
        if self.backend == "chroma" and self._collection:
            from services.chroma_service import run_with_retry_async
            def op():
                return self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                )
            results = await run_with_retry_async(op)
            out = []
            if results and results.get("ids") and len(results["ids"]) > 0:
                for i in range(len(results["ids"][0])):
                    out.append({
                        "id": results["ids"][0][i],
                        "document": results["documents"][0][i] if results.get("documents") else "",
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                        "score": 1 - results["distances"][0][i] if results.get("distances") else 0.0,
                    })
            return out

        elif self.backend == "faiss" and self._index is not None:
            import numpy as np
            if len(query_embedding) != self._dimension:
                logger.warning(f"FAISS dimension mismatch: query={len(query_embedding)} vs index={self._dimension}")
                return []
            arr = np.array([query_embedding], dtype="float32")
            D, I = self._index.search(arr, top_k)
            out = []
            for idx, dist in zip(I[0], D[0]):
                if idx >= 0 and idx < len(self._docs):
                    doc = self._docs[idx]
                    out.append({**doc, "score": float(1 / (1 + dist))})
            return out

        return []

    async def delete(self, ids: List[str]):
        await self.ensure_initialized()
        if self.backend == "chroma" and self._collection:
            from services.chroma_service import run_with_retry_async
            def op():
                self._collection.delete(ids=ids)
            await run_with_retry_async(op)

    async def count(self) -> int:
        await self.ensure_initialized()
        if self.backend == "chroma" and self._collection:
            from services.chroma_service import run_with_retry_async
            count_val = await run_with_retry_async(self._collection.count)
            return count_val or 0
        elif self.backend == "faiss" and self._index:
            return self._index.ntotal
        return 0


class MockVectorCollection:
    """In-memory mock for testing without ChromaDB"""
    _shared_collections = {}

    def __init__(self, collection_name: str = "default"):
        self.collection_name = collection_name
        if collection_name not in MockVectorCollection._shared_collections:
            MockVectorCollection._shared_collections[collection_name] = []
        self._data = MockVectorCollection._shared_collections[collection_name]

    def add(self, documents, embeddings, metadatas, ids):
        for i in range(len(ids)):
            self._data.append({
                "id": ids[i],
                "document": documents[i],
                "embedding": embeddings[i],
                "metadata": metadatas[i],
            })

    def query(self, query_embeddings, n_results=5):
        import random
        n = min(n_results, len(self._data))
        sample = self._data[:n] if self._data else []
        return {
            "ids": [[d["id"] for d in sample]],
            "documents": [[d["document"] for d in sample]],
            "metadatas": [[d["metadata"] for d in sample]],
            "distances": [[random.uniform(0.05, 0.4) for _ in sample]],
        }

    def delete(self, ids):
        self._data = [d for d in self._data if d["id"] not in ids]

    def count(self):
        return len(self._data)


class OpenAIEmbedder:
    """OpenAI embedding wrapper compatible with the sentence-transformers encode API"""
    def __init__(self, api_key: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)

    def encode(self, texts, **kwargs):
        import numpy as np
        # Handle string input
        if isinstance(texts, str):
            res = self.client.embeddings.create(
                input=[texts],
                model="text-embedding-3-small"
            )
            emb = res.data[0].embedding
            return np.array(emb, dtype="float32")
        
        # Handle list input
        res = self.client.embeddings.create(
            input=texts,
            model="text-embedding-3-small"
        )
        embs = [d.embedding for d in res.data]
        return np.array(embs, dtype="float32")


class HashingTFIDFEmbedder:
    """A lightweight, local embedder using signed feature hashing TF-IDF.
    Fits in < 1MB RAM, requires no PyTorch/SentenceTransformer, and gives true keyword similarity."""
    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def encode(self, texts, **kwargs):
        import numpy as np
        import hashlib
        import re

        is_single = isinstance(texts, str)
        if is_single:
            texts = [texts]

        stop_words = {"the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "to", "of", "in", "for", "on", "with", "at", "by"}

        embeddings = []
        for text in texts:
            words = re.findall(r'\w+', text.lower())
            tf = {}
            for w in words:
                if w not in stop_words:
                    tf[w] = tf.get(w, 0) + 1

            vec = np.zeros(self.dimension, dtype="float32")
            for w, freq in tf.items():
                h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
                idx = h % self.dimension
                sign = 1 if ((h >> 8) & 1) else -1
                vec[idx] += sign * freq

            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            embeddings.append(vec)

        if is_single:
            return embeddings[0]
        return np.array(embeddings, dtype="float32")


_shared_embedding_model = None

def get_embedding_model(model_name: str = "paraphrase-MiniLM-L3-v2"):
    """Load embedding model with fallbacks to OpenAI and HashingTFIDFEmbedder to ensure zero crashes"""
    global _shared_embedding_model

    # Map the old default to the new lightweight model name to ensure consistency
    if model_name == "all-MiniLM-L6-v2":
        model_name = "paraphrase-MiniLM-L3-v2"

    # 1. Try OpenAI if API key is present
    if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-..."):
        try:
            logger.info("Initializing OpenAIEmbedder...")
            return OpenAIEmbedder(api_key=settings.OPENAI_API_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize OpenAIEmbedder: {e}. Falling back to SentenceTransformer.")

    # 2. Try SentenceTransformer
    if _shared_embedding_model is not None:
        return _shared_embedding_model

    import os
    os.environ["ORT_LOGGING_LEVEL"] = "3"
    os.environ["ONNXRUNTIME_PROVIDERS"] = '["CPUExecutionProvider"]'
    os.environ["HF_HUB_HTTP_TIMEOUT"] = "15"
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            logger.info(f"Attempting to load SentenceTransformer model: {model_name} on CPU (attempt {attempt + 1}/{max_attempts})...")
            import gc
            try:
                import torch
                torch.set_num_threads(1)
                logger.info("Set PyTorch num_threads to 1 for CPU optimization.")
            except Exception as torch_err:
                logger.warning(f"Failed to set PyTorch num_threads: {torch_err}")
                
            from sentence_transformers import SentenceTransformer
            _shared_embedding_model = SentenceTransformer(model_name, device="cpu")
            
            # Clean up any unused references/memory immediately after loading
            gc.collect()
            logger.info(f"Using SentenceTransformer: {model_name}")
            return _shared_embedding_model
        except (MemoryError, RuntimeError, Exception) as e:
            logger.warning(f"Failed to load SentenceTransformer (attempt {attempt + 1}/{max_attempts}): {e}")
            if attempt < max_attempts - 1:
                import time
                time.sleep(2)
            else:
                logger.error(f"All attempts to load SentenceTransformer failed. Falling back to HashingTFIDFEmbedder.")
                return HashingTFIDFEmbedder(384)


async def get_embedding_model_async(model_name: str = "paraphrase-MiniLM-L3-v2"):
    """Load embedding model asynchronously on a separate thread pool to prevent blocking the event loop."""
    global _shared_embedding_model
    if _shared_embedding_model is not None:
        return _shared_embedding_model
    return await asyncio.to_thread(get_embedding_model, model_name)
