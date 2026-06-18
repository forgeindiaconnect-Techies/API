import time
import httpx

url = "https://api-n7cm.onrender.com/api/v1/test-gemini"
print(f"Pinging {url} to check new backend status...")
start = time.time()

# Poll for up to 5 minutes
for i in range(15):
    try:
        resp = httpx.get(url, timeout=15)
        print(f"[{i+1}] Status: {resp.status_code}, Response: {resp.text}")
        if resp.status_code == 200:
            print(f"Server is healthy and active! (Took {time.time() - start:.1f}s)")
            break
    except Exception as e:
        print(f"[{i+1}] Request failed: {e}")
    time.sleep(10)

