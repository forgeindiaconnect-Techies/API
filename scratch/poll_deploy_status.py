import requests
import time
from typing import Any, Dict

def poll() -> None:
    url: str = "https://d-ai-7k8h.onrender.com/api/v1/datasets/6a26551be275408ac3940470"
    headers: Dict[str, str] = {"Origin": "https://d-ai-nu.vercel.app"}
    print("Polling live server for deployment status changes (waiting for 403 -> 401 status shift)...")
    start_time: float = time.time()
    while time.time() - start_time < 300: # Poll for up to 5 minutes
        try:
            r: requests.Response = requests.get(url, headers=headers, timeout=10)
            status: int = r.status_code
            json_data: dict[str, Any] = r.json()
            detail: Any = json_data.get("detail")
            print(f"[{time.strftime('%H:%M:%S')}] Status: {status}, Detail: {detail}")
            if status == 401:
                print("SUCCESS: The new deployment has finished booting up and is now live!")
                break
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Request failed: {e}")
        time.sleep(15)

if __name__ == '__main__':
    poll()
