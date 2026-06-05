import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db
from vector_db.store import VectorStore, get_embedding_model

async def main():
    await connect_db()
    db = get_db()
    
    dataset = await db.datasets.find_one({"name": "dialogs.txt"})
    if not dataset:
        print("Dataset not found!")
        return
        
    index = await db.rag_indexes.find_one({"dataset_id": str(dataset["_id"])})
    if not index:
        print("Index not found!")
        return
        
    index_id = str(index["_id"])
    print(f"Index ID: {index_id}")
    
    store = VectorStore(backend=index.get("index_type", "chroma"), collection_name=index_id)
    print(f"Store count: {store.count()}")
    
    # Let's inspect mock collection details
    if hasattr(store, "_collection"):
        collection = store._collection
        if hasattr(collection, "_data"):
            print(f"Mock Collection Data Length: {len(collection._data)}")
            if len(collection._data) > 0:
                print("First 3 documents in mock store:")
                for d in collection._data[:3]:
                    print(f"- ID: {d['id']}, Doc preview: {d['document'][:60]}...")
            else:
                print("Mock collection data is empty!")
                
    # Let's query the vector store
    from api.routes.rag import query_vector_store
    results = await query_vector_store(index_id, "What is AI Studio?", top_k=3, db=db)
    print(f"Query results: {len(results)}")
    for r in results:
        print(f"- Score: {r.score}, Content: {r.content[:100]}..., Source: {r.source}")

if __name__ == "__main__":
    asyncio.run(main())
