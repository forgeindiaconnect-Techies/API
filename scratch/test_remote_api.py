import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_remote_api")

def test():
    # 1. Login to Render
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
        
        # 2. POST /api/v1/api-keys
        create_url = "https://d-ai-7k8h.onrender.com/api/v1/api-keys"
        create_payload = {
            "name": "Test Key from Remote Script",
            "scopes": ["chat"],
            "rate_limit": 10000,
            "allowed_datasets": ["test_both_original (1).txt"],
            "allowed_models": ["Data"]
        }
        
        res = client.post(create_url, json=create_payload, headers=headers, timeout=60.0)
        logger.info(f"Create API Key status: {res.status_code}")
        logger.info(f"Response: {res.text}")

if __name__ == "__main__":
    test()
