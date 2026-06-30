import sys
import os
import asyncio
import numpy as np

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from config import settings
from vector_db.store import get_embedding_model, GeminiEmbedder

def test_gemini_embedder():
    print("=== Testing Gemini Embeddings Integration ===")
    
    # 1. Initialize embedding model
    print("Initializing GeminiEmbedder directly...")
    embedder = GeminiEmbedder(api_key=settings.GEMINI_API_KEY)
    
    print(f"Loaded embedder class: {embedder.__class__.__name__}")
    assert isinstance(embedder, GeminiEmbedder), f"Expected GeminiEmbedder, got {type(embedder)}"
    
    # 2. Test single text encoding
    text = "Artificial intelligence and embeddings represent semantic meanings in higher dimensional space."
    print(f"Encoding single text: '{text[:50]}...'")
    vector = embedder.encode(text)
    
    print(f"Single vector type: {type(vector)}")
    print(f"Single vector shape: {vector.shape}")
    assert isinstance(vector, np.ndarray), "Expected numpy array output"
    assert vector.shape == (3072,), f"Expected shape (3072,), got {vector.shape}"
    
    # 3. Test batch encoding
    batch = [
        "First test sentence to embed.",
        "Second test sentence to embed."
    ]
    print(f"Encoding batch of size {len(batch)}...")
    vectors = embedder.encode(batch)
    
    print(f"Batch vectors type: {type(vectors)}")
    print(f"Batch vectors shape: {vectors.shape}")
    assert isinstance(vectors, np.ndarray), "Expected numpy array output"
    assert vectors.shape == (2, 3072), f"Expected shape (2, 3072), got {vectors.shape}"
    
    print("=== All Gemini Embeddings Integration Tests Passed Successfully! ===")
    return True

if __name__ == "__main__":
    import sys
    success = test_gemini_embedder()
    sys.exit(0 if success else 1)
