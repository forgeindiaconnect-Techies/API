import asyncio
import os
import sys

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db, get_db

async def main():
    await connect_db()
    db = get_db()
    
    print("Listing last 10 datasets in database:")
    async for d in db.datasets.find().sort("created_at", -1).limit(10):
        print(f"ID: {d['_id']}")
        print(f"  Name: {d.get('name') or d.get('file_name')}")
        print(f"  Status: {d.get('status')}")
        print(f"  Cloudinary URL: {d.get('cloudinary_url')}")
        print(f"  Error Message: {d.get('error_message')}")
        print(f"  Created At: {d.get('created_at')}")
        print(f"  File Path: {d.get('file_path')}")
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
