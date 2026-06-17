import sys
import os
import asyncio
import logging
from bson import ObjectId

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db
from config import settings
from services.cloudinary_service import upload_file_to_cloudinary
from services.dataset_service import download_file_from_gridfs
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_cloudinary_urls")

async def main():
    logger.info("Connecting to MongoDB Atlas...")
    await connect_db()
    db = get_db()
    
    if db is None:
        logger.error("Failed to connect to database!")
        return

    # Check Cloudinary configuration
    cloudinary_configured = bool(settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET)
    if not cloudinary_configured:
        logger.error("Cloudinary is not configured! Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in .env.")
        sys.exit(1)

    logger.info("Scanning database for datasets missing 'cloudinary_url'...")
    query = {
        "$or": [
            {"cloudinary_url": {"$in": [None, ""]}},
            {"cloudinary_url": {"$exists": False}},
            {"secure_url": {"$in": [None, ""]}},
            {"secure_url": {"$exists": False}}
        ]
    }
    
    cursor = db.datasets.find(query)
    datasets = await cursor.to_list(length=None)
    logger.info(f"Found {len(datasets)} datasets that need migration.")

    migration_success = 0
    migration_failed = 0

    for dataset in datasets:
        dataset_id = dataset["_id"]
        name = dataset.get("name") or dataset.get("file_name", "unknown")
        file_path = dataset.get("file_path")
        gridfs_id = dataset.get("gridfs_id")
        
        logger.info(f"Migrating dataset '{name}' (ID: {dataset_id})...")
        
        file_content = None
        # 1. Try to get file from GridFS first
        if gridfs_id:
            try:
                logger.info(f"  Fetching file from GridFS (ID: {gridfs_id})...")
                fs = AsyncIOMotorGridFSBucket(db._db)
                grid_out = await fs.open_download_stream(ObjectId(gridfs_id))
                file_content = await grid_out.read()
                logger.info(f"  Successfully retrieved {len(file_content)} bytes from GridFS.")
            except Exception as gf_err:
                logger.warning(f"  Failed to retrieve from GridFS: {gf_err}")

        # 2. Try to get file from local file path if GridFS failed or was missing
        if file_content is None and file_path:
            # Check multiple possible local locations
            paths_to_try = [
                file_path,
                os.path.abspath(file_path),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", file_path)),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", file_path))
            ]
            for p in paths_to_try:
                if os.path.exists(p) and os.path.isfile(p):
                    try:
                        with open(p, "rb") as f:
                            file_content = f.read()
                        logger.info(f"  Successfully read {len(file_content)} bytes from local path: {p}")
                        break
                    except Exception as read_err:
                        logger.warning(f"  Failed to read file from path {p}: {read_err}")

        if file_content is None:
            logger.error(f"  Could not find any file content locally or in GridFS for dataset '{name}'. Skipping.")
            migration_failed += 1
            continue

        # 3. Upload content to Cloudinary
        try:
            logger.info(f"  Uploading file content to Cloudinary...")
            cloudinary_res = await upload_file_to_cloudinary(file_content, name)
            sec_url = cloudinary_res.get("secure_url") or cloudinary_res.get("url")
            public_id = cloudinary_res.get("public_id")
            
            logger.info(f"  Cloudinary upload succeeded. secure_url: {sec_url}")
            
            # Update MongoDB record
            await db.datasets.update_one(
                {"_id": dataset_id},
                {"$set": {
                    "cloudinary_url": sec_url,
                    "secure_url": sec_url,
                    "public_id": public_id
                }}
            )
            logger.info(f"  ✓ Successfully updated MongoDB dataset record with Cloudinary attributes.")
            migration_success += 1
        except Exception as upload_err:
            logger.error(f"  Cloudinary upload or MongoDB update failed: {upload_err}")
            migration_failed += 1

    logger.info(f"Migration completed. Success: {migration_success}, Failed: {migration_failed}")

if __name__ == "__main__":
    asyncio.run(main())
