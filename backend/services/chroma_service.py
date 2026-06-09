import asyncio
import logging
import chromadb
from config import settings

logger = logging.getLogger(__name__)

class ChromaManager:
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            logger.info(f"Initializing singleton ChromaDB PersistentClient at path: {settings.CHROMA_PERSIST_DIR} (Telemetry: Disabled)")
            from chromadb.config import Settings
            cls._client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=Settings(anonymized_telemetry=False)
            )
        return cls._client

async def run_with_retry_async(func, *args, **kwargs):
    """
    Run ChromaDB database operation with retry logic for SQLite locked database errors.
    Uses asyncio.to_thread to keep the event loop unblocked.
    """
    max_attempts = 5
    delay = 2.0
    for attempt in range(max_attempts):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as e:
            err_msg = str(e).lower()
            if "database is locked" in err_msg or "db is locked" in err_msg or "code: 5" in err_msg or "locked" in err_msg:
                if attempt < max_attempts - 1:
                    logger.warning(
                        f"ChromaDB locked error (attempt {attempt + 1}/{max_attempts}). "
                        f"Retrying in {delay} seconds... Error: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"ChromaDB locked error. Max attempts ({max_attempts}) reached. Error: {e}")
                    raise
            else:
                raise

async def collection_is_empty(collection_name: str) -> bool:
    """Check if a ChromaDB collection is empty or does not exist."""
    try:
        client = await asyncio.to_thread(ChromaManager.get_client)
        if client is None:
            return True
            
        def _check():
            try:
                col = client.get_collection(name=collection_name)
                return col.count() == 0
            except Exception as e:
                err_msg = str(e).lower()
                if "does not exist" in err_msg or "not found" in err_msg:
                    return True
                raise
                
        return await run_with_retry_async(_check)
    except Exception as e:
        logger.error(f"Error checking if collection {collection_name} is empty: {e}")
        return True
