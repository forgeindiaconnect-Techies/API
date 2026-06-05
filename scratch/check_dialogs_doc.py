import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db

async def main():
    await connect_db()
    db = get_db()
    
    print("--- DATASETS ---")
    async for d in db.datasets.find({}):
        print(f"ID: {d['_id']}, Name: {d.get('name')}, File Path: {d.get('file_path')}, GridFS ID: {d.get('gridfs_id')}")
        
    print("\n--- RAG INDEXES ---")
    async for idx in db.rag_indexes.find({}):
        print(f"ID: {idx['_id']}, Name: {idx.get('name')}, Dataset ID: {idx.get('dataset_id')}, Status: {idx.get('status')}, Error: {idx.get('error')}")

if __name__ == '__main__':
    asyncio.run(main())
