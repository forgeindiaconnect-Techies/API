import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("test_via_testclient")

import httpx
from main import app
from database import connect_db, get_db, disconnect_db
from api.routes.api_keys import generate_api_key

async def test_flow():
    # 1. Connect database
    logger.info("Connecting to DB...")
    await connect_db()
    db = get_db()
    
    # Clean up and setup a test API key
    await db.api_keys.delete_many({"name": "Test Client Key"})
    
    user_id = "6a2a8ce94af4f2be830e5d28"
    
    raw_key, prefix, key_hash = generate_api_key()
    doc = {
        "user_id": user_id,
        "name": "Test Client Key",
        "key_prefix": prefix,
        "key_hash": key_hash,
        "scopes": ["chat", "predict", "embed", "rag"],
        "rate_limit": 1000,
        "requests_count": 0,
        "request_count": 0,
        "is_active": True,
        "created_at": datetime.utcnow()
    }
    await db.api_keys.insert_one(doc)
    logger.info(f"API Key created in MongoDB: {raw_key}")
    
    # 2. Run test using httpx AsyncClient and ASGITransport
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Test A: OPTIONS preflight request to protected route
        logger.info("\n--- Test A: OPTIONS preflight check ---")
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key"
        }
        res = await client.options("/api/v1/predict", headers=headers)
        logger.info(f"OPTIONS status: {res.status_code}")
        logger.info(f"OPTIONS headers: {res.headers}")
        
        # Test B: Request to protected route with x-api-key header
        logger.info("\n--- Test B: POST to /api/v1/predict with x-api-key ---")
        headers = {
            "x-api-key": raw_key,
            "Origin": "http://localhost:3000"
        }
        body = {"model_id": "nonexistent_model", "input": [1, 2, 3]}
        res = await client.post("/api/v1/predict", headers=headers, json=body)
        logger.info(f"POST status: {res.status_code}")
        logger.info(f"POST response: {res.json()}")
        
        # Test C: Request to protected route with Authorization Bearer API key header
        logger.info("\n--- Test C: POST to /api/v1/predict with Authorization Bearer ---")
        headers = {
            "Authorization": f"Bearer {raw_key}",
            "Origin": "http://localhost:3000"
        }
        res = await client.post("/api/v1/predict", headers=headers, json=body)
        logger.info(f"POST status: {res.status_code}")
        logger.info(f"POST response: {res.json()}")
        
        # Test D: Check if request count was updated
        logger.info("\n--- Test D: Verify requests count increment ---")
        refetched = await db.api_keys.find_one({"key_hash": key_hash})
        logger.info(f"Database counters: request_count={refetched.get('request_count')}, requests_count={refetched.get('requests_count')}")
        if refetched.get("request_count") == 2 and refetched.get("requests_count") == 2:
            logger.info("SUCCESS: Both request counts incremented to 2!")
        else:
            logger.error(f"FAIL: request_count={refetched.get('request_count')}, requests_count={refetched.get('requests_count')}")
            
        # Test E: GET /api/v1/test-gemini
        logger.info("\n--- Test E: GET /api/v1/test-gemini ---")
        res = await client.get("/api/v1/test-gemini")
        logger.info(f"Test Gemini status: {res.status_code}")
        logger.info(f"Test Gemini response: {res.json()}")

        # Test F: GET /api/v1/rag/indexes with API key
        logger.info("\n--- Test F: GET /api/v1/rag/indexes with API key ---")
        headers = {
            "x-api-key": raw_key,
            "Origin": "http://localhost:3000"
        }
        try:
            res = await client.get("/api/v1/rag/indexes", headers=headers)
            logger.info(f"GET RAG indexes status: {res.status_code}")
            logger.info(f"GET RAG indexes response: {res.json() if res.status_code == 200 else res.text}")
        except Exception as e:
            logger.error(f"GET RAG indexes failed: {e}", exc_info=True)
            
    await disconnect_db()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_flow())
