import asyncio
import os
import sys
from fastapi import HTTPException

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db, get_db
from api.routes.chat import ensure_dataset_indexed

async def main():
    await connect_db()
    db = get_db()
    
    # We know 6a312095a69ee21d5f5fb024 is failed
    failed_id = "6a312095a69ee21d5f5fb024"
    
    # Let's test calling ensure_dataset_indexed on it
    try:
        print(f"Testing ensure_dataset_indexed for dataset ID: {failed_id}")
        await ensure_dataset_indexed(failed_id, db)
        print("Success? This was expected to fail!")
    except HTTPException as e:
        print(f"HTTPException caught successfully!")
        print(f"Status Code: {e.status_code}")
        print(f"Detail: {e.detail}")
    except Exception as e:
        print(f"Unexpected exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
