import os
import sys
import asyncio
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("test_api_key_system")

from database import connect_db, get_db, disconnect_db
from api.routes.api_keys import generate_api_key, fmt_key
from auth.utils import verify_api_key
from config import settings

async def run_tests():
    logger.info("Connecting to MongoDB...")
    await connect_db()
    db = get_db()
    if db is None:
        logger.error("DB connection failed")
        return
        
    logger.info("MongoDB Connected.")
    
    # Clean up old test keys
    await db.api_keys.delete_many({"name": {"$regex": "^Test API Key System.*"}})
    
    user_id = "6a2a8ce94af4f2be830e5d28"
    
    # ----------------------------------------------------
    # TEST 1: Generate Manual API Key
    # ----------------------------------------------------
    logger.info("\n--- TEST 1: Generating Manual API Key ---")
    raw_key, prefix, key_hash = generate_api_key()
    logger.info(f"Generated Key: {raw_key}")
    logger.info(f"Prefix: {prefix}")
    logger.info(f"Hash: {key_hash}")
    
    doc_manual = {
        "user_id": user_id,
        "name": "Test API Key System (Manual)",
        "key": raw_key,
        "key_hash": key_hash,
        "scopes": ["chat", "predict", "embed"],
        "rate_limit": 10,
        "request_count": 0,
        "requests_count": 0,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "last_used": None,
        "expires_at": None,
        "dataset_ids": [],
        "model_ids": []
    }
    await db.api_keys.insert_one(doc_manual)
    logger.info("Manual API Key inserted into DB.")
    
    # ----------------------------------------------------
    # TEST 2: Generate Auto-Generated Dataset API Key
    # ----------------------------------------------------
    logger.info("\n--- TEST 2: Generating Auto-Generated Key (Dataset Style, no plaintext key field) ---")
    raw_key_auto, prefix_auto, key_hash_auto = generate_api_key()
    logger.info(f"Generated Auto Key: {raw_key_auto}")
    logger.info(f"Prefix: {prefix_auto}")
    logger.info(f"Hash: {key_hash_auto}")
    
    doc_auto = {
        "user_id": user_id,
        "name": "Test API Key System (Auto)",
        "key_prefix": prefix_auto,
        "key_hash": key_hash_auto,
        "scopes": ["chat", "predict", "embed"],
        "rate_limit": 10,
        "requests_count": 0, # auto-generated keys start with this
        "status": "active",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "last_used": None,
        "expires_at": None,
        "dataset_ids": ["test-dataset-id"],
        "model_ids": []
    }
    await db.api_keys.insert_one(doc_auto)
    logger.info("Auto-Generated Dataset API Key inserted into DB.")
    
    # ----------------------------------------------------
    # TEST 3: Validate Manual API Key and verify count updates
    # ----------------------------------------------------
    logger.info("\n--- TEST 3: Verifying Manual API Key Authentication ---")
    verified_manual = await verify_api_key(raw_key)
    if not verified_manual:
        logger.error("FAIL: Manual API Key verification failed!")
    else:
        logger.info(f"SUCCESS: Manual API Key verified! Name: {verified_manual.get('name')}")
        # Re-fetch to check if both counts incremented
        refetched = await db.api_keys.find_one({"_id": verified_manual["_id"]})
        logger.info(f"Counts after verification: request_count={refetched.get('request_count')}, requests_count={refetched.get('requests_count')}")
        if refetched.get("request_count") == 1 and refetched.get("requests_count") == 1:
            logger.info("SUCCESS: Both request_count and requests_count incremented successfully!")
        else:
            logger.error("FAIL: Counts did not increment correctly.")
            
    # ----------------------------------------------------
    # TEST 4: Validate Auto-Generated Key (Dataset Style) and verify count updates
    # ----------------------------------------------------
    logger.info("\n--- TEST 4: Verifying Auto-Generated Dataset API Key Authentication ---")
    verified_auto = await verify_api_key(raw_key_auto)
    if not verified_auto:
        logger.error("FAIL: Auto-Generated Dataset API Key verification failed!")
    else:
        logger.info(f"SUCCESS: Auto-Generated Dataset API Key verified! Name: {verified_auto.get('name')}")
        # Re-fetch to check if both counts incremented
        refetched = await db.api_keys.find_one({"_id": verified_auto["_id"]})
        logger.info(f"Counts after verification: request_count={refetched.get('request_count')}, requests_count={refetched.get('requests_count')}")
        if refetched.get("request_count") == 1 and refetched.get("requests_count") == 1:
            logger.info("SUCCESS: Both request_count and requests_count incremented successfully!")
        else:
            logger.error("FAIL: Counts did not increment correctly.")
            
    # ----------------------------------------------------
    # TEST 5: Verify formatting logic (fmt_key)
    # ----------------------------------------------------
    logger.info("\n--- TEST 5: Testing fmt_key formatting and masking ---")
    formatted_manual = fmt_key(verified_manual, mask=True)
    formatted_auto = fmt_key(verified_auto, mask=True)
    
    logger.info(f"Formatted Manual Key (Masked): {formatted_manual.get('key')}")
    logger.info(f"Formatted Auto Key (Masked): {formatted_auto.get('key')}")
    
    if "••••" in formatted_manual.get('key') and prefix_auto in formatted_auto.get('key'):
        logger.info("SUCCESS: Formatting and masking is fully correct!")
    else:
        logger.error("FAIL: Masking does not work correctly.")
        
    # ----------------------------------------------------
    # TEST 6: Google Gemini connectivity and fallback test
    # ----------------------------------------------------
    logger.info("\n--- TEST 6: Testing Google Gemini Fallback Integration ---")
    gemini_key = os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY
    logger.info(f"Configured GEMINI_API_KEY: {gemini_key[:8] + '...' if gemini_key else 'None'}")
    
    if not gemini_key:
        logger.warning("GEMINI_API_KEY is not set. Skipping live connectivity test.")
    else:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            logger.info("Calling model.generate_content_async...")
            res = await model.generate_content_async("Respond with exactly: 'Gemini fallback works!'")
            text = res.text.strip()
            logger.info(f"Gemini API Response: '{text}'")
            if "works" in text.lower():
                logger.info("SUCCESS: Live Gemini connectivity test passed!")
            else:
                logger.error(f"FAIL: Unexpected response text: {text}")
        except Exception as e:
            logger.error(f"FAIL: Gemini connectivity test failed: {e}", exc_info=True)
            
    await disconnect_db()
    logger.info("\nAll tests completed.")

if __name__ == "__main__":
    asyncio.run(run_tests())
