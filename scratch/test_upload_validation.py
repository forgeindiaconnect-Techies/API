import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock
from fastapi import UploadFile, BackgroundTasks, HTTPException
import io

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ["MONGODB_URL"] = "mock_url"
os.environ["MONGODB_DB_NAME"] = "mock_db"

from config import settings
import database
from database import MockDB, DatabaseWrapper

# Override settings to have dummy values for Cloudinary (so the route tries it)
settings.CLOUDINARY_CLOUD_NAME = "dummy_cloud"
settings.CLOUDINARY_API_KEY = "dummy_key"
settings.CLOUDINARY_API_SECRET = "dummy_secret"

# Mock User class inheriting from dict
class MockUser(dict):
    def __init__(self, user_id):
        super().__init__()
        self["_id"] = user_id

async def run_test_cases():
    print("=== STARTING SYNCHRONOUS UPLOAD VALIDATION TESTS ===")

    # Initialize a new mock database for each test to keep them isolated
    mock_db = DatabaseWrapper(MockDB())
    database.db = mock_db

    mock_user = MockUser("user_abc")

    # Clean up upload directory for user_abc at startup
    user_upload_dir = os.path.join(settings.UPLOAD_DIR, "user_abc")
    if os.path.exists(user_upload_dir):
        import shutil
        shutil.rmtree(user_upload_dir)
        print("  Cleaned up user_abc uploads directory at startup.")

    # Helper to create dummy UploadFile
    def make_file():
        return UploadFile(
            file=io.BytesIO(b"prompt,response\nhello,world\npersist,test\n"),
            filename="validation_test.csv"
        )

    # Mock background tasks
    bg_tasks = BackgroundTasks()
    bg_tasks.add_task = AsyncMock()

    from api.routes.datasets import upload_dataset

    # --- Case 1: Both Cloudinary and GridFS fail ---
    print("\n[Case 1] Testing: Both Cloudinary and GridFS fail...")
    with patch("services.cloudinary_service.upload_file_to_cloudinary", side_effect=Exception("Cloudinary upload error")), \
         patch("services.dataset_service.upload_file_to_gridfs", side_effect=Exception("GridFS upload error")), \
         patch("services.dataset_service.build_index_for_dataset") as mock_build:
         
        try:
            await upload_dataset(
                background_tasks=bg_tasks,
                file=make_file(),
                current_user=mock_user
            )
            assert False, "Should have raised HTTPException!"
        except HTTPException as he:
            assert he.status_code == 500
            assert "Both Cloudinary and GridFS backup attempts failed" in he.detail
            print("  [OK] Correctly raised HTTP 500 error!")
            
            # Check database is empty
            db_docs = mock_db.datasets._collection._data
            assert len(db_docs) == 0, "No document should have been inserted in MongoDB!"
            print("  [OK] Database insertion was skipped!")
            
            # Check local file cleanup
            user_upload_dir = os.path.join(settings.UPLOAD_DIR, "user_abc")
            if os.path.exists(user_upload_dir):
                files = os.listdir(user_upload_dir)
                assert len(files) == 0, f"Expected 0 files in local upload directory, found: {files}"
            print("  [OK] Local file was cleaned up successfully!")
            mock_build.assert_not_called()

    # --- Case 2: Cloudinary fails, but GridFS succeeds ---
    print("\n[Case 2] Testing: Cloudinary fails, GridFS succeeds...")
    mock_db = DatabaseWrapper(MockDB())
    database.db = mock_db
    
    with patch("services.cloudinary_service.upload_file_to_cloudinary", side_effect=Exception("Cloudinary upload error")), \
         patch("services.dataset_service.upload_file_to_gridfs", return_value="dummy_gridfs_id_999") as mock_gridfs_upload, \
         patch("services.dataset_service.build_index_for_dataset") as mock_build:
         
        res = await upload_dataset(
            background_tasks=bg_tasks,
            file=make_file(),
            current_user=mock_user
        )
        assert res["status"] == "processing"
        
        # Verify db document
        db_docs = mock_db.datasets._collection._data
        assert len(db_docs) == 1
        doc = db_docs[0]
        assert doc["gridfs_id"] == "dummy_gridfs_id_999"
        assert doc["cloudinary_url"] is None
        assert doc["status"] == "processing"
        assert os.path.exists(doc["file_path"]), "Local copy should persist!"
        print("  [OK] Upload succeeded with GridFS backup only!")
        print("  [OK] Database record correctly saved gridfs_id and empty cloudinary_url.")
        
        # Cleanup local file
        if os.path.exists(doc["file_path"]):
            os.remove(doc["file_path"])
        mock_build.assert_not_called()

    # --- Case 3: Cloudinary succeeds, but GridFS fails ---
    print("\n[Case 3] Testing: Cloudinary succeeds, GridFS fails...")
    mock_db = DatabaseWrapper(MockDB())
    database.db = mock_db
    
    dummy_cloud_res = {
        "secure_url": "https://cloudinary.com/dummy.csv",
        "url": "http://cloudinary.com/dummy.csv",
        "public_id": "dummy_pub_id_111"
    }
    with patch("services.cloudinary_service.upload_file_to_cloudinary", return_value=dummy_cloud_res), \
         patch("services.dataset_service.upload_file_to_gridfs", return_value=""), \
         patch("services.dataset_service.build_index_for_dataset") as mock_build:
         
        res = await upload_dataset(
            background_tasks=bg_tasks,
            file=make_file(),
            current_user=mock_user
        )
        assert res["status"] == "processing"
        
        # Verify db document
        db_docs = mock_db.datasets._collection._data
        assert len(db_docs) == 1
        doc = db_docs[0]
        assert doc["gridfs_id"] is None
        assert doc["cloudinary_url"] == "https://cloudinary.com/dummy.csv"
        assert doc["public_id"] == "dummy_pub_id_111"
        assert os.path.exists(doc["file_path"]), "Local copy should persist!"
        print("  [OK] Upload succeeded with Cloudinary backup only!")
        print("  [OK] Database record correctly saved Cloudinary URL and empty gridfs_id.")
        
        # Cleanup local file
        if os.path.exists(doc["file_path"]):
            os.remove(doc["file_path"])
        mock_build.assert_not_called()

    # --- Case 4: Both succeed ---
    print("\n[Case 4] Testing: Both Cloudinary and GridFS succeed...")
    mock_db = DatabaseWrapper(MockDB())
    database.db = mock_db
    
    with patch("services.cloudinary_service.upload_file_to_cloudinary", return_value=dummy_cloud_res), \
         patch("services.dataset_service.upload_file_to_gridfs", return_value="dummy_gridfs_id_777"), \
         patch("services.dataset_service.build_index_for_dataset") as mock_build:
         
        res = await upload_dataset(
            background_tasks=bg_tasks,
            file=make_file(),
            current_user=mock_user
        )
        assert res["status"] == "processing"
        
        # Verify db document
        db_docs = mock_db.datasets._collection._data
        assert len(db_docs) == 1
        doc = db_docs[0]
        assert doc["gridfs_id"] == "dummy_gridfs_id_777"
        assert doc["cloudinary_url"] == "https://cloudinary.com/dummy.csv"
        assert doc["public_id"] == "dummy_pub_id_111"
        assert os.path.exists(doc["file_path"]), "Local copy should persist!"
        print("  [OK] Upload succeeded with both backups!")
        
        # Cleanup local file
        if os.path.exists(doc["file_path"]):
            os.remove(doc["file_path"])
        mock_build.assert_not_called()

    print("\n=== ALL SYNCHRONOUS UPLOAD VALIDATION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_test_cases())
