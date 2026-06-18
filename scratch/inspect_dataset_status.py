import asyncio
import os
import sys

# Add backend directory to sys.path so we can import modules
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from database import connect_db, get_db
from api.routes.datasets import fmt_dataset

async def main():
    await connect_db()
    db = get_db()
    
    # Query the dataset document from DB
    d = await db.datasets.find_one({"_id": "6a2695fa1f1de9768349fdfe"})
    if not d:
        print("Dataset not found!")
        return
        
    print("Database status:", d.get("status"))
    print("Formatted dataset API status:", fmt_dataset(d)["status"])

if __name__ == "__main__":
    asyncio.run(main())
