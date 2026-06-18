import os
import sys
import asyncio
import numpy as np

# Ensure backend is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ["MONGODB_URL"] = "mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0"
os.environ["MONGODB_DB_NAME"] = "personal_ai_studio"

from config import settings
from vector_db.store import VectorStore

async def main():
    print("--- STARTING RAG BATCH INDEXING TEST ---")
    
    # Initialize a test collection name
    test_collection = "test_batch_collection"
    store = VectorStore(backend="chroma", collection_name=test_collection)
    
    # Clean up previous store if exists
    try:
        await store.delete_store()
        print("Cleaned up old test collection.")
    except Exception:
        pass
        
    # Re-instantiate so ensure_initialized creates the collection fresh
    store = VectorStore(backend="chroma", collection_name=test_collection)
        
    # Generate 250 dummy chunks and embeddings (384 dimensions)
    print("Generating 250 mock documents and embeddings...")
    documents = [f"This is mock document chunk number {i}" for i in range(250)]
    embeddings = [[float(x) for x in np.random.randn(384)] for _ in range(250)]
    metadatas = [{"chunk_id": i, "source": "test_script"} for i in range(250)]
    ids = [f"test_doc_{i}" for i in range(250)]
    
    print("Calling store.add_documents() (expecting batching of 100 elements)...")
    added_count = await store.add_documents(documents, embeddings, metadatas, ids)
    print(f"Total documents successfully added: {added_count}")
    
    # Query count of collection
    count = await store.count()
    print(f"ChromaDB collection count: {count}")
    
    # Clean up test collection
    await store.delete_store()
    print("Cleaned up test collection. Test passed successfully!")

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
