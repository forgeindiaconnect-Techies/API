import asyncio
import sys
import os
from bson import ObjectId

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db
from motor.motor_asyncio import AsyncIOMotorGridFSBucket

async def main():
    print("Connecting to MongoDB Atlas...")
    await connect_db()
    db = get_db()
    
    if db is None:
        print("Failed to connect to database!")
        return

    fs = AsyncIOMotorGridFSBucket(db._db)
    
    print("\nScanning datasets...")
    cursor = db.datasets.find({})
    async for dataset in cursor:
        dataset_id = dataset["_id"]
        name = dataset.get("name")
        file_path = dataset.get("file_path")
        gridfs_id = dataset.get("gridfs_id")
        
        print(f"\nChecking dataset: '{name}' (ID: {dataset_id})")
        if gridfs_id:
            print(f"  Already has GridFS ID: {gridfs_id}")
            continue
            
        if not file_path:
            print("  No file_path found in dataset document.")
            continue
            
        # Try to locate file locally
        # Since the database paths might be relative (e.g. ./uploads/...) we check relative to backend folder
        abs_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend', file_path))
        print(f"  Looking for file at: {abs_file_path}")
        
        if not os.path.exists(abs_file_path):
            # Try direct relative path if it's already absolute or structured differently
            if os.path.exists(file_path):
                abs_file_path = os.path.abspath(file_path)
            else:
                print(f"  File NOT found locally. Skipping migration for this file.")
                continue
                
        print(f"  Found file! Uploading to GridFS...")
        try:
            # Detect content type roughly
            content_type = "application/octet-stream"
            if name.endswith(".txt"):
                content_type = "text/plain"
            elif name.endswith(".csv"):
                content_type = "text/csv"
            elif name.endswith(".pdf"):
                content_type = "application/pdf"
            elif name.endswith(".docx"):
                content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                
            with open(abs_file_path, "rb") as f:
                new_gridfs_id = await fs.upload_from_stream(
                    name,
                    f,
                    metadata={"content_type": content_type}
                )
            
            print(f"  Successfully uploaded to GridFS with ID: {new_gridfs_id}")
            
            # Update database
            await db.datasets.update_one(
                {"_id": dataset_id},
                {"$set": {"gridfs_id": str(new_gridfs_id)}}
            )
            print("  Updated dataset document in MongoDB Atlas.")
            
        except Exception as e:
            print(f"  Error uploading file: {e}")

    print("\nMigration complete!")

if __name__ == '__main__':
    asyncio.run(main())
