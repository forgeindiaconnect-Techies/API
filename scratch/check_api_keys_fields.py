import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("check_api_keys_fields")

from database import connect_db, get_db

async def check():
    await connect_db()
    db = get_db()
    
    col = db._db.api_keys
    async for doc in col.find({}):
        allowed_ds = doc.get("allowed_datasets")
        allowed_md = doc.get("allowed_models")
        
        # Log if allowed_datasets or allowed_models is None
        if allowed_ds is None or allowed_md is None:
            logger.info(f"Doc ID: {doc['_id']}, name: {doc.get('name')}")
            logger.info(f"  allowed_datasets: {allowed_ds} (type: {type(allowed_ds)})")
            logger.info(f"  allowed_models: {allowed_md} (type: {type(allowed_md)})")

if __name__ == "__main__":
    asyncio.run(check())
