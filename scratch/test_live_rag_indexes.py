import asyncio
import sys
import os
import httpx

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from config import settings
from auth.utils import create_access_token

async def run_live_test():
    print(f"Loaded SECRET_KEY (first 5 chars): {settings.SECRET_KEY[:5]}...")
    
    # Generate token for user id danish@gmail.com: 6a213b5f4f5a5a8a0249f24b
    user_id = "6a213b5f4f5a5a8a0249f24b"
    token = create_access_token(data={"sub": user_id})
    print(f"Generated access token: {token[:30]}...")
    
    url = "https://d-ai-7k8h.onrender.com/api/v1/rag/indexes"
    headers = {
        "Origin": "https://d-ai-nu.vercel.app",
        "Authorization": f"Bearer {token}"
    }
    
    print(f"\nSending GET request to {url}...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            print(f"Response Status Code: {response.status_code}")
            print("\nResponse Headers:")
            for k, v in response.headers.items():
                print(f"  {k}: {v}")
            print("\nResponse Body:")
            print(response.text)
        except Exception as e:
            print(f"Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_live_test())
