import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_api_key_creation")

from database import connect_db, get_db
from api.routes.api_keys import create_api_key
from models import ApiKeyCreate

async def test():
    await connect_db()
    db = get_db()
    
    current_user = {
        "_id": "6a2a8ce94af4f2be830e5d28",
        "username": "demo@aistudio.com",
        "email": "demo@aistudio.com"
    }
    
    data = ApiKeyCreate(
        name="Test Creation Key",
        scopes=["chat"],
        rate_limit=10000,
        allowed_datasets=["test_both_original (1).txt"],
        allowed_models=["Data"]
    )
    
    try:
        res = await create_api_key(data=data, current_user=current_user)
        logger.info("Successfully created API Key!")
        logger.info(f"Response: {res}")
    except Exception as e:
        logger.error("Failed to create API key:", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test())
