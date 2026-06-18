import asyncio
import sys
import os

# Add backend directory to sys.path so we can import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from database import connect_db, get_db
from redis_client import get_redis, close_redis

async def run_tests():
    print("--- 1. Testing MongoDB Connection and Indexes ---")
    await connect_db()
    db = get_db()
    
    if db is None:
        print("FAIL: MongoDB db instance is None!")
        return
        
    try:
        # Check if indexes on training_jobs collection exist
        indexes = await db.training_jobs.index_information()
        print("Found training_jobs indexes:")
        for name, info in indexes.items():
            print(f"  - {name}: {info}")
            
        has_model_id_index = any("model_id" in dict(info["key"]) for info in indexes.values())
        has_user_id_index = any("user_id" in dict(info["key"]) for info in indexes.values())
        
        if has_model_id_index:
            print("SUCCESS: Found index on training_jobs.model_id")
        else:
            print("FAIL: Missing index on training_jobs.model_id")
            
        if has_user_id_index:
            print("SUCCESS: Found index on training_jobs.user_id")
        else:
            print("FAIL: Missing index on training_jobs.user_id")
            
    except Exception as e:
        print(f"FAIL: MongoDB index check failed: {e}")
        
    print("\n--- 2. Testing Redis Connection and Cache operations ---")
    redis_client = get_redis()
    if redis_client is None:
        print("FAIL: Redis client is None!")
    else:
        try:
            # Test basic set/get
            test_key = "test:models:performance"
            test_val = "optimized_speed_test"
            await redis_client.set(test_key, test_val)
            retrieved = await redis_client.get(test_key)
            if retrieved == test_val:
                print(f"SUCCESS: Set and retrieved '{test_val}' from Redis.")
            else:
                print(f"FAIL: Retrieved value '{retrieved}' did not match '{test_val}'")
                
            # Test key deletion
            await redis_client.delete(test_key)
            after_delete = await redis_client.get(test_key)
            if after_delete is None:
                print("SUCCESS: Key deleted successfully.")
            else:
                print("FAIL: Key still exists after delete.")
                
        except Exception as e:
            print(f"FAIL: Redis operations failed: {e}")
        finally:
            await close_redis()

if __name__ == "__main__":
    asyncio.run(run_tests())
