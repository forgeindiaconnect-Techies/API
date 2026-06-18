import sys
import os
import asyncio
import logging
from bson import ObjectId

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

import database
from config import settings
from vector_db.store import VectorStore
from api.routes.datasets import delete_dataset

async def test_dataset_deletion():
    # Configure settings and database connection
    settings.MONGODB_URL = 'mongodb+srv://danish_ai:Danish%4021@cluster0.e8trmtg.mongodb.net/?appName=Cluster0'
    settings.MONGODB_DB_NAME = 'personal_ai_studio'
    
    await database.connect_db()
    db = database.get_db()
    
    # 1. Create a dummy user info
    current_user = {
        "_id": "6a213b5f4f5a5a8a0249f24b",
        "email": "danish@gmail.com"
    }
    user_id_str = current_user["_id"]
    
    # 2. Create a dummy raw local file
    user_upload_dir = os.path.join(settings.UPLOAD_DIR, user_id_str)
    os.makedirs(user_upload_dir, exist_ok=True)
    temp_file_path = os.path.join(user_upload_dir, "test_delete_temp.txt")
    with open(temp_file_path, "w", encoding="utf-8") as f:
        f.write("This is some dummy content to test complete dataset deletion.")
    
    logger.info(f"Created dummy local file at: {temp_file_path}")
    
    # 3. Insert a dummy dataset record in MongoDB
    dataset_doc = {
        "file_name": "test_delete_temp.txt",
        "name": "test_delete_temp.txt",
        "file_type": "txt",
        "file_path": temp_file_path,
        "size_bytes": os.path.getsize(temp_file_path),
        "status": "indexed",
        "user_id": user_id_str,
    }
    from datetime import datetime
    dataset_doc["created_at"] = datetime.utcnow()
    
    ds_res = await db.datasets.insert_one(dataset_doc)
    dataset_id = str(ds_res.inserted_id)
    logger.info(f"Created dummy dataset record with ID: {dataset_id}")
    
    # 4. Insert a dummy RAG index record in MongoDB
    index_doc = {
        "name": "test_delete_temp.txt index",
        "dataset_id": dataset_id,
        "embedding_model": "paraphrase-MiniLM-L3-v2",
        "index_type": "chroma",
        "status": "ready",
        "user_id": user_id_str,
        "created_at": datetime.utcnow()
    }
    idx_res = await db.rag_indexes.insert_one(index_doc)
    index_id = str(idx_res.inserted_id)
    logger.info(f"Created dummy RAG index record with ID: {index_id}")
    
    # 5. Populate a dummy ChromaDB collection for this RAG index
    store = VectorStore(backend="chroma", collection_name=index_id)
    # Ensure initialized creates the collection
    await store.ensure_initialized()
    logger.info(f"ChromaDB collection '{index_id}' initialized")
    
    # Add dummy documents to the collection
    await store.add_documents(
        documents=["test chunk 1", "test chunk 2"],
        embeddings=[[0.1]*384, [0.2]*384],
        metadatas=[{"source": "test"}, {"source": "test"}],
        ids=[f"{index_id}_0", f"{index_id}_1"]
    )
    count_before = await store.count()
    logger.info(f"ChromaDB collection document count before deletion: {count_before}")
    assert count_before == 2, "ChromaDB collection count should be 2"
    
    # 6. Call delete_dataset endpoint logic
    logger.info(f"Triggering delete_dataset for ID: {dataset_id}")
    delete_res = await delete_dataset(dataset_id=dataset_id, current_user=current_user)
    logger.info(f"Delete response: {delete_res}")
    
    # 7. Asserts to verify deletion cleanup
    # Check dataset document deleted
    db_ds = await db.datasets.find_one({"_id": ObjectId(dataset_id)})
    logger.info(f"Verifying dataset document deletion: {db_ds}")
    assert db_ds is None, "Dataset document was not deleted from MongoDB!"
    
    # Check RAG index document deleted
    db_idx = await db.rag_indexes.find_one({"dataset_id": dataset_id})
    logger.info(f"Verifying RAG index document deletion: {db_idx}")
    assert db_idx is None, "RAG index document was not deleted from MongoDB!"
    
    # Check local file deleted
    file_exists = os.path.exists(temp_file_path)
    logger.info(f"Verifying local file deletion: File exists = {file_exists}")
    assert not file_exists, "Local file was not deleted from disk!"
    
    # Check ChromaDB collection deleted
    # Instantiate store again, trying to count or query should show collection was deleted
    store_after = VectorStore(backend="chroma", collection_name=index_id)
    await store_after.ensure_initialized()
    count_after = await store_after.count()
    logger.info(f"Verifying ChromaDB collection deletion: count after = {count_after}")
    assert count_after == 0, "ChromaDB collection was not deleted or is not empty!"
    
    logger.info("SUCCESS: All cleanup assertions passed! Complete dataset deletion works perfectly.")
    await database.disconnect_db()

if __name__ == '__main__':
    asyncio.run(test_dataset_deletion())
