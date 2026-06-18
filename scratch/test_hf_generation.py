import sys
import os
import httpx
import asyncio

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from config import settings

async def test_hf_image():
    token = settings.HUGGINGFACE_TOKEN
    print("HF Token loaded:", token[:10] + "..." if token else "None")
    
    # Let's try FLUX.1-schnell first
    model_id = "black-forest-labs/FLUX.1-schnell"
    api_url = f"https://api-inference.huggingface.co/models/{model_id}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": "A beautiful view of Goa beach with palm trees and sunset, photorealistic",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            print("FLUX status:", resp.status_code)
            if resp.status_code == 200:
                print("Success! Bytes length:", len(resp.content))
                # Save it
                with open("scratch/test_hf_flux.png", "wb") as f:
                    f.write(resp.content)
                print("Saved scratch/test_hf_flux.png")
                return
            else:
                print("FLUX failed:", resp.text)
    except Exception as e:
        print("FLUX exception:", e)
        
    # Let's try runwayml/stable-diffusion-v1-5 as a fallback
    model_id = "runwayml/stable-diffusion-v1-5"
    api_url = f"https://api-inference.huggingface.co/models/{model_id}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            print("Stable Diffusion v1.5 status:", resp.status_code)
            if resp.status_code == 200:
                print("Success! Bytes length:", len(resp.content))
                with open("scratch/test_hf_sd.png", "wb") as f:
                    f.write(resp.content)
                print("Saved scratch/test_hf_sd.png")
            else:
                print("Stable Diffusion failed:", resp.text)
    except Exception as e:
        print("Stable Diffusion exception:", e)

if __name__ == "__main__":
    asyncio.run(test_hf_image())
