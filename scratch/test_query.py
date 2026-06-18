import asyncio
import os
import sys

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.append(backend_dir)

from services.chat_service import query_dataset_rag
from vector_db.store import VectorStore, get_embedding_model_async

class MockDBCollection:
    def __init__(self, doc):
        self.doc = doc
    async def find_one(self, query, *args, **kwargs):
        return self.doc

class MockDB:
    def __init__(self, index_doc, dataset_doc):
        self.rag_indexes = MockDBCollection(index_doc)
        self.datasets = MockDBCollection(dataset_doc)

async def main():
    # Force low memory mode to use HashingTFIDFEmbedder (matching Render)
    os.environ["LOW_MEMORY_MODE"] = "true"
    
    # Local ChromaDB collection that exists
    index_id = "6a29308b560ff62912746135"

    question = "how are you doing today?"
    
    # Mock documents that the RAG service looks up
    index_doc = {
        "_id": index_id,
        "status": "ready",
        "dataset_id": "dataset_1",
        "embedding_model": "paraphrase-MiniLM-L3-v2",
        "index_type": "chroma"
    }
    dataset_doc = {
        "_id": "dataset_1",
        "file_name": "dialogs.txt",
        "name": "dialogs.txt"
    }
    
    mock_db = MockDB(index_doc, dataset_doc)
    
    print(f"Testing RAG query on local Chroma index '{index_id}' with question: '{question}'...")
    res = await query_dataset_rag(index_id, question, top_k=5, db=mock_db)
    
    print("\n=== RAG RESULT ===")
    print("Answer:", res.get("answer"))
    print("Sources count:", len(res.get("sources", [])))
    for s in res.get("sources", []):
        print(f"- Score: {s.score:.4f} | Source: {s.source} | Content: {s.content[:120]}")

    print("\n=== RAW VECTORSTORE QUERY ===")
    embedder = await get_embedding_model_async("paraphrase-MiniLM-L3-v2")
    query_emb = await asyncio.to_thread(embedder.encode, question)
    if hasattr(query_emb, "tolist"):
        query_emb = query_emb.tolist()
        
    store = VectorStore(backend="chroma", collection_name=index_id)
    raw_results = await store.query(query_emb, top_k=5)
    for r in raw_results:
        print(f"- Score: {r['score']:.4f} | Content: {r['document'][:150]}")

if __name__ == "__main__":
    asyncio.run(main())
