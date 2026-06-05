import asyncio
import sys
import os
from bson import ObjectId

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db

async def main():
    await connect_db()
    db = get_db()
    
    # Reset dialogs.txt index
    res = await db.rag_indexes.update_one(
        {"_id": ObjectId("6a22a793fa689261146412ad")},
        {"$set": {"status": "ready", "error": None}}
    )
    print(f"Index reset result: {res.modified_count} documents updated.")

if __name__ == '__main__':
    asyncio.run(main())
