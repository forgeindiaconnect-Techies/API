import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("check_index_details")

from database import connect_db, get_db

async def check():
    await connect_db()
    db = get_db()
    
    col = db._db.api_keys
    indexes = await col.index_information()
    for name, info in indexes.items():
        logger.info(f"Index name: {name}")
        logger.info(f"  Info: {info}")

if __name__ == "__main__":
    asyncio.run(check())
