import sys
import os
import asyncio
import httpx

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db
from auth.utils import create_access_token
from main import app

async def test_post():
    # Connect to the real DB
    await connect_db()
    
    db = get_db()
    # Find Danish in the real database
    user = await db.users.find_one({"email": "danish@gmail.com"})
    if not user:
        print("User danish@gmail.com not found in the database!")
        return
    
    print(f"Found user: {user.get('name')} (ID: {user['_id']})")
    
    # Create token for Danish
    token = create_access_token({"sub": str(user["_id"]), "email": user["email"]})
    print(f"Generated access token: {token[:30]}...")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
        print("\n=== Sending POST /api/v1/api-keys ===")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "name": "Local Diagnostic Key 1",
            "scopes": ["chat"],
            "rate_limit": 10000
        }
        try:
            response = await client.post("/api/v1/api-keys", json=payload, headers=headers)
            print("Status code:", response.status_code)
            print("Response:", response.text)
            if response.status_code == 200:
                data = response.json()
                print("\nCreated key response payload:")
                print(data)
                
                print("\n=== Testing API Key authentication using the generated key ===")
                # Let's try calling another endpoint using the generated API Key!
                # E.g. GET /api/v1/api-keys
                auth_headers = {
                    "Authorization": f"Bearer {data['key']}"
                }
                list_res = await client.get("/api/v1/api-keys", headers=auth_headers)
                print("List keys using API Key status:", list_res.status_code)
                print("List keys response:", list_res.text[:200])
        except Exception as e:
            print("Request failed:", e)

if __name__ == '__main__':
    asyncio.run(test_post())
