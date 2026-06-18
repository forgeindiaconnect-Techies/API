import sys
import os
import asyncio
import httpx

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db, DatabaseWrapper, MockDB, CollectionWrapper
from auth.utils import create_access_token
from main import app

# Setup mock database
mock_db = DatabaseWrapper(MockDB())

user_doc = {
    "_id": "6a213b5f4f5a5a8a0249f24b",
    "email": "danish@gmail.com",
    "name": "Danish",
    "disabled": False,
    "role": "admin"
}

# Override CollectionWrapper.find_one directly
async def mock_find_one(self, filter, *args, **kwargs):
    return user_doc

CollectionWrapper.find_one = mock_find_one

# Override get_db
import database
database.db = mock_db

# Create a valid access token
token = create_access_token({"sub": "6a213b5f4f5a5a8a0249f24b", "email": "danish@gmail.com"})

async def test_post():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        print("=== Sending POST /api/v1/api-keys ===")
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "name": "Test Key",
            "scopes": ["chat"],
            "rate_limit": 10000
        }
        response = await client.post("/api/v1/api-keys", json=payload, headers=headers)
        print("Status code:", response.status_code)
        print("Response JSON:", response.json())

if __name__ == '__main__':
    asyncio.run(test_post())
