import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend to python path
sys.path.append(os.path.abspath("backend"))

from api.routes.ai import generate_image, GenerateImageRequest

async def test_endpoint():
    # Mock authentication checks to test backend logic directly
    with patch("api.routes.ai.verify_key_permissions", new_callable=AsyncMock) as mock_verify:
        data = GenerateImageRequest(prompt="Dog", size="512x512")
        request = MagicMock()
        
        print("Calling generate_image endpoint...")
        try:
            result = await generate_image(data=data, request=request, current_user="test_user")
            print("Endpoint call succeeded!")
            print("Result keys:", result.keys())
            print("Note:", result.get("note"))
            print("Image URL prefix:", result.get("image_url")[:50] if result.get("image_url") else None)
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_endpoint())
