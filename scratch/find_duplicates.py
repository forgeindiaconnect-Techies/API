import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("find_duplicates")

from database import connect_db, get_db

async def find():
    await connect_db()
    db = get_db()
    
    col = db._db.api_keys
    
    # Check duplicate key_hash
    hashes = {}
    async for doc in col.find({}):
        kh = doc.get("key_hash")
        if kh:
            hashes[kh] = hashes.get(kh, 0) + 1
            
    dup_hashes = {k: v for k, v in hashes.items() if v > 1}
    logger.info(f"Duplicate key_hash: {dup_hashes}")
    
    # Check duplicate keys
    keys = {}
    async for doc in col.find({}):
        k = doc.get("key")
        if k:
            keys[k] = keys.get(k, 0) + 1
            
    dup_keys = {k: v for k, v in keys.items() if v > 1}
    logger.info(f"Duplicate keys: {dup_keys}")

if __name__ == "__main__":
    asyncio.run(find())
