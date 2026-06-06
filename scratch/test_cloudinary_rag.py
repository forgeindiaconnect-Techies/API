import sys
import os
import asyncio
import logging
from unittest.mock import patch, MagicMock, AsyncMock

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import database
from database import MockDB, DatabaseWrapper

# Setup mock database
mock_db = DatabaseWrapper(MockDB())
database.db = mock_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_cloudinary_rag")

async def test_cloudinary_upload_and_indexing():
    logger.info("=== Starting Cloudinary & RAG Pipeline Tests ===")

    # 1. Mock Cloudinary Upload
    from services.cloudinary_service import upload_file_to_cloudinary
    with patch("cloudinary.uploader.upload") as mock_upload:
        mock_upload.return_value = {
            "secure_url": "https://res.cloudinary.com/dummy/raw/upload/v123456/sample.txt",
            "public_id": "sample.txt"
        }
        res = await upload_file_to_cloudinary(b"hello world", "sample.txt")
        logger.info(f"Mock Cloudinary Upload Result: {res}")
        assert res["url"] == "https://res.cloudinary.com/dummy/raw/upload/v123456/sample.txt"
        assert res["public_id"] == "sample.txt"

    # 2. Mock Download & Indexing
    from services.dataset_service import build_index_for_dataset
    
    from bson import ObjectId

    # Create a dummy dataset doc in MongoDB
    dataset_doc = {
        "_id": ObjectId("6a21429591ef830d2aa4b9f0"),
        "name": "sample.txt",
        "file_name": "sample.txt",
        "file_type": "txt",
        "size_bytes": 100,
        "cloudinary_url": "https://res.cloudinary.com/dummy/raw/upload/v123456/sample.txt",
        "public_id": "sample.txt",
        "status": "pending",
        "user_id": "user_123"
    }
    mock_db.datasets._collection._data.append(dataset_doc)

    # Pre-create index doc with a 24-character ID to avoid ChromaDB collection name format validation failure (length >= 3)
    index_doc = {
        "_id": "idx_6a21429591ef830d2aa4b9f0",
        "name": "sample.txt index",
        "dataset_id": "6a21429591ef830d2aa4b9f0",
        "embedding_model": "all-MiniLM-L6-v2",
        "chunk_size": 512,
        "chunk_overlap": 50,
        "index_type": "chroma",
        "chunk_count": 0,
        "status": "building",
        "user_id": "user_123"
    }
    mock_db.rag_indexes._collection._data.append(index_doc)

    # Let's mock download_file_from_cloudinary to return a temp file with content
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    temp_file.write(b"This is a test document about artificial intelligence and RAG pipelines.\nIt contains useful facts.")
    temp_file.close()
    temp_path = temp_file.name

    async def mock_download(url):
        return temp_path

    # Let's patch download_file_from_cloudinary and _process_sync
    with patch("services.dataset_service.download_file_from_cloudinary", side_effect=mock_download), \
         patch("services.dataset_service._process_sync") as mock_proc:
         
        mock_proc.return_value = {
            "rows": 2,
            "cols": 0,
            "columns": [],
            "metadata": {}
        }
        
        index_id = await build_index_for_dataset(dataset_doc, mock_db)
        logger.info(f"Build index completed. Index ID: {index_id}")
        assert index_id is not None
        
        # Verify dataset document in DB is updated to status 'indexed'
        updated_dataset = await mock_db.datasets.find_one({"_id": dataset_doc["_id"]})
        logger.info(f"Updated Dataset Document: {updated_dataset}")
        assert updated_dataset["status"] == "indexed"
        
        # Verify index document status is 'ready'
        index_doc = await mock_db.rag_indexes.find_one({"dataset_id": str(dataset_doc["_id"])})
        logger.info(f"Updated Index Document: {index_doc}")
        assert index_doc["status"] == "ready"
        assert index_doc["chunk_count"] > 0

    # Clean up temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)

    # 3. Test query_dataset_rag in chat_service
    from services.chat_service import query_dataset_rag
    
    logger.info("Testing query_dataset_rag with offline LLM fallback (Dataset-Only RAG)...")
    
    with patch("services.chat_service.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = ""
        mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"
        
        with patch("services.chat_service.AsyncClient.generate", side_effect=Exception("Ollama offline")):
            response = await query_dataset_rag(index_id, "artificial intelligence", top_k=2, db=mock_db)
            logger.info(f"Query response: {response}")
            assert "According to the dataset" in response["answer"]
            assert "artificial intelligence" in response["answer"].lower()
            assert len(response["sources"]) > 0

    # 4. Test Startup Recovery
    from services.startup_rebuild import run_startup_recovery
    
    # Mock find method for datasets to handle the status $in query for MockDB
    original_find = database.CollectionWrapper.find
    def mock_find(self, query=None, *args, **kwargs):
        if query and "status" in query and isinstance(query["status"], dict) and "$in" in query["status"]:
            query = query.copy()
            del query["status"]
        return original_find(self, query, *args, **kwargs)
    database.CollectionWrapper.find = mock_find

    logger.info("Testing startup recovery rebuild logic...")
    
    with patch("services.startup_rebuild.collection_is_empty", return_value=True) as mock_empty_check, \
         patch("services.startup_rebuild.build_index_for_dataset", new_callable=AsyncMock) as mock_rebuild:
         
         await run_startup_recovery()
         
         # Assert empty check was called with our index_id
         mock_empty_check.assert_called_with(index_id)
         # Assert rebuild was triggered for our dataset
         assert mock_rebuild.call_count == 1
         logger.info("Startup recovery successfully detected empty ChromaDB collection and triggered rebuild!")

    logger.info("=== All Cloudinary & RAG Tests Passed Successfully! ===")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_cloudinary_upload_and_indexing())
    sys.exit(0 if success else 1)
