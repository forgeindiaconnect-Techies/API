import httpx

login_url = "https://d-ai-7k8h.onrender.com/api/v1/auth/login"
image_url = "https://d-ai-7k8h.onrender.com/api/v1/ai/generate-image"

async def test_remote():
    # 1. Log in
    credentials = {"email": "danish@gmail.com", "password": "Danish@21"}
    print(f"Logging in to {login_url}...")
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(login_url, json=credentials)
        print("Login status:", resp.status_code)
        if resp.status_code != 200:
            print("Login failed:", resp.text)
            return
            
        data = resp.json()
        token = data.get("access_token")
        print("Login successful! Token acquired.")
        
        # 2. Call generate-image
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"prompt": "A beautiful sunset over the mountains", "size": "512x512"}
        print(f"Requesting remote image generation for prompt: '{payload['prompt']}'...")
        
        # This could take a few seconds as it calls Hugging Face Inference API
        image_resp = await client.post(image_url, json=payload, headers=headers)
        print("Image generation status:", image_resp.status_code)
        
        if image_resp.status_code == 200:
            res_data = image_resp.json()
            print("Image generation SUCCESS!")
            print("Keys returned:", list(res_data.keys()))
            print("Note from API:", res_data.get("note"))
            url = res_data.get("image_url")
            print("Generated image URL (prefix):", url[:100] if url else None)
        else:
            print("Image generation failed:", image_resp.text)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_remote())
