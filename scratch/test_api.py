import asyncio
import httpx
import urllib.parse

async def test_hf():
    hf_token = "hf_placeholder_token_for_testing"
    model_id = "black-forest-labs/FLUX.1-schnell"
    api_url = f"https://api-inference.huggingface.co/models/{model_id}"
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }
    payload = {"inputs": "Dog"}
    print(f"Testing HF model {model_id}...")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
            print(f"HF Status: {resp.status_code}")
            if resp.status_code == 200:
                print("HF success! Received bytes size:", len(resp.content))
            else:
                print("HF failed:", resp.text)
    except Exception as e:
        print("HF Exception:", e)

async def test_pollinations_p():
    quoted_prompt = urllib.parse.quote("Dog")
    pollinations_url = f"https://image.pollinations.ai/p/{quoted_prompt}?width=512&height=512&nologo=true"
    print("Testing Pollinations AI with /p/ path:", pollinations_url)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
        }
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            resp = await client.get(pollinations_url)
            print(f"Pollinations /p/ Status: {resp.status_code}")
            if resp.status_code == 200:
                print("Pollinations /p/ success! Received bytes size:", len(resp.content))
            else:
                print("Pollinations /p/ failed:", resp.text)
    except Exception as e:
        print("Pollinations /p/ Exception:", e)

async def test_pollinations_prompt():
    quoted_prompt = urllib.parse.quote("Dog")
    pollinations_url = f"https://image.pollinations.ai/prompt/{quoted_prompt}?width=512&height=512&nologo=true"
    print("Testing Pollinations AI with /prompt/ path:", pollinations_url)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
        }
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            resp = await client.get(pollinations_url)
            print(f"Pollinations /prompt/ Status: {resp.status_code}")
            if resp.status_code == 200:
                print("Pollinations /prompt/ success! Received bytes size:", len(resp.content))
            else:
                print("Pollinations /prompt/ failed:", resp.text)
    except Exception as e:
        print("Pollinations /prompt/ Exception:", e)

async def main():
    await test_hf()
    print("-" * 50)
    await test_pollinations_p()
    print("-" * 50)
    await test_pollinations_prompt()

if __name__ == "__main__":
    asyncio.run(main())
