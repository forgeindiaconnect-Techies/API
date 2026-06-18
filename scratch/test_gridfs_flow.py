import sys
import os
import asyncio
import logging
import io

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from database import connect_db, get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_gridfs_flow")

async def test():
    await connect_db()
    db = get_db()
    
    if db is None or hasattr(db, "_db") and db._db.__class__.__name__ == "MockDB":
        logger.error("DB connection failed or using MockDB!")
        return
        
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket
    from bson import ObjectId
    import tempfile
    
    raw_db = db._db
    fs = AsyncIOMotorGridFSBucket(raw_db)
    
    test_bytes = b"Hello, this is a GridFS test file content!"
    filename = "test_gridfs_file.txt"
    
    # 1. Test Upload
    logger.info("Testing Upload to GridFS...")
    stream = io.BytesIO(test_bytes)
    gridfs_id = await fs.upload_from_stream(
        filename,
        stream,
        metadata={"content_type": "text/plain"}
    )
    logger.info(f"Upload Success! GridFS ID: {gridfs_id} (type: {type(gridfs_id)})")
    
    # 2. Test Download
    logger.info("Testing Download from GridFS...")
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    temp_path = temp_file.name
    temp_file.close()
    
    with open(temp_path, "wb") as f:
        await fs.download_to_stream(ObjectId(gridfs_id), f)
        
    with open(temp_path, "rb") as f:
        downloaded_content = f.read()
        
    logger.info(f"Downloaded Content: {downloaded_content}")
    assert downloaded_content == test_bytes
    logger.info("Download Success!")
    
    # Clean up temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)
        
    # 3. Clean up GridFS document
    logger.info("Cleaning up GridFS file...")
    await fs.delete(ObjectId(gridfs_id))
    logger.info("Cleanup Success!")
    
    logger.info("ALL GRIDFS TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(test())
