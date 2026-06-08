import jose.jwt
from datetime import datetime, timedelta
import json

def generate():
    secret = "a421a8c63cfbc647ce5c88bdcea2199d802ee8e617da5304e578ebfdb39ee648"
    user_id = "6a213b5f4f5a5a8a0249f24b"
    
    access_payload = {
        "sub": user_id,
        "type": "access",
        "exp": (datetime.utcnow() + timedelta(days=7)).timestamp()
    }
    access_token = jose.jwt.encode(access_payload, secret, algorithm="HS256")
    
    refresh_payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": (datetime.utcnow() + timedelta(days=30)).timestamp()
    }
    refresh_token = jose.jwt.encode(refresh_payload, secret, algorithm="HS256")
    
    user_info = {
        "id": user_id,
        "email": "danish@gmail.com",
        "name": "Danish",
        "role": "admin"
    }
    
    print("ACCESS_TOKEN:")
    print(access_token)
    print("\nREFRESH_TOKEN:")
    print(refresh_token)
    print("\nUSER_INFO:")
    print(json.dumps(user_info))

if __name__ == '__main__':
    generate()
