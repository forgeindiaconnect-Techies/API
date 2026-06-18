import requests
from jose import jwt
from datetime import datetime, timedelta

def test():
    secret = "a421a8c63cfbc647ce5c88bdcea2199d802ee8e617da5304e578ebfdb39ee648"
    payload = {
        "sub": "6a213b5f4f5a5a8a0249f24b",
        "type": "access",
        "exp": datetime.utcnow() + timedelta(days=1)
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    url = "https://d-ai-7k8h.onrender.com/api/v1/test-embedder"
    print(f"Requesting {url} with JWT...")
    try:
        r = requests.get(url, headers=headers, timeout=30)
        print("Response status:", r.status_code)
        print("Response body:")
        print(r.text)
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    test()
