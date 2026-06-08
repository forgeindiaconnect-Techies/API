import numpy as np
import hashlib
import re
import os

class HashingTFIDFEmbedder:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def encode(self, texts, **kwargs):
        is_single = isinstance(texts, str)
        if is_single:
            texts = [texts]

        stop_words = {"the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "to", "of", "in", "for", "on", "with", "at", "by"}

        embeddings = []
        for text in texts:
            words = re.findall(r'\w+', text.lower())
            tf = {}
            for w in words:
                if w not in stop_words:
                    tf[w] = tf.get(w, 0) + 1

            vec = np.zeros(self.dimension, dtype="float32")
            for w, freq in tf.items():
                h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
                idx = h % self.dimension
                sign = 1 if ((h >> 8) & 1) else -1
                vec[idx] += sign * freq

            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            embeddings.append(vec)

        if is_single:
            return embeddings[0]
        return np.array(embeddings, dtype="float32")

def run():
    filepath = 'backend/uploads/6a213b5f4f5a5a8a0249f24b/00bc861c-8033-49bc-8547-69dc09048691.txt'
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    
    chunk_size = 512
    chunk_overlap = 50
    step = chunk_size - chunk_overlap
    chunks = []
    for i in range(0, len(text), step):
        chunks.append(text[i:i+chunk_size])
        
    print(f"Total chunks: {len(chunks)}")
    
    embedder = HashingTFIDFEmbedder(384)
    chunk_embeddings = embedder.encode(chunks)
    
    query = "have you seen the new girl in school?"
    query_emb = embedder.encode(query)
    
    scores = np.dot(chunk_embeddings, query_emb)
    
    top_indices = np.argsort(scores)[::-1][:5]
    print("\nTop 5 matches for query:", query)
    for idx in top_indices:
        print(f"\n[Index {idx}] Score: {scores[idx]:.4f}")
        print("Content:")
        print(chunks[idx])
        print("-" * 40)

if __name__ == '__main__':
    run()
