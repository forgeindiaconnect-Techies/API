import os
import sys
import asyncio
import logging
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_rag_endpoint")

from main import app
from database import connect_db

async def run_test():
    await connect_db()
    
    # Use ASGITransport to route requests directly to the FastAPI app without listening on ports
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Login to get token
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "demo@aistudio.com",
            "password": "demo1234"
        })
        logger.info(f"Login status: {login_res.status_code}")
        if login_res.status_code != 200:
            logger.error(f"Login failed: {login_res.text}")
            return
            
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Call POST /api/v1/rag/index (which is a protected endpoint)
        # Note: This is just testing if it passes the middleware authentication check.
        # We expect it to pass and fail with a 404 (due to missing dataset or index details)
        # or succeed if the validation details are matched. But it should NOT return 401.
        logger.info("Sending request to protected RAG index route...")
        create_res = await client.post("/api/v1/rag/index", json={
            "dataset_id": "6a2a52bf76a71ceec1c8d862",
            "name": "Test Index",
            "embedding_model": "paraphrase-MiniLM-L3-v2",
            "chunk_size": 512,
            "chunk_overlap": 50,
            "index_type": "chroma"
        }, headers=headers)
        
        logger.info(f"RAG Index Status: {create_res.status_code}")
        logger.info(f"Response Body: {create_res.text}")

if __name__ == "__main__":
    asyncio.run(run_test())
