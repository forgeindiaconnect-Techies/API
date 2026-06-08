from jose import jwt
import requests
import json
from datetime import datetime, timedelta

def test_live_stream():
    # 1. Generate access token
    secret = "a421a8c63cfbc647ce5c88bdcea2199d802ee8e617da5304e578ebfdb39ee648"
    payload = {
        "sub": "6a213b5f4f5a5a8a0249f24b",
        "type": "access",
        "exp": datetime.utcnow() + timedelta(days=1)
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    print(f"Generated JWT token: {token[:30]}...")

    # 2. Call stream endpoint
    url = "https://d-ai-7k8h.onrender.com/api/v1/chat/conversations/6a21429591ef830d2aa4b9f7/stream"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    body = {
        "content": "have you seen the new girl in school?",
        "model": "llama3",
        "temperature": 0.7,
        "max_tokens": 2048,
        "dataset_id": "6a21567a49dd8906f4ff3e2b",
        "mode": "dataset_only"
    }
    
    print("Sending request to stream endpoint...")
    try:
        response = requests.post(url, headers=headers, json=body, stream=True, timeout=60)
        print(f"Response status code: {response.status_code}")
        if response.status_code != 200:
            print("Response content:", response.text)
            return

        print("Streaming tokens:")
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                print(decoded_line)
    except Exception as e:
        print("Request failed:", e)

if __name__ == '__main__':
    test_live_stream()
