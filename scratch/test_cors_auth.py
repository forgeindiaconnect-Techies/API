import sys
import os
import asyncio
from unittest.mock import patch, MagicMock
import httpx

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Mock database connection during import to prevent locks
import database
from database import MockDB, DatabaseWrapper
mock_db = DatabaseWrapper(MockDB())
database.db = mock_db

# Mock startup recovery to bypass index checks
with patch("services.startup_rebuild.run_startup_recovery", return_value=None):
    from main import app

async def run_tests():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        
        print("\n--- 1. Testing preflight OPTIONS request ---")
        headers = {
            "Origin": "https://d-ai-nu.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type"
        }
        response = await client.options("/api/v1/datasets/6a2650c5a3d0ac1e7efca123/process", headers=headers)
        print("Preflight Response Status:", response.status_code)
        print("CORS Headers:", {k: v for k, v in response.headers.items() if "access-control" in k.lower()})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://d-ai-nu.vercel.app"
        assert response.headers.get("access-control-allow-credentials") == "true"
        print("Preflight test passed!")

        print("\n--- 2. Testing unauthorized request (missing token) ---")
        headers = {
            "Origin": "https://d-ai-nu.vercel.app"
        }
        response = await client.post("/api/v1/datasets/6a2650c5a3d0ac1e7efca123/process", headers=headers, json={})
        print("Unauthorized Response Status:", response.status_code)
        print("Response Body:", response.json())
        print("CORS Headers:", {k: v for k, v in response.headers.items() if "access-control" in k.lower()})
        assert response.status_code == 401
        assert response.headers.get("access-control-allow-origin") == "https://d-ai-nu.vercel.app"
        print("Unauthorized request test passed!")

        print("\n--- 3. Testing authorized request (valid token) ---")
        # Insert mock user
        mock_db.users._collection._data.append({
            "_id": "user_abc",
            "name": "Test User",
            "email": "test@example.com",
            "role": "admin",
            "disabled": False
        })
        
        from auth.utils import create_access_token
        token = create_access_token({"sub": "user_abc", "email": "test@example.com"})
        
        headers = {
            "Origin": "https://d-ai-nu.vercel.app",
            "Authorization": f"Bearer {token}"
        }
        
        response = await client.post("/api/v1/datasets/6a2650c5a3d0ac1e7efca123/process", headers=headers, json={
            "clean_nulls": True,
            "remove_duplicates": False
        })
        print("Authorized Response Status:", response.status_code)
        print("Response Body:", response.json())
        print("CORS Headers:", {k: v for k, v in response.headers.items() if "access-control" in k.lower()})
        
        assert response.status_code == 404
        assert response.headers.get("access-control-allow-origin") == "https://d-ai-nu.vercel.app"
        print("Authorized request test passed!")

if __name__ == "__main__":
    asyncio.run(run_tests())
    print("\nALL CORS & AUTHENTICATION TESTS PASSED SUCCESSFULLY!")
