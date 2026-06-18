import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inspect_api_keys")

from database import connect_db, get_db

async def inspect():
    await connect_db()
    db = get_db()
    
    col = db._db.api_keys
    count = await col.count_documents({})
    logger.info(f"Total API keys count: {count}")
    
    # print keys
    async for key_doc in col.find({}):
        logger.info(f"ID: {key_doc.get('_id')}, name: {key_doc.get('name')}, has_key: {'key' in key_doc}, key_value: {key_doc.get('key')}, has_key_hash: {'key_hash' in key_doc}")

if __name__ == "__main__":
    asyncio.run(inspect())
