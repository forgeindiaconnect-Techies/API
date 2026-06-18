import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_via_client")

from fastapi.testclient import TestClient
from main import app
from database import connect_db

async def run_test():
    await connect_db()
    
    client = TestClient(app)
    
    # 1. Login to get token
    login_res = client.post("/api/v1/auth/login", json={
        "email": "demo@aistudio.com",
        "password": "demo1234"
    })
    logger.info(f"Login status: {login_res.status_code}")
    if login_res.status_code != 200:
        logger.error(f"Login failed: {login_res.json()}")
        return
        
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Call POST /api/v1/api-keys
    create_res = client.post("/api/v1/api-keys", json={
        "name": "Test Key from Client",
        "scopes": ["chat"],
        "rate_limit": 10000,
        "allowed_datasets": ["test_both_original (1).txt"],
        "allowed_models": ["Data"]
    }, headers=headers)
    
    logger.info(f"Create API Key status: {create_res.status_code}")
    logger.info(f"Response: {create_res.json()}")

if __name__ == "__main__":
    asyncio.run(run_test())
