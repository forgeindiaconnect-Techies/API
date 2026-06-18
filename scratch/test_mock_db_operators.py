import sys
import os
import asyncio
import httpx
from datetime import datetime, timezone

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import DatabaseWrapper, MockDB
from auth.utils import create_access_token
from main import app
import database

async def verify_mock_db():
    print("=== Testing MockDB Operators ===")
    mock_db = DatabaseWrapper(MockDB())
    
    # 1. Test insert_one and find_one with standard matching
    user_doc = {
        "email": "danish@gmail.com",
        "name": "Danish",
        "disabled": False,
        "role": "admin"
    }
    res = await mock_db.users.insert_one(user_doc)
    doc_id = res.inserted_id
    print(f"Inserted doc ID: {doc_id}")
    
    # 2. Test find_one with $in operator
    found_in = await mock_db.users.find_one({"_id": {"$in": [doc_id, "99999"]}})
    print("Found with $in operator:", found_in is not None and found_in.get("email") == "danish@gmail.com")
    
    # 3. Test find_one with $or operator
    found_or = await mock_db.users.find_one({"$or": [{"email": "nonexistent@gmail.com"}, {"_id": doc_id}]})
    print("Found with $or operator:", found_or is not None and found_or.get("email") == "danish@gmail.com")
    
    # 4. Test find_one with $exists operator
    found_exists = await mock_db.users.find_one({"role": {"$exists": True}})
    print("Found with $exists operator:", found_exists is not None and found_exists.get("email") == "danish@gmail.com")
    
    # 5. Test count_documents with query filter
    count = await mock_db.users.count_documents({"disabled": False})
    print("Counted documents:", count)
    
    # Override global database db with our mock database for API verification
    database.db = mock_db
    
    # 6. Test dynamic demo account registration on login attempt
    print("\n=== Testing Dynamic Demo Account Registration ===")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Verify demo user does not exist in mock_db first
        pre_check = await mock_db.users.find_one({"email": "demo@aistudio.com"})
        print("Demo user exists pre-login:", pre_check is not None)
        
        # Send login request
        login_payload = {
            "email": "demo@aistudio.com",
            "password": "demo1234"
        }
        login_res = await client.post("/api/v1/auth/login", json=login_payload)
        print("Login status code:", login_res.status_code)
        
        # Verify demo user exists in mock_db now
        post_check = await mock_db.users.find_one({"email": "demo@aistudio.com"})
        print("Demo user exists post-login:", post_check is not None)
        if post_check:
            print(f"Registered Demo User ID: {post_check['_id']}, Role: {post_check.get('role')}")
            
        # Verify we got a valid JWT and can list API keys (which will query using MockDB and $in)
        token = login_res.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        keys_res = await client.get("/api/v1/api-keys", headers=headers)
        print("GET /api-keys status code:", keys_res.status_code)
        print("GET /api-keys response:", keys_res.json())

if __name__ == '__main__':
    asyncio.run(verify_mock_db())
