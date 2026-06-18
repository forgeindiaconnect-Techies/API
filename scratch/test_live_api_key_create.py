import requests
from jose import jwt
from datetime import datetime, timedelta

def test_live_create():
    secret = "a421a8c63cfbc647ce5c88bdcea2199d802ee8e617da5304e578ebfdb39ee648"
    payload = {
        "sub": "6a213b5f4f5a5a8a0249f24b",
        "type": "access",
        "exp": datetime.utcnow() + timedelta(days=1)
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    
    url = "https://d-ai-7k8h.onrender.com/api/v1/api-keys"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    body = {
        "name": "Live Diagnostic Key",
        "scopes": ["chat"],
        "rate_limit": 10000
    }
    
    print("Sending live request to Render...")
    try:
        res = requests.post(url, headers=headers, json=body, timeout=30)
        print("Status code:", res.status_code)
        print("Response:", res.text)
    except Exception as e:
        print("Request failed:", e)

if __name__ == '__main__':
    test_live_create()
