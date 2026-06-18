import os
import sys
import asyncio
from unittest.mock import patch, MagicMock
import httpx
from fastapi import HTTPException

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
    print("=== STARTING DATASET STATUS ENDPOINT DIAGNOSTIC TESTS ===")
    
    # Initialize mock database
    mock_db = DatabaseWrapper(MockDB())
    database.db = mock_db
    
    # Insert mock user into DB
    mock_db._db.users._data.append(mock_user)
    
    # Insert a dummy dataset
    dataset_id = "6a326c6aa92e442a38f061fe"
    dummy_doc = {
        "_id": database.convert_id(dataset_id),
        "user_id": "6a2bcb589670afa5956d7759",
        "name": "test.csv",
        "file_name": "test.csv",
        "file_path": "./uploads/test.csv",
        "file_type": "csv",
        "status": "processing",
        "error_message": None
    }
    mock_db._db.datasets._data.append(dummy_doc)
    
    headers = {"Authorization": "Bearer dummy_token"}
    
    # Mock decode_token inside middleware
    with patch("middleware.decode_token", return_value={"sub": "6a2bcb589670afa5956d7759"}), \
         patch("services.chroma_service.ChromaManager.get_client") as mock_chroma_client:
         
        # Configure ChromaDB mock client
        mock_client_instance = MagicMock()
        mock_client_instance.heartbeat.return_value = 123456789
        mock_chroma_client.return_value = mock_client_instance

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            
            # 1. Test standard status fetch (should return 200, status processing, progress 50)
            print("\n[Case 1] Fetching status for processing dataset without RAG index doc...")
            response = await client.get(f"/api/v1/datasets/{dataset_id}/status", headers=headers)
            print(f"  Response Status: {response.status_code}")
            print(f"  Response JSON: {response.json()}")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "processing"
            assert data["progress"] == 50
            assert data["mongodb_connected"] is True
            assert data["chromadb_connected"] is True

            # 2. Test status fetch with RAG index doc present (progress 75%)
            print("\n[Case 2] Fetching status with RAG index doc showing progress 75%...")
            dummy_index = {
                "dataset_id": dataset_id,
                "status": "building",
                "progress": 75.0,
                "error": None
            }
            mock_db._db.rag_indexes._data.append(dummy_index)
            
            response = await client.get(f"/api/v1/datasets/{dataset_id}/status", headers=headers)
            print(f"  Response Status: {response.status_code}")
            print(f"  Response JSON: {response.json()}")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "processing"
            assert data["progress"] == 75.0
            
            # 3. Test ChromaDB offline (should return 500 error cleanly in JSON instead of crashing)
            print("\n[Case 3] Fetching status when ChromaDB fails heartbeat...")
            mock_client_instance.heartbeat.side_effect = Exception("ChromaDB connection refused")
            response = await client.get(f"/api/v1/datasets/{dataset_id}/status", headers=headers)
            print(f"  Response Status: {response.status_code}")
            print(f"  Response JSON: {response.json()}")
            assert response.status_code == 500
            assert "refused" in response.json()["detail"]

    # Clear overrides
    app.dependency_overrides.clear()
    print("\n=== ALL DATASET STATUS ENDPOINT TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
