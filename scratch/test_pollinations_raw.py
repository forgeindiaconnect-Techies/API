import httpx
import asyncio

async def test_pollinations():
    url = "https://image.pollinations.ai/p/goa?width=512&height=512&nologo=true"
    
    # Test 1: No headers (similar to what failed)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            print("Test 1 (No headers):", resp.status_code)
            if resp.status_code == 200:
                print("Test 1 success, bytes length:", len(resp.content))
            else:
                print("Test 1 failed. Response text:", resp.text[:200])
    except Exception as e:
        print("Test 1 failed with exception:", e)

    # Test 2: With User-Agent headers
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124"
        }
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            resp = await client.get(url)
            print("Test 2 (With User-Agent):", resp.status_code)
            if resp.status_code == 200:
                print("Test 2 success, bytes length:", len(resp.content))
            else:
                print("Test 2 failed. Response text:", resp.text[:200])
    except Exception as e:
        print("Test 2 failed with exception:", e)

if __name__ == "__main__":
    asyncio.run(test_pollinations())
