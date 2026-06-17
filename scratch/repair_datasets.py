import os
import sys
import asyncio
import logging
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("repair_datasets")

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ["MONGODB_URL"] = "mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0"
os.environ["MONGODB_DB_NAME"] = "personal_ai_studio"

from database import connect_db, get_db
from config import settings
from services.cloudinary_service import upload_file_to_cloudinary
from services.dataset_service import upload_file_to_gridfs, download_file_from_cloudinary

async def check_gridfs_exists(db, gridfs_id: str) -> bool:
    if not gridfs_id:
        return False
    try:
        fs = AsyncIOMotorGridFSBucket(db._db)
        cursor = fs.find({"_id": ObjectId(gridfs_id)})
        files = await cursor.to_list(length=1)
        return len(files) > 0
    except Exception as e:
        logger.warning(f"Error checking GridFS for ID {gridfs_id}: {e}")
        return False

async def main():
    logger.info("=== STARTING DATASETS REPAIR SCRIPT ===")
    await connect_db()
    db = get_db()
    if not db:
        logger.error("Failed to connect to database.")
        return

    # Check Cloudinary configuration
    cloudinary_configured = bool(settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET)
    if not cloudinary_configured:
        logger.warning("Cloudinary credentials are not configured in environment! Cloudinary repair uploads will skip.")

    # Find all datasets
    cursor = db.datasets.find()
    datasets = await cursor.to_list(length=None)
    logger.info(f"Scanning {len(datasets)} datasets in database...")

    repaired_count = 0
    failed_count = 0
    healthy_count = 0

    for idx, d in enumerate(datasets):
        dataset_id = str(d["_id"])
        name = d.get("name") or d.get("file_name") or "unknown"
        local_path = d.get("file_path")
        cloudinary_url = d.get("cloudinary_url") or d.get("secure_url")
        public_id = d.get("public_id")
        gridfs_id = d.get("gridfs_id")
        ext = d.get("file_type") or name.split(".")[-1].lower()

        logger.info(f"\n[{idx+1}/{len(datasets)}] Inspecting Dataset: '{name}' (ID: {dataset_id})")

        # 1. Resolve local path and check existence
        local_exists = False
        resolved_local_path = None
        if local_path:
            paths_to_try = [
                local_path,
                os.path.abspath(local_path),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", local_path)),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", local_path))
            ]
            for p in paths_to_try:
                if os.path.exists(p) and os.path.isfile(p):
                    local_exists = True
                    resolved_local_path = p
                    break
        
        # 2. Check backups
        has_cloudinary = bool(cloudinary_url)
        has_public_id = bool(public_id)
        
        # GridFS check
        gridfs_exists = False
        if gridfs_id:
            gridfs_exists = await check_gridfs_exists(db, gridfs_id)

        # Log current status
        logger.info(f"  - Local File: {'✓ Found' if local_exists else '✗ Missing'} ({local_path})")
        logger.info(f"  - Cloudinary URL: {'✓ Present' if has_cloudinary else '✗ Missing'} ({cloudinary_url})")
        logger.info(f"  - Public ID: {'✓ Present' if has_public_id else '✗ Missing'} ({public_id})")
        logger.info(f"  - GridFS Backup: {'✓ Verified in DB & FS' if gridfs_exists else '✗ Missing/Invalid'} ({gridfs_id})")

        # Determine if repair is needed
        needs_repair = not (local_exists and has_cloudinary and has_public_id and gridfs_exists)
        if not needs_repair:
            logger.info("  => Dataset is healthy and fully persisted. No repair needed.")
            healthy_count += 1
            continue

        logger.info("  => Dataset requires repair. Finding recovery content...")
        file_bytes = None
        
        # Recovery strategy:
        # A. Get bytes from local file
        if local_exists and resolved_local_path:
            try:
                with open(resolved_local_path, "rb") as f:
                    file_bytes = f.read()
                logger.info(f"  ✓ Recovered {len(file_bytes)} bytes from local file.")
            except Exception as e:
                logger.error(f"  Failed to read local file: {e}")

        # B. Get bytes from GridFS
        if file_bytes is None and gridfs_exists:
            try:
                fs = AsyncIOMotorGridFSBucket(db._db)
                grid_out = await fs.open_download_stream(ObjectId(gridfs_id))
                file_bytes = await grid_out.read()
                logger.info(f"  ✓ Recovered {len(file_bytes)} bytes from GridFS.")
            except Exception as e:
                logger.error(f"  Failed to download from GridFS: {e}")

        # C. Get bytes from Cloudinary
        if file_bytes is None and has_cloudinary:
            try:
                temp_path = await download_file_from_cloudinary(cloudinary_url)
                with open(temp_path, "rb") as f:
                    file_bytes = f.read()
                os.remove(temp_path)
                logger.info(f"  ✓ Recovered {len(file_bytes)} bytes from Cloudinary.")
            except Exception as e:
                logger.error(f"  Failed to download from Cloudinary: {e}")

        # If we failed to get bytes, we cannot repair the dataset!
        if file_bytes is None:
            logger.error("  ✗ Recovery Failed: No copies of file content exist anywhere. Cannot repair.")
            await db.datasets.update_one(
                {"_id": ObjectId(dataset_id)},
                {"$set": {"status": "failed", "error_message": "All backup and local files were lost (irrecoverable)."}}
            )
            failed_count += 1
            continue

        # Perform repairs
        updates = {}
        
        # 1. Restore local file copy if missing
        if not local_exists and local_path:
            try:
                backend_local_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", local_path))
                os.makedirs(os.path.dirname(backend_local_path), exist_ok=True)
                with open(backend_local_path, "wb") as f:
                    f.write(file_bytes)
                logger.info(f"  ✓ Restored local file copy at: {backend_local_path}")
                local_exists = True
            except Exception as e:
                logger.error(f"  Failed to write local file copy: {e}")

        # 2. Upload to Cloudinary if missing
        if (not has_cloudinary or not has_public_id) and cloudinary_configured:
            try:
                logger.info("  Uploading content to Cloudinary...")
                cloudinary_res = await upload_file_to_cloudinary(file_bytes, name, resource_type="raw")
                sec_url = cloudinary_res.get("secure_url") or cloudinary_res.get("url")
                pub_id = cloudinary_res.get("public_id")
                
                updates["cloudinary_url"] = sec_url
                updates["secure_url"] = sec_url
                updates["public_id"] = pub_id
                
                has_cloudinary = True
                has_public_id = True
                logger.info(f"  ✓ Cloudinary repair uploaded: {sec_url}")
            except Exception as e:
                logger.error(f"  Failed to upload repair copy to Cloudinary: {e}")

        # 3. Upload to GridFS if missing
        if not gridfs_exists:
            try:
                logger.info("  Uploading content to GridFS...")
                content_type = "application/octet-stream"
                if ext == "txt":
                    content_type = "text/plain"
                elif ext == "csv":
                    content_type = "text/csv"
                elif ext == "pdf":
                    content_type = "application/pdf"
                elif ext == "json":
                    content_type = "application/json"
                    
                new_gridfs_id = await upload_file_to_gridfs(file_bytes, name, content_type)
                if new_gridfs_id:
                    updates["gridfs_id"] = new_gridfs_id
                    gridfs_exists = True
                    logger.info(f"  ✓ GridFS repair uploaded, new ID: {new_gridfs_id}")
            except Exception as e:
                logger.error(f"  Failed to upload repair copy to GridFS: {e}")

        if updates:
            await db.datasets.update_one({"_id": ObjectId(dataset_id)}, {"$set": updates})
            logger.info(f"  ✓ Database record updated with: {updates}")
            repaired_count += 1
        else:
            logger.info("  ✓ File content recovered, local copy restored if possible. Database references were already complete.")
            repaired_count += 1

    logger.info("\n=== REPAIR SUMMARY ===")
    logger.info(f"Total datasets scanned: {len(datasets)}")
    logger.info(f"Healthy datasets (no action needed): {healthy_count}")
    logger.info(f"Successfully repaired / restored: {repaired_count}")
    logger.info(f"Failed to repair (irrecoverable): {failed_count}")
    logger.info("=======================")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
