import chromadb
import inspect

try:
    from chromadb.api.types import EmbeddingFunction
    print("EmbeddingFunction imported from chromadb.api.types")
    print(inspect.getsource(EmbeddingFunction))
except Exception as e:
    print("Failed to inspect EmbeddingFunction:", e)
