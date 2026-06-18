import asyncio
import httpx
import os
import sys

# Add backend directory to sys.path so we can import modules
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db, get_db

async def main():
    await connect_db()
    db = get_db()
    
    # 1. Inspect RAG Indexes in DB
    print("=== MongoDB RAG Indexes ===")
    cursor = db.rag_indexes.find()
    async for doc in cursor:
        print(f"ID: {doc['_id']}, Name: {doc.get('name')}, Status: {doc.get('status')}, Chunk count: {doc.get('chunk_count')}")

    # 2. Query Deployed API on Render
    print("\n=== Deployed Render API (rag/indexes) ===")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Note: /rag/indexes requires authentication, but we can check if it responds
            res = await client.get("https://d-ai-7k8h.onrender.com/api/v1/rag/indexes")
            print("Status code:", res.status_code)
            print("Response:", res.text[:200])
    except Exception as e:
        print("Failed to query Render API:", e)

if __name__ == "__main__":
    asyncio.run(main())
