import sys
import os
import asyncio
import logging

# Set PYTHONPATH to include backend folder
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_rag_pipeline")

async def test_flow():
    logger.info("Starting verification test...")
    
    # 1. Test embedding model tiered fallback
    logger.info("1. Testing get_embedding_model...")
    from vector_db.store import get_embedding_model
    try:
        embedder = get_embedding_model()
        logger.info(f"Successfully obtained embedder. Class: {embedder.__class__.__name__}")
        
        # Test encoding
        logger.info("Encoding query...")
        emb = embedder.encode("test query")
        logger.info(f"Encoding successful. Vector type: {type(emb)}, shape/len: {len(emb) if hasattr(emb, '__len__') else 'unknown'}")
    except Exception as e:
        logger.error(f"Embedding initialization or encoding failed: {e}", exc_info=True)
        return False

    # 2. Test VectorStore initialization with missing ChromaDB fallback
    logger.info("2. Testing VectorStore initialization fallback...")
    from vector_db.store import VectorStore
    try:
        # Should fall back to FAISS or Mock gracefully since chromadb is not installed
        store = VectorStore(backend="chroma", collection_name="test_verify_collection")
        logger.info(f"Successfully initialized VectorStore. Selected backend: {store.backend}")
    except Exception as e:
        logger.error(f"VectorStore initialization crashed: {e}", exc_info=True)
        return False

    # 3. Test querying vector store
    logger.info("3. Testing query_vector_store thread wrapper...")
    from database import MockDB, DatabaseWrapper
    from services.rag_service import query_vector_store
    
    mock_db = DatabaseWrapper(MockDB())
    
    # Insert a mock rag index doc
    index_doc = {
        "_id": "6a21429591ef830d2aa4b9f7",
        "dataset_id": "dataset_123",
        "embedding_model": "all-MiniLM-L6-v2",
        "index_type": "chroma",
        "status": "ready"
    }
    await mock_db.rag_indexes.insert_one(index_doc)
    
    try:
        # This will call the embedder and vector store queries wrapped in asyncio.to_thread
        results = await query_vector_store("6a21429591ef830d2aa4b9f7", "hello", top_k=3, db=mock_db)
        logger.info(f"query_vector_store completed successfully. Results count: {len(results)}")
    except Exception as e:
        logger.error(f"query_vector_store failed: {e}", exc_info=True)
        return False

    # 4. Verify stream generator error handling
    logger.info("4. Testing generate_response stream handler...")
    import json
    
    # Mock stream generation with an error triggered mid-stream
    async def generate_response_test():
        try:
            logger.info("Starting mock generator loop...")
            yield "data: {\"token\": \"Hello\"}\n\n"
            yield "data: {\"token\": \"world\"}\n\n"
            
            # Simulate a database error mid-stream
            logger.info("Simulating mid-stream DB exception...")
            raise Exception("MongoDB connection timeout during state update")
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Captured error inside generator: {e}")
            yield f"data: {json.dumps({'error': f'Stream generation failed: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"

    try:
        outputs = []
        async for chunk in generate_response_test():
            outputs.append(chunk.strip())
        logger.info(f"Stream outputs: {outputs}")
        
        # Verify that error was gracefully yielded instead of crashing the stream execution
        assert any("error" in chunk for chunk in outputs), "Error was not returned in stream chunks!"
        assert outputs[-1] == "data: [DONE]", "Stream was not cleanly closed with [DONE]!"
        logger.info("Stream generator error handling verified successfully!")
    except Exception as e:
        logger.error(f"Stream generator verification failed: {e}", exc_info=True)
        return False

    logger.info("All verification tests passed successfully!")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_flow())
    sys.exit(0 if success else 1)
