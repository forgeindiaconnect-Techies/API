import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from api.routes.ai import generate_image, GenerateImageRequest
from config import settings

class MockRequest:
    def __init__(self):
        self.state = type('State', (), {'api_key': None})()

async def test_fallback_flow():
    # Make sure token is set for the test
    settings.HUGGINGFACE_TOKEN = "hf_test_token_12345"
    
    req = GenerateImageRequest(prompt="goa", style="photorealistic", size="512x512")
    request = MockRequest()
    
    print("Test 1: Hugging Face API returns 200, Cloudinary succeeds")
    # Mock verify_key_permissions
    with patch("api.routes.ai.verify_key_permissions", return_value=None):
        # Mock responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake_image_bytes_from_hf"
        
        # Correctly mock httpx.AsyncClient context manager
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        
        # Mock Cloudinary upload
        mock_cloudinary = AsyncMock(return_value={"url": "https://res.cloudinary.com/test/image.png", "public_id": "test_id"})
        
        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("services.cloudinary_service.upload_file_to_cloudinary", mock_cloudinary):
             
            res = await generate_image(data=req, request=request, current_user={})
            print("Response:", res)
            assert res["image_url"] == "https://res.cloudinary.com/test/image.png"
            assert "Hugging Face" in res["note"]
            print("Test 1 passed!\n")

    print("Test 2: Hugging Face fails, Pollinations AI succeeds, Cloudinary fails (base64 fallback)")
    with patch("api.routes.ai.verify_key_permissions", return_value=None):
        # HF response is 500, Pollinations response (GET) is 200
        mock_hf_resp = MagicMock()
        mock_hf_resp.status_code = 500
        mock_hf_resp.text = "HF Server Error"
        
        mock_poll_resp = MagicMock()
        mock_poll_resp.status_code = 200
        mock_poll_resp.content = b"fake_image_bytes_from_pollinations"
        
        # Correctly mock httpx.AsyncClient context manager
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_hf_resp
        mock_client.get.return_value = mock_poll_resp
        
        # Cloudinary upload throws exception to trigger base64 fallback
        mock_cloudinary = AsyncMock(side_effect=Exception("Cloudinary Down"))
        
        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("services.cloudinary_service.upload_file_to_cloudinary", mock_cloudinary):
             
            res = await generate_image(data=req, request=request, current_user={})
            print("Response notes:", res["note"])
            print("Response URL starts with:", res["image_url"][:30])
            assert res["image_url"].startswith("data:image/png;base64,")
            assert "Pollinations AI" in res["note"]
            print("Test 2 passed!\n")

if __name__ == "__main__":
    asyncio.run(test_fallback_flow())
