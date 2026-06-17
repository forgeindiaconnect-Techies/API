import sys
import os
import asyncio
from unittest.mock import patch, MagicMock

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from config import settings
# Override credentials to empty to force fallback
settings.CLOUDINARY_CLOUD_NAME = ""
settings.CLOUDINARY_API_KEY = ""
settings.CLOUDINARY_API_SECRET = ""

import database
from database import MockDB, DatabaseWrapper
mock_db = DatabaseWrapper(MockDB())
database.db = mock_db

# Create a dummy current_user
class MockUser:
    def __getitem__(self, key):
        if key == "_id":
            return "user_123"
        raise KeyError(key)

async def test_fallback():
    from api.routes.datasets import upload_dataset
    from fastapi import UploadFile, BackgroundTasks
    
    # 1. Prepare dummy upload file
    import io
    dummy_file = UploadFile(
        file=io.BytesIO(b"Col1,Col2\nVal1,Val2\nVal3,Val4"),
        filename="test_fallback.csv"
    )
    
    # Mock background tasks
    bg_tasks = BackgroundTasks()
    bg_tasks.add_task = MagicMock()
    
    # Mock database insertion
    mock_user = MockUser()
    
    print("Testing upload_dataset route with missing Cloudinary credentials...")
    
    # Patch the background task to not run the actual indexing
    with patch("services.dataset_service.build_index_for_dataset") as mock_build:
        res = await upload_dataset(
            background_tasks=bg_tasks,
            file=dummy_file,
            current_user=mock_user
        )
        print("Upload Response:", res)
        
        # Verify result fields
        assert res["name"] == "test_fallback.csv"
        assert res["status"] == "pending"
        
        # Check database document
        inserted_docs = mock_db.datasets._collection._data
        assert len(inserted_docs) == 1
        doc = inserted_docs[0]
        assert doc["cloudinary_url"] is None
        assert doc["public_id"] is None
        assert doc["file_path"] is not None
        assert os.path.exists(doc["file_path"])
        print("Local file path saved:", doc["file_path"])
        
        # Clean up
        if os.path.exists(doc["file_path"]):
            os.remove(doc["file_path"])
            print("Cleaned up local test file.")
            
    print("SUCCESS: Fallback storage verification passed!")

if __name__ == "__main__":
    asyncio.run(test_fallback())
