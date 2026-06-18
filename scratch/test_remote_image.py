import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_remote_image")

def test():
    # 1. Login to get token
    login_url = "https://d-ai-7k8h.onrender.com/api/v1/auth/login"
    login_payload = {
        "email": "demo@aistudio.com",
        "password": "demo1234"
    }
    
    with httpx.Client() as client:
        res = client.post(login_url, json=login_payload, timeout=60.0)
        logger.info(f"Login status: {res.status_code}")
        if res.status_code != 200:
            logger.error(f"Login failed: {res.text}")
            return
            
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Call POST /api/v1/ai/generate-image
        url = "https://d-ai-7k8h.onrender.com/api/v1/ai/generate-image"
        payload = {
            "prompt": "goa",
            "style": "photorealistic",
            "size": "512x512"
        }
        
        res = client.post(url, json=payload, headers=headers, timeout=60.0)
        logger.info(f"Image Generate status: {res.status_code}")
        logger.info(f"Response: {res.text}")

if __name__ == "__main__":
    test()
