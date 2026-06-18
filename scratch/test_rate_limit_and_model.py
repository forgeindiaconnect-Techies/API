import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import MockDB, DatabaseWrapper
from services.chat_service import query_dataset_rag

async def test_dynamic_model():
    print("=== Testing dynamic model passing in query_dataset_rag ===")
    
    mock_db = DatabaseWrapper(MockDB())
    
    # Insert a dataset and RAG index doc
    dataset_doc = {
        "_id": "dataset_abc",
        "name": "test_doc.txt",
        "file_type": "txt",
        "status": "ready"
    }
    index_doc = {
        "_id": "6a21429591ef830d2aa4b9f7",
        "dataset_id": "dataset_abc",
        "embedding_model": "paraphrase-MiniLM-L3-v2",
        "index_type": "chroma",
        "status": "ready"
    }
    await mock_db.datasets.insert_one(dataset_doc)
    await mock_db.rag_indexes.insert_one(index_doc)
    
    # Run chat service query passing a custom model name
    try:
        res = await query_dataset_rag(
            index_id="6a21429591ef830d2aa4b9f7",
            question="hello",
            top_k=2,
            db=mock_db,
            model="mistral"
        )
        print("Successfully queried dynamic model. Response keys:", res.keys())
    except Exception as e:
        print("Failed dynamic model query:", e)

async def test_rate_limiting():
    print("\n=== Testing API key rate limit check ===")
    from auth.utils import get_current_user
    from fastapi import Request
    from starlette.datastructures import Headers
    
    mock_db = DatabaseWrapper(MockDB())
    
    # Insert a user and api key doc
    user_doc = {
        "_id": "user_123",
        "email": "user@test.com",
        "name": "Test User",
        "disabled": False
    }
    
    # An active key that has reached its rate limit
    api_key_str = "sk-test-limit-key"
    import hashlib
    key_hash = hashlib.sha256(api_key_str.encode()).hexdigest()
    
    key_doc = {
        "user_id": "user_123",
        "name": "Limit Key",
        "key_prefix": "sk-test",
        "key_hash": key_hash,
        "is_active": True,
        "rate_limit": 5,
        "requests_count": 5, # Limit met
        "scopes": ["chat"]
    }
    
    await mock_db.users.insert_one(user_doc)
    await mock_db.api_keys.insert_one(key_doc)
    
    # Construct a mock request
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {api_key_str}".encode())],
        "state": {}
    }
    
    # Stub get_db in auth.utils
    import auth.utils
    original_get_db = auth.utils.get_db
    auth.utils.get_db = lambda: mock_db
    
    request = Request(scope)
    
    try:
        await get_current_user(request)
        print("FAILED: API Key allowed past rate limit!")
    except Exception as e:
        print(f"PASSED: Rate limiting blocked request with expected exception: {e}")
        
    auth.utils.get_db = original_get_db

if __name__ == '__main__':
    asyncio.run(test_dynamic_model())
    asyncio.run(test_rate_limiting())
