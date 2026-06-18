import asyncio
import httpx

async def run_login_test():
    url = "https://d-ai-7k8h.onrender.com/api/v1/auth/login"
    payload = {
        "email": "dummy@example.com",
        "password": "password"
    }
    print("Sending POST request to login...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=10.0)
            print(f"Status Code: {response.status_code}")
            print(f"Response Body: {response.text}")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_login_test())
