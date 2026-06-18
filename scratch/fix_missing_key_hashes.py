import os
import sys
import asyncio
import logging
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_missing_key_hashes")

from database import connect_db, get_db

async def fix():
    await connect_db()
    db = get_db()
    
    col = db._db.api_keys
    count = 0
    async for doc in col.find({}):
        key_val = doc.get("key")
        key_hash = doc.get("key_hash")
        
        if key_val and not key_hash:
            computed_hash = hashlib.sha256(key_val.encode()).hexdigest()
            await col.update_one({"_id": doc["_id"]}, {"$set": {"key_hash": computed_hash}})
            logger.info(f"Updated key {doc['_id']} ('{doc.get('name')}') with computed key_hash")
            count += 1
            
    logger.info(f"Fixed {count} documents")

if __name__ == "__main__":
    asyncio.run(fix())
