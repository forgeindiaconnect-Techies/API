import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db

async def main():
    await connect_db()
    db = get_db()
    
    dataset = await db.datasets.find_one({"name": "dialogs.txt"})
    if dataset:
        print("Dataset:")
        print(f"  Name: {dataset['name']}")
        print(f"  Status: {dataset.get('status')}")
        print(f"  Path: {dataset.get('file_path')}")
        print(f"  Error: {dataset.get('error_message')}")
        
        index = await db.rag_indexes.find_one({"dataset_id": str(dataset["_id"])})
        if index:
            print("Index:")
            print(f"  Name: {index.get('name')}")
            print(f"  Status: {index.get('status')}")
            print(f"  Chunks: {index.get('chunk_count')}")
            print(f"  Error: {index.get('error')}")
        else:
            print("No index found for dataset ID:", dataset["_id"])
    else:
        print("Dataset not found!")

if __name__ == "__main__":
    asyncio.run(main())
