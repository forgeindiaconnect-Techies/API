import requests
import json
from jose import jwt
from datetime import datetime, timedelta

def run():
    # 1. Generate access token
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

    # 2. Get the new index ID
    # In the previous step, the new index ID was: 6a23c7d0a965da47cfaccf9f
    index_id = "6a23c91fa965da47cfaccfa5"
    
    url = "https://d-ai-7k8h.onrender.com/api/v1/rag/search"
    queries = [
        "have you seen the new girl in school?",
        "what's your favorite movie?",
        "hi, how are you",
        "pcc campus movie"
    ]
    
    for q in queries:
        print(f"\nQuerying: '{q}'...")
        body = {
            "index_id": index_id,
            "query": q,
            "top_k": 3
        }
        res = requests.post(url, headers=headers, json=body)
        print("Response Code:", res.status_code)
        if res.status_code == 200:
            data = res.json()
            results = data.get("results", [])
            print(f"Returned {len(results)} results:")
            for idx, r in enumerate(results):
                print(f"  [{idx+1}] Score: {r.get('score')}")
                print(f"      Source: {r.get('source')}")
                print(f"      Content: {r.get('content')[:120]}...")
        else:
            print("Response:", res.text)

if __name__ == '__main__':
    run()
