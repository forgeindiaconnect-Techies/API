import os
import sys
import asyncio
from unittest.mock import patch, MagicMock
import httpx

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ["MONGODB_URL"] = "mock_url"
os.environ["MONGODB_DB_NAME"] = "mock_db"

from main import app
from auth.utils import get_current_user
import database
from database import DatabaseWrapper, MockDB

# Create a mock user
mock_user = {
    "_id": "6a2bcb589670afa5956d7759",
    "email": "demo@aistudio.com",
    "name": "Demo User",
    "role": "admin"
}

# Override auth dependency
app.dependency_overrides[get_current_user] = lambda: mock_user

async def main():
    print("=== STARTING REPROCESSING BODY OPTIONAL TESTS ===")
    
    # Initialize mock database
    mock_db = DatabaseWrapper(MockDB())
    database.db = mock_db
    
    # Insert mock user into DB
    mock_db._db.users._data.append(mock_user)
    
    # Insert a dummy dataset to reprocess
    dataset_id = "6a326c6aa92e442a38f061fe"
    dummy_doc = {
        "_id": database.convert_id(dataset_id),
        "user_id": "6a2bcb589670afa5956d7759",
        "name": "test.csv",
        "file_name": "test.csv",
        "file_path": "./uploads/test.csv",
        "file_type": "csv",
        "status": "pending",
        "recovery_attempts": 3
    }
    mock_db._db.datasets._data.append(dummy_doc)
    
    headers = {"Authorization": "Bearer dummy_token"}
    
    # Mock decode_token inside middleware and build_index_for_dataset
    with patch("middleware.decode_token", return_value={"sub": "6a2bcb589670afa5956d7759"}), \
         patch("services.dataset_service.build_index_for_dataset") as mock_build:
         
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            
            # 1. Test sending POST request with NO body at all
            print("\n[Case 1] POST with NO body...")
            response = await client.post(f"/api/v1/datasets/{dataset_id}/process", headers=headers)
            
            print(f"  Response Status: {response.status_code}")
            print(f"  Response JSON: {response.json()}")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            res_data = response.json()
            assert res_data["status"] == "processing"
            
            # Verify recovery_attempts got reset to 0 in DB
            db_doc = await mock_db.datasets.find_one({"_id": database.convert_id(dataset_id)})
            assert db_doc.get("recovery_attempts") == 0, f"Expected recovery_attempts to be 0, got {db_doc.get('recovery_attempts')}"
            print("  [OK] Successfully reprocessed with empty body and reset recovery_attempts!")

            # 2. Test sending POST request with empty JSON body {}
            print("\n[Case 2] POST with empty JSON body {}...")
            # Reset recovery_attempts
            await mock_db.datasets.update_one({"_id": database.convert_id(dataset_id)}, {"$set": {"recovery_attempts": 3}})
            
            response = await client.post(f"/api/v1/datasets/{dataset_id}/process", headers=headers, json={})
            print(f"  Response Status: {response.status_code}")
            print(f"  Response JSON: {response.json()}")
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            db_doc = await mock_db.datasets.find_one({"_id": database.convert_id(dataset_id)})
            assert db_doc.get("recovery_attempts") == 0
            print("  [OK] Successfully reprocessed with {} body!")

            mock_build.assert_called()

    # Clear overrides
    app.dependency_overrides.clear()
    print("\n=== ALL REPROCESSING BODY OPTIONAL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
