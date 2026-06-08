import requests
import time

def check():
    url = "https://d-ai-7k8h.onrender.com/api/v1/test-embedder"
    print("Polling /api/v1/test-embedder for status...")
    start_time = time.time()
    while time.time() - start_time < 600: # Wait up to 10 minutes
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                print(f"\nSUCCESS: Endpoint returned 200!")
                import json
                print(json.dumps(res.json(), indent=2))
                break
            elif res.status_code == 404:
                print(f"[{time.strftime('%H:%M:%S')}] Endpoint returned 404 (old deployment still running)...")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Status code: {res.status_code}")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Request failed: {e}")
        time.sleep(15)

if __name__ == '__main__':
    check()
