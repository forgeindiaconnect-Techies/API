import sys
import os
import asyncio
import logging

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

import database
from config import settings

async def run_local_build():
    # Force low memory mode to use HashingTFIDFEmbedder
    os.environ["LOW_MEMORY_MODE"] = "true"
    
    # Connect to MongoDB Atlas
    settings.MONGODB_URL = 'mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0'
    settings.MONGODB_DB_NAME = 'personal_ai_studio'
    
    await database.connect_db()
    db = database.get_db()
    
    # Find the latest dataset in processing status
    dataset_doc = await db.datasets.find_one({"status": "processing"}, sort=[("created_at", -1)])
    if not dataset_doc:
        # Fall back to any dataset
        dataset_doc = await db.datasets.find_one({}, sort=[("created_at", -1)])
        
    if not dataset_doc:
        print("No datasets found in database!")
        return

    print(f"Testing index build for Dataset ID: {dataset_doc['_id']}, Name: {dataset_doc.get('name')}")
    
    from services.dataset_service import build_index_for_dataset
    try:
        index_id = await build_index_for_dataset(dataset_doc, db)
        print("Build Succeeded! Index ID:", index_id)
    except Exception as e:
        print("Build Failed with Exception:", e)
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(run_local_build())
