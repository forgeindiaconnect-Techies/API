import sys
import os
import asyncio
import httpx
from datetime import datetime

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db
from auth.utils import create_access_token
from main import app

async def run_tests():
    print("Connecting to DB...")
    await connect_db()
    db = get_db()

    # 1. Fetch or create a test user
    user = await db.users.find_one({"email": "danish@gmail.com"})
    if not user:
        print("Creating mock user...")
        user = {
            "name": "Danish",
            "email": "danish@gmail.com",
            "disabled": False,
            "role": "admin"
        }
        res = await db.users.insert_one(user)
        user["_id"] = res.inserted_id

    user_id = str(user["_id"])
    print(f"Using User: {user['email']} (ID: {user_id})")

    # Generate access token
    token = create_access_token({"sub": user_id, "email": user["email"]})
    headers = {"Authorization": f"Bearer {token}"}

    # Setup transport and client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:

        # --- Test 1: Fetch Dataset by String ID ---
        print("\n--- Test 1: Fetching Dataset by String ID ---")
        # Create a temp dataset
        dataset_doc = {
            "name": "Test Query Dataset",
            "file_name": "test_query.csv",
            "file_type": "csv",
            "size_bytes": 100,
            "status": "ready",
            "user_id": user_id,
            "created_at": datetime.utcnow()
        }
        ds_res = await db.datasets.insert_one(dataset_doc)
        dataset_str_id = str(ds_res.inserted_id)
        print(f"Created temp dataset with ID: {dataset_str_id}")

        # Query using route
        resp = await client.get(f"/api/v1/datasets/{dataset_str_id}", headers=headers)
        print("Fetch dataset response status:", resp.status_code)
        assert resp.status_code == 200, f"Failed to fetch dataset: {resp.text}"
        print("[OK] Dataset fetch verified.")

        # --- Test 2: Chat Conversation deletion and updates ---
        print("\n--- Test 2: Chat Conversation operations ---")
        # Create conversation
        conv_doc = {
            "title": "Test String ID Conv",
            "model": "llama3",
            "user_id": user_id,
            "message_count": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        c_res = await db.conversations.insert_one(conv_doc)
        conv_str_id = str(c_res.inserted_id)
        print(f"Created temp conversation with ID: {conv_str_id}")

        # Send a message (which calls update_one internally on conversation using string ID)
        print("Sending message...")
        msg_payload = {"content": "Hello computer"}
        resp = await client.post(f"/api/v1/chat/conversations/{conv_str_id}/messages", json=msg_payload, headers=headers)
        print("Send message status:", resp.status_code)
        assert resp.status_code == 200, f"Failed to send message: {resp.text}"
        print("[OK] Message sent and conversation updated successfully.")

        # Delete conversation using string ID
        print("Deleting conversation...")
        resp = await client.delete(f"/api/v1/chat/conversations/{conv_str_id}", headers=headers)
        print("Delete conversation status:", resp.status_code)
        assert resp.status_code == 200, f"Failed to delete conversation: {resp.text}"
        print("[OK] Conversation deleted successfully.")

        # --- Test 3: Model Training Status and Stop ---
        print("\n--- Test 3: Model Training operations ---")
        # Create training job
        job_doc = {
            "model_id": "test_model_123",
            "user_id": user_id,
            "status": "training",
            "progress": 10.0,
            "created_at": datetime.utcnow()
        }
        j_res = await db.training_jobs.insert_one(job_doc)
        job_str_id = str(j_res.inserted_id)
        print(f"Created training job with ID: {job_str_id}")

        # Fetch training status
        resp = await client.get(f"/api/v1/models/training/{job_str_id}", headers=headers)
        print("Get training status response:", resp.status_code)
        assert resp.status_code == 200, f"Failed to get training status: {resp.text}"
        print("[OK] Training status retrieved.")

        # Stop training
        resp = await client.post(f"/api/v1/models/training/{job_str_id}/stop", headers=headers)
        print("Stop training status:", resp.status_code)
        assert resp.status_code == 200, f"Failed to stop training: {resp.text}"
        print("[OK] Stop training successful.")

        # Cleanup dataset and job
        await db.datasets.delete_one({"_id": ds_res.inserted_id})
        await db.training_jobs.delete_one({"_id": j_res.inserted_id})
        print("\nCleanup completed.")

    print("\nAll string-ID verification checks passed successfully!")

if __name__ == '__main__':
    asyncio.run(run_tests())
