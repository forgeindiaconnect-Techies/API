import sys
import os
import asyncio
from unittest.mock import patch
from datetime import datetime, timedelta
import httpx

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Mock database connection during import
import database
from database import MockDB, DatabaseWrapper
mock_db = DatabaseWrapper(MockDB())
database.db = mock_db

# Mock startup recovery
with patch("services.startup_rebuild.run_startup_recovery", return_value=None):
    from main import app
    from auth.utils import create_access_token, create_refresh_token, decode_token

async def run_jwt_tests():
    print("\n=== STARTING JWT PIPELINE & REFRESH ENDPOINT TESTS ===")
    
    # 1. Generate test tokens
    token_data = {"sub": "user_123", "email": "test@example.com"}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    print("\n--- 1. Testing decode_token (valid access token) ---")
    payload = decode_token(access_token, expected_type="access")
    print("Decoded Access Payload:", payload)
    assert payload["sub"] == "user_123"
    assert payload["type"] == "access"
    
    print("\n--- 2. Testing decode_token (valid refresh token) ---")
    payload_refresh = decode_token(refresh_token, expected_type="refresh")
    print("Decoded Refresh Payload:", payload_refresh)
    assert payload_refresh["sub"] == "user_123"
    assert payload_refresh["type"] == "refresh"
    
    print("\n--- 3. Testing decode_token with wrong type ---")
    try:
        decode_token(access_token, expected_type="refresh")
        print("FAIL: decoded access token as refresh token")
        assert False
    except Exception as e:
        print("Success: raising error on wrong type:", type(e), str(e))
        
    print("\n--- 4. Testing decode_token with expired token ---")
    expired_token = create_access_token(token_data, expires_delta=timedelta(seconds=-10))
    try:
        decode_token(expired_token, expected_type="access")
        print("FAIL: decoded expired access token")
        assert False
    except Exception as e:
        print("Success: raising error on expired token:", type(e), str(e))
        # Ensure it mentions expired
        assert "expired" in str(e).lower()
        
    print("\n--- 5. Testing /refresh HTTP endpoint ---")
    # Add mock user to database
    mock_db.users._collection._data.append({
        "_id": "user_123",
        "name": "Refresh User",
        "email": "test@example.com",
        "role": "user",
        "disabled": False
    })
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Valid refresh
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        print("Refresh status:", response.status_code)
        print("Refresh body:", response.json())
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert "refresh_token" in response.json()
        
        # Expired refresh
        expired_refresh = create_refresh_token(token_data)
        # We manually modify exp field by encoding it with past expiry
        from jose import jwt
        from config import settings
        past_payload = token_data.copy()
        past_payload["exp"] = datetime.utcnow() - timedelta(seconds=10)
        past_payload["type"] = "refresh"
        secret = settings.JWT_REFRESH_SECRET or settings.SECRET_KEY
        expired_refresh_jwt = jwt.encode(past_payload, secret, algorithm=settings.ALGORITHM)
        
        response_expired = await client.post("/api/v1/auth/refresh", json={"refresh_token": expired_refresh_jwt})
        print("Expired refresh status:", response_expired.status_code)
        print("Expired refresh body:", response_expired.json())
        assert response_expired.status_code == 401
        assert "expired" in response_expired.json()["detail"].lower()
        
        # Invalid signature refresh
        bad_refresh = jwt.encode(past_payload, "different_secret_key", algorithm=settings.ALGORITHM)
        response_bad = await client.post("/api/v1/auth/refresh", json={"refresh_token": bad_refresh})
        print("Bad signature refresh status:", response_bad.status_code)
        print("Bad signature refresh body:", response_bad.json())
        assert response_bad.status_code == 401
        assert "invalid" in response_bad.json()["detail"].lower()
        
    print("\nALL JWT AND REFRESH ROUTE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_jwt_tests())
