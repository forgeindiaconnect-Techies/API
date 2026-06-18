import sys
import os
import asyncio
from unittest.mock import patch

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from api.routes.ai import generate_image, GenerateImageRequest

class MockRequest:
    def __init__(self):
        self.state = type('State', (), {'api_key': None})()

async def test_image():
    req = GenerateImageRequest(prompt="goa", style="photorealistic", size="512x512")
    request = MockRequest()
    
    print("Generating image for 'goa'...")
    # Mock verify_key_permissions to bypass API Key auth check
    with patch("api.routes.ai.verify_key_permissions", return_value=None):
        res = await generate_image(data=req, request=request, current_user={"username": "test_user"})
        print("Success! Response keys:", list(res.keys()))
        print("Response image URL:", res["image_url"][:100] + "...")
        assert "image_url" in res
        assert "search_data" in res

if __name__ == "__main__":
    asyncio.run(test_image())
