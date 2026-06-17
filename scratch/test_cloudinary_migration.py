import sys
import os
import asyncio
import logging
from bson import ObjectId
from unittest.mock import patch, MagicMock
import tempfile

# Add backend and workspace root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import connect_db, get_db
from config import settings

# Override config settings so the migration script configuration checks succeed
settings.CLOUDINARY_CLOUD_NAME = "dummy_cloud_name"
settings.CLOUDINARY_API_KEY = "dummy_api_key"
settings.CLOUDINARY_API_SECRET = "dummy_api_secret"

from services.cloudinary_service import upload_file_to_cloudinary
from services.dataset_service import get_dataset_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_cloudinary_migration")

# Mock User class
class MockUser(dict):
    def __init__(self, user_id):
        super().__init__()
        self["_id"] = user_id

# Helper to mock cloudinary.uploader.upload response
def mock_upload(file_bytes, **kwargs):
    resource_type = kwargs.get("resource_type", "raw")
    public_id = kwargs.get("public_id", "test_file.csv")
    return {
        "secure_url": f"https://res.cloudinary.com/dummy_cloud_name/{resource_type}/upload/v123456/{public_id}",
        "url": f"http://res.cloudinary.com/dummy_cloud_name/{resource_type}/upload/v123456/{public_id}",
        "public_id": public_id,
        "resource_type": resource_type
    }

async def main():
    await connect_db()
    db = get_db()
    
    if db is None:
        logger.error("Failed to connect to database!")
        return

    logger.info("Running Cloudinary Direct Upload test (with mocked cloudinary)...")
    test_content = b"header1,header2\nrow1val1,row1val2\n"
    test_filename = "test_raw_resource_type.csv"
    
    # 1. Verify Cloudinary upload succeeds and returns secure_url with mock
    with patch("cloudinary.uploader.upload", side_effect=mock_upload) as mock_cloudinary_upload:
        cloudinary_res = await upload_file_to_cloudinary(test_content, test_filename)
        logger.info(f"Cloudinary returned result: {cloudinary_res}")
        
        # Verify call arguments
        mock_cloudinary_upload.assert_called_once()
        args, kwargs = mock_cloudinary_upload.call_args
        assert kwargs.get("resource_type") == "raw", "Expected resource_type to be 'raw' for CSV!"
        
        assert "secure_url" in cloudinary_res, "secure_url missing from upload response!"
        assert cloudinary_res["secure_url"].startswith("https://"), "secure_url is not secure!"
        assert "public_id" in cloudinary_res, "public_id missing from upload response!"
        logger.info("✓ Cloudinary Direct Upload validation passed successfully!")

    # 2. Verify upload & status update database record save
    user_id = "6a2bcb589670afa5956d7759"
    current_user = MockUser(user_id)
    
    # Create mock dataset document missing cloudinary_url
    logger.info("Creating mock dataset document missing cloudinary_url...")
    dummy_doc = {
        "user_id": user_id,
        "name": "migration_test_file.csv",
        "file_name": "migration_test_file.csv",
        "file_type": "csv",
        "status": "pending",
        "file_path": "./uploads/6a2bcb589670afa5956d7759/migration_test_file.csv",
    }
    
    # Create the local directory and file if it doesn't exist
    local_dir = "./uploads/6a2bcb589670afa5956d7759"
    os.makedirs(local_dir, exist_ok=True)
    with open(dummy_doc["file_path"], "wb") as f:
        f.write(b"col1,col2\nval1,val2\n")
        
    res = await db.datasets.insert_one(dummy_doc)
    doc_id = res.inserted_id
    logger.info(f"Mock dataset document inserted with ID: {doc_id}")
    
    # Check that it's missing cloudinary_url
    inserted_doc = await db.datasets.find_one({"_id": doc_id})
    assert "cloudinary_url" not in inserted_doc, "Mock dataset document already contains cloudinary_url!"

    # Run the database migration script directly inside this process
    logger.info("Running migrate_cloudinary_urls.py migration script...")
    from scratch.migrate_cloudinary_urls import main as run_migration
    
    with patch("cloudinary.uploader.upload", side_effect=mock_upload) as mock_mig_upload:
        await run_migration()
        assert mock_mig_upload.call_count >= 1, "Expected at least 1 upload call during migration"
        logger.info(f"✓ Migration completed inside test runner context. Migrated {mock_mig_upload.call_count} records.")

    # Query document to confirm secure_url and cloudinary_url are set
    updated_doc = await db.datasets.find_one({"_id": doc_id})
    logger.info(f"Updated document after migration: {updated_doc}")
    
    assert updated_doc.get("cloudinary_url") is not None, "cloudinary_url is missing after migration!"
    assert updated_doc.get("secure_url") is not None, "secure_url is missing after migration!"
    assert updated_doc.get("public_id") is not None, "public_id is missing after migration!"
    assert updated_doc["cloudinary_url"].startswith("https://"), "cloudinary_url does not start with https!"
    logger.info("✓ Database record has valid secure_url and cloudinary_url.")

    # 3. Validate cloudinary_url exists and can be downloaded if local file is deleted
    logger.info("Deleting local copy of file to simulate container restart...")
    os.remove(dummy_doc["file_path"])
    
    # Mock download_file_from_cloudinary to return a temp path containing mock content
    def mock_download(url):
        temp_f = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        temp_f.write(b"col1,col2\nval1,val2\n")
        temp_f.close()
        return temp_f.name

    logger.info("Attempting to retrieve file via get_dataset_file (should download from Cloudinary URL)...")
    with patch("services.dataset_service.download_file_from_cloudinary", side_effect=mock_download) as mock_dl:
        temp_path, is_temp = await get_dataset_file(updated_doc)
        mock_dl.assert_called_once_with(updated_doc["cloudinary_url"])
        
    logger.info(f"Successfully retrieved file at temp path: {temp_path} (is_temp={is_temp})")
    assert is_temp == True, "Expected get_dataset_file to return is_temp=True since it downloaded from Cloudinary!"
    assert os.path.exists(temp_path), "Downloaded file temp path does not exist!"
    
    # Clean up temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)
        
    # 4. Clean up database mock dataset record
    await db.datasets.delete_one({"_id": doc_id})
    logger.info("Cleaned up mock dataset from DB.")
    
    logger.info("ALL CLOUDINARY MIGRATION PIPELINE VERIFICATION TESTS PASSED SUCCESSFULLY!")
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
