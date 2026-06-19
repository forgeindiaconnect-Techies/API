import os
import sys
import asyncio
import logging
from datetime import datetime
import httpx

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from main import app
from database import connect_db, get_db, disconnect_db
from auth.utils import create_access_token, hash_password
from bson import ObjectId

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("test_rag_pipeline")

async def test_rag_flow():
    logger.info("Connecting to DB...")
    await connect_db()
    db = get_db()
    if db is None:
        logger.error("Database connection unavailable")
        return False

    # 1. Setup Test User
    logger.info("Setting up temporary test user...")
    test_user_id = "6a0000000000000000000001"
    # Ensure test user is cleared first
    await db.users.delete_many({"_id": {"$in": [test_user_id, ObjectId(test_user_id)]}})
    await db.users.delete_many({"email": "rag_test_user@example.com"})
    
    user_doc = {
        "_id": ObjectId(test_user_id),
        "email": "rag_test_user@example.com",
        "hashed_password": hash_password("testpassword123"),
        "role": "admin",
        "created_at": datetime.utcnow()
    }
    await db.users.insert_one(user_doc)
    
    # Generate Bearer Token
    token = create_access_token({"sub": test_user_id})
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "http://localhost:3000"
    }
    logger.info(f"JWT Token generated: {token[:20]}...")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 2. Test Dynamic Health Check
        logger.info("\n--- Step 2: Testing /health endpoint ---")
        health_resp = await client.get("/health")
        logger.info(f"Health check status: {health_resp.status_code}")
        health_json = health_resp.json()
        logger.info(f"Health check response: {health_json}")
        assert health_json["status"] in ("healthy", "degraded"), f"Unexpected status: {health_json['status']}"
        assert "mongodb" in health_json, "mongodb field missing from health check"
        assert "chromadb" in health_json, "chromadb field missing from health check"

        # 3. Upload Dataset
        logger.info("\n--- Step 3: Uploading dummy dataset file ---")
        dummy_content = (
            "Advanced Agentic Coding agent named Antigravity. "
            "Antigravity is built by the Google DeepMind team. "
            "It is designed to solve coding tasks, build web applications, "
            "and assist developers in refactoring codebases with precision."
        )
        files = {
            "file": ("antigravity_info.txt", dummy_content.encode('utf-8'), "text/plain")
        }
        upload_resp = await client.post("/api/v1/datasets/upload", headers=headers, files=files)
        logger.info(f"Upload response status: {upload_resp.status_code}")
        assert upload_resp.status_code == 202, f"Upload failed: {upload_resp.text}"
        
        upload_json = upload_resp.json()
        dataset_id = upload_json.get("id")
        logger.info(f"Uploaded dataset. ID: {dataset_id}")
        assert dataset_id is not None, "Dataset ID was not returned on upload"

        # 4. Wait for background chunking and embedding to complete
        logger.info("\n--- Step 4: Waiting for indexing status to reach 'ready' ---")
        dataset_doc = None
        max_retries = 30
        for i in range(max_retries):
            # Check dataset status in db
            dataset_doc = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
            if dataset_doc:
                status = dataset_doc.get("status")
                logger.info(f"Checking dataset status: {status} (attempt {i+1}/{max_retries})")
                if status in ("ready", "indexed"):
                    logger.info("Dataset indexed successfully!")
                    break
            else:
                logger.warning("Dataset doc not found in database yet")
            await asyncio.sleep(2.0)
        else:
            logger.error("Dataset indexing timed out")
            return False

        # Wait a small delay to make sure ChromaDB collection is updated
        await asyncio.sleep(2.0)

        # 5. Verify RAG Index exists
        logger.info("\n--- Step 5: Verifying RAG index exists ---")
        index_doc = await db.rag_indexes.find_one({"dataset_id": dataset_id})
        assert index_doc is not None, f"No RAG index document found for dataset {dataset_id}"
        index_id = str(index_doc["_id"])
        logger.info(f"Found RAG index document. ID: {index_id}, status: {index_doc.get('status')}")

        # 6. Test RAG Search / Query Retrieval
        logger.info("\n--- Step 6: Querying RAG Search ---")
        search_req = {
            "index_id": index_id,
            "query": "Who built Antigravity?",
            "top_k": 2
        }
        search_resp = await client.post("/api/v1/rag/search", headers=headers, json=search_req)
        logger.info(f"Search status: {search_resp.status_code}")
        assert search_resp.status_code == 200, f"Search query failed: {search_resp.text}"
        search_json = search_resp.json()
        logger.info(f"Search results: {search_json}")
        
        results = search_json.get("results", [])
        assert len(results) > 0, "No results returned from RAG search"
        
        # Verify content contains expected search tokens
        found = False
        for res in results:
            content = res.get("content", "")
            logger.info(f"Chunk content: {content}")
            if "Google DeepMind" in content or "Antigravity" in content:
                found = True
        assert found, "Expected keyword 'Google DeepMind' or 'Antigravity' not found in retrieved chunks"
        logger.info("RAG search and retrieval successfully verified!")

        # 7. Test RAG Chat
        logger.info("\n--- Step 7: Testing RAG Chat Answer Generation ---")
        chat_req = {
            "index_id": index_id,
            "question": "What is Antigravity?",
            "top_k": 2
        }
        chat_resp = await client.post("/api/v1/rag/chat", headers=headers, json=chat_req)
        logger.info(f"Chat status: {chat_resp.status_code}")
        assert chat_resp.status_code == 200, f"Chat query failed: {chat_resp.text}"
        chat_json = chat_resp.json()
        logger.info(f"Chat answer: {chat_json.get('answer')}")
        logger.info(f"Chat sources count: {len(chat_json.get('sources', []))}")
        
        # Clean up database records
        logger.info("\n--- Step 8: Cleaning up test data ---")
        await db.users.delete_many({"_id": ObjectId(test_user_id)})
        await db.datasets.delete_many({"_id": ObjectId(dataset_id)})
        await db.rag_indexes.delete_many({"dataset_id": dataset_id})
        
        # Clear ChromaDB collection
        from services.chroma_service import ChromaManager
        chroma_client = ChromaManager.get_client()
        try:
            chroma_client.delete_collection(index_id)
            logger.info(f"Deleted test ChromaDB collection: {index_id}")
        except Exception as ce:
            logger.warning(f"Could not delete ChromaDB collection (this is normal if it doesn't match ID): {ce}")

    await disconnect_db()
    logger.info("\nAll end-to-end RAG pipeline checks completed successfully!")
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_rag_flow())
        import sys
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            h_process = kernel32.GetCurrentProcess()
            kernel32.TerminateProcess(h_process, 0 if success is True else 1)
        else:
            import os as os_module
            os_module._exit(0 if success is True else 1)
    except BaseException:
        import sys
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            h_process = kernel32.GetCurrentProcess()
            kernel32.TerminateProcess(h_process, 2)
        else:
            import os as os_module
            os_module._exit(2)
