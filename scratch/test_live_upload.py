import os
import sys
import asyncio
import logging
import zipfile
import tempfile
import hashlib
from datetime import datetime
import httpx

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from main import app
from database import connect_db, get_db, disconnect_db
from auth.utils import create_access_token, hash_password
from bson import ObjectId

# Reset logging
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("test_live_upload")

# Use ctypes TerminateProcess to avoid the PyTorch teardown segfault on Windows
def win32_exit(exit_code=0):
    try:
        import ctypes
        logger.info(f"Exiting cleanly on Windows (exit code: {exit_code}) via TerminateProcess...")
        ctypes.windll.kernel32.TerminateProcess(ctypes.windll.kernel32.GetCurrentProcess(), exit_code)
    except Exception as e:
        logger.warning(f"Fallback to standard exit: {e}")
        sys.exit(exit_code)

async def run_verification():
    logger.info("Connecting to DB...")
    await connect_db()
    db = get_db()
    if db is None:
        logger.error("Database connection unavailable")
        win32_exit(1)

    # 1. Setup Test User
    logger.info("Setting up test user...")
    test_user_id = "6b0000000000000000000002"
    await db.users.delete_many({"_id": {"$in": [test_user_id, ObjectId(test_user_id)]}})
    await db.users.delete_many({"email": "upload_test_user@example.com"})
    await db.datasets.delete_many({"user_id": test_user_id})
    await db.rag_indexes.delete_many({"user_id": test_user_id})
    
    user_doc = {
        "_id": ObjectId(test_user_id),
        "email": "upload_test_user@example.com",
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
        
        # Test 1: Uploading file with invalid extension
        logger.info("\n--- Test 1: File Extension Validation ---")
        files_invalid = {
            "file": ("malicious.exe", b"fake binary data", "application/octet-stream")
        }
        resp = await client.post("/api/v1/datasets/upload", headers=headers, files=files_invalid)
        logger.info(f"Response status (expected 400): {resp.status_code}")
        logger.info(f"Response: {resp.text}")
        assert resp.status_code == 400, "Should have rejected executable file"

        # Test 2: Upload valid file and wait for processing completion
        logger.info("\n--- Test 2: Valid File Processing & API Telemetry ---")
        content_txt = "Antigravity is a deep reinforcement learning coding assistant."
        files_txt = {
            "file": ("assistant.txt", content_txt.encode("utf-8"), "text/plain")
        }
        resp = await client.post("/api/v1/datasets/upload", headers=headers, files=files_txt)
        logger.info(f"Response status (expected 202): {resp.status_code}")
        assert resp.status_code == 202, f"Upload failed: {resp.text}"
        
        upload_data = resp.json()
        dataset_id = upload_data.get("id")
        logger.info(f"Dataset uploaded successfully. ID: {dataset_id}")
        
        # Poll status
        logger.info("Polling dataset status...")
        max_attempts = 15
        dataset_finished = False
        for attempt in range(max_attempts):
            status_resp = await client.get(f"/api/v1/datasets/{dataset_id}/status", headers=headers)
            status_json = status_resp.json()
            status = status_json.get("status")
            logger.info(f"Attempt {attempt+1}: Status = {status}, Progress = {status_json.get('progress')}%")
            if status in ("indexed", "ready", "completed"):
                dataset_finished = True
                # Validate stats are present in the response
                logger.info(f"Status stats response: {status_json}")
                assert "chunk_count" in status_json, "Missing chunk_count"
                assert "embedding_count" in status_json, "Missing embedding_count"
                assert "processing_time" in status_json, "Missing processing_time"
                assert status_json["chunk_count"] > 0, "Chunk count should be > 0"
                break
            elif status == "failed":
                logger.error(f"Processing failed: {status_json}")
                break
            await asyncio.sleep(2.0)
            
        assert dataset_finished, "Dataset indexing did not complete in time"

        # Test 3: Check database-stored chunk metadata
        logger.info("\n--- Test 3: Verify MongoDB Chunk Metadata Storage ---")
        chunks_count = await db.dataset_chunks.count_documents({"dataset_id": dataset_id})
        logger.info(f"Found {chunks_count} chunks stored in MongoDB 'dataset_chunks'")
        assert chunks_count > 0, "No chunks stored in MongoDB dataset_chunks collection"
        
        first_chunk = await db.dataset_chunks.find_one({"dataset_id": dataset_id})
        logger.info(f"First chunk document: {first_chunk}")
        assert "chunk_text" in first_chunk, "Missing chunk_text field in chunk document"
        assert "index_id" in first_chunk, "Missing index_id field in chunk document"

        # Test 4: Prevent duplicate upload
        logger.info("\n--- Test 4: Duplicate Upload Check (MD5 Content Hash) ---")
        resp_dup = await client.post("/api/v1/datasets/upload", headers=headers, files=files_txt)
        logger.info(f"Duplicate upload response status (expected 409): {resp_dup.status_code}")
        logger.info(f"Response: {resp_dup.text}")
        assert resp_dup.status_code == 409, "Should block duplicate content uploads"

        # Test 5: ZIP archive processing
        logger.info("\n--- Test 5: ZIP File Parsing & Extraction ---")
        zip_temp_fd, zip_temp_path = tempfile.mkstemp(suffix=".zip")
        os.close(zip_temp_fd)
        
        with zipfile.ZipFile(zip_temp_path, "w") as zip_file:
            zip_file.writestr("notes.txt", "RAG architectures combine information retrieval with generation.")
            zip_file.writestr("topic.csv", "key,desc\nLLM,Large Language Model\nChromaDB,Vector Database")
            
        try:
            with open(zip_temp_path, "rb") as zf:
                files_zip = {
                    "file": ("archive.zip", zf.read(), "application/zip")
                }
            resp_zip = await client.post("/api/v1/datasets/upload", headers=headers, files=files_zip)
            logger.info(f"ZIP upload response status (expected 202): {resp_zip.status_code}")
            assert resp_zip.status_code == 202, f"ZIP upload failed: {resp_zip.text}"
            
            zip_dataset_id = resp_zip.json().get("id")
            
            # Poll status of ZIP dataset
            logger.info("Polling ZIP dataset indexing status...")
            zip_finished = False
            for attempt in range(max_attempts):
                status_resp = await client.get(f"/api/v1/datasets/{zip_dataset_id}/status", headers=headers)
                status_json = status_resp.json()
                status = status_json.get("status")
                logger.info(f"ZIP Attempt {attempt+1}: Status = {status}, Progress = {status_json.get('progress')}%")
                if status in ("indexed", "ready", "completed"):
                    zip_finished = True
                    break
                await asyncio.sleep(2.0)
                
            assert zip_finished, "ZIP indexing did not complete"
            
            # Verify ZIP chunks in MongoDB dataset_chunks
            zip_chunks = await db.dataset_chunks.find({"dataset_id": zip_dataset_id}).to_list(length=100)
            logger.info(f"Extracted {len(zip_chunks)} chunks from ZIP archive.")
            for c in zip_chunks:
                logger.info(f"Chunk text from ZIP inner file: {c.get('chunk_text')}")
                
            assert len(zip_chunks) >= 2, "Expected at least 2 chunks (one from notes.txt and one/more from topic.csv)"
            
            # Verify RAG search retrieval on ZIP content
            index_doc = await db.rag_indexes.find_one({"dataset_id": zip_dataset_id})
            assert index_doc is not None, "Missing index doc for ZIP dataset"
            zip_index_id = str(index_doc["_id"])
            
            logger.info("Querying RAG search over ZIP content...")
            search_req = {
                "index_id": zip_index_id,
                "query": "RAG architectures",
                "top_k": 2
            }
            search_resp = await client.post("/api/v1/rag/search", headers=headers, json=search_req)
            assert search_resp.status_code == 200, f"RAG search query failed: {search_resp.text}"
            search_json = search_resp.json()
            logger.info(f"RAG search response for ZIP: {search_json}")
            results = search_json.get("results", [])
            assert len(results) > 0, "No search results returned for ZIP query"
            
            found_zip_content = False
            for res in results:
                content = res.get("content", "")
                if "RAG architectures" in content or "notes.txt" in content:
                    found_zip_content = True
            assert found_zip_content, "Could not retrieve parsed zip chunk content via RAG search"
            logger.info("ZIP dataset end-to-end processing and search validated successfully!")
            
        finally:
            if os.path.exists(zip_temp_path):
                os.remove(zip_temp_path)

    await disconnect_db()
    logger.info("All tests passed successfully!")
    win32_exit(0)

if __name__ == "__main__":
    asyncio.run(run_verification())
