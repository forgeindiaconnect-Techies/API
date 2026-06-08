import numpy as np
import hashlib
import re

def encode(texts, dimension=384):
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
                
        vec = np.zeros(dimension, dtype="float32")
        for w, freq in tf.items():
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
            idx = h % dimension
            sign = 1 if ((h >> 8) & 1) else -1
            vec[idx] += sign * freq
            
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        embeddings.append(vec)
        
    if is_single:
        return embeddings[0]
    return np.array(embeddings, dtype="float32")

q = encode("hi, how are you")
d1 = encode("Ahi, how are you doing? i'm fine. how about yourself?")
d2 = encode("which school do you attend? i'm attending pcc right now.")

sim1 = np.dot(q, d1)
sim2 = np.dot(q, d2)
print("d1 similarity:", sim1)
print("d2 similarity:", sim2)
