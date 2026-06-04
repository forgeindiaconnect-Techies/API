"""
Vector database abstraction supporting ChromaDB and FAISS.
"""
from typing import List, Dict, Any, Optional, Tuple
import logging
import os

from config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Unified interface for vector databases"""

    def __init__(self, backend: str = "chroma", collection_name: str = "default"):
        self.backend = backend
        self.collection_name = collection_name
        self._store = None
        self._init_store()

    def _init_store(self):
        if self.backend == "chroma":
            self._init_chroma()
        elif self.backend == "faiss":
            self._init_faiss()

    def _init_chroma(self):
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"ChromaDB collection '{self.collection_name}' ready")
        except ImportError:
            logger.warning("ChromaDB not installed; using in-memory mock")
            self._collection = MockVectorCollection()

    def _init_faiss(self):
        try:
            import faiss
            import numpy as np
            self._dimension = 384
            self._index = faiss.IndexFlatL2(self._dimension)
            self._docs: List[Dict] = []
            logger.info("FAISS index ready")
        except ImportError:
            logger.warning("FAISS not installed; using mock")
            self._index = None

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None,
    ) -> int:
        if not ids:
            ids = [f"doc_{i}" for i in range(len(documents))]
        if not metadatas:
            metadatas = [{} for _ in documents]

        if self.backend == "chroma" and self._collection:
            self._collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )
        elif self.backend == "faiss" and self._index is not None:
            import numpy as np
            arr = np.array(embeddings, dtype="float32")
            self._index.add(arr)
            self._docs.extend(
                [{"id": ids[i], "document": documents[i], "metadata": metadatas[i]}
                 for i in range(len(documents))]
            )
        return len(documents)

    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if self.backend == "chroma" and self._collection:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
            )
            out = []
            for i in range(len(results["ids"][0])):
                out.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": 1 - results["distances"][0][i],  # cosine → similarity
                })
            return out

        elif self.backend == "faiss" and self._index is not None:
            import numpy as np
            arr = np.array([query_embedding], dtype="float32")
            D, I = self._index.search(arr, top_k)
            out = []
            for idx, dist in zip(I[0], D[0]):
                if idx < len(self._docs):
                    doc = self._docs[idx]
                    out.append({**doc, "score": float(1 / (1 + dist))})
            return out

        return []

    def delete(self, ids: List[str]):
        if self.backend == "chroma" and self._collection:
            self._collection.delete(ids=ids)

    def count(self) -> int:
        if self.backend == "chroma" and self._collection:
            return self._collection.count()
        elif self.backend == "faiss" and self._index:
            return self._index.ntotal
        return 0


class MockVectorCollection:
    """In-memory mock for testing without ChromaDB"""

    def __init__(self):
        self._data: List[Dict] = []

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


def get_embedding_model(model_name: str = "all-MiniLM-L6-v2"):
    """Load sentence-transformers embedding model"""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_name)
    except ImportError:
        logger.warning("sentence-transformers not installed; returning mock embedder")
        return MockEmbedder()


class MockEmbedder:
    def encode(self, texts, **kwargs):
        import random
        if isinstance(texts, str):
            return [random.uniform(-1, 1) for _ in range(384)]
        return [[random.uniform(-1, 1) for _ in range(384)] for _ in texts]
