import asyncio
import logging
import os

# Disable ChromaDB telemetry globally
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from config import settings

logger = logging.getLogger(__name__)


def safe_print(msg: str):
    import sys
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding='utf-8')
                print(msg, flush=True)
            else:
                raise
        except Exception:
            ascii_msg = msg.replace("🧠", "[CHROMA]").replace("📁", "Dir:").replace("📦", "Collections:").replace("💾", "Disk:").replace("⏱", "Time:").replace("✅", "[OK]").replace("❌", "[FAIL]")
            try:
                print(ascii_msg, flush=True)
            except Exception:
                pass


class ChromaManager:
    _client = None

    @classmethod
    def get_client(cls):
        import chromadb
        if cls._client is None or getattr(cls._client, "_closed", False):
            logger.info(f"Initializing singleton ChromaDB PersistentClient at path: {settings.CHROMA_PERSIST_DIR} (Telemetry: Disabled)")
            from chromadb.config import Settings
            cls._client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=Settings(anonymized_telemetry=False)
            )
        return cls._client

    @classmethod
    def close_client(cls):
        if cls._client is not None:
            try:
                cls._client.close()
                logger.info("ChromaDB PersistentClient closed successfully.")
            except Exception as e:
                logger.error(f"Error closing ChromaDB client: {e}")
            finally:
                cls._client = None

    @classmethod
    def validate_startup(cls) -> dict:
        import time
        import os
        import shutil
        import sqlite3
        import chromadb
        from chromadb.config import Settings
        
        diagnostics = {
            "path": settings.CHROMA_PERSIST_DIR,
            "collections_count": 0,
            "disk_space": "Unknown",
            "startup_time_ms": 0.0,
            "status": "failed",
            "error_message": "",
            "chroma_version": chromadb.__version__,
            "sqlite_version": sqlite3.sqlite_version
        }
        
        start_time = time.perf_counter()
        
        # 1. Verify directory exists & test write permissions
        try:
            os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
            test_file_path = os.path.join(settings.CHROMA_PERSIST_DIR, ".write_test")
            with open(test_file_path, "w", encoding="utf-8") as f:
                f.write("test")
            if os.path.exists(test_file_path):
                os.remove(test_file_path)
        except Exception as e:
            diagnostics["error_message"] = f"Directory permissions failure: {str(e)}"
            diagnostics["startup_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
            cls._print_diagnostics_report(diagnostics)
            return diagnostics

        # 2. Disk space check
        try:
            total, used, free = shutil.disk_usage(settings.CHROMA_PERSIST_DIR)
            free_gb = round(free / (1024**3), 2)
            diagnostics["disk_space"] = f"{free_gb} GB"
        except Exception as e:
            logger.warning(f"Could not retrieve disk space: {e}")

        # 3. Client Initialization & CRUD validation
        try:
            if cls._client is None or getattr(cls._client, "_closed", False):
                cls._client = chromadb.PersistentClient(
                    path=settings.CHROMA_PERSIST_DIR,
                    settings=Settings(anonymized_telemetry=False)
                )
            
            # List collections
            collections = cls._client.list_collections()
            diagnostics["collections_count"] = len(collections)
            
            # Connection validation (test create/insert/query/delete)
            test_col_name = "startup_validation_check_test_col"
            try:
                try:
                    cls._client.delete_collection(test_col_name)
                except Exception:
                    pass
                test_col = cls._client.create_collection(
                    name=test_col_name,
                    embedding_function=DummyEmbeddingFunction()
                )
                test_col.add(
                    documents=["startup diagnostics test"],
                    ids=["diagnostics_id"],
                    embeddings=[[0.0] * 384]
                )
                query_res = test_col.query(
                    query_embeddings=[[0.0] * 384],
                    n_results=1
                )
                if not query_res or len(query_res.get("ids", [])) == 0:
                    raise Exception("Query validation returned empty results")
                cls._client.delete_collection(test_col_name)
            except Exception as val_err:
                raise Exception(f"Validation collection test failed: {str(val_err)}")

            diagnostics["status"] = "success"
        except Exception as e:
            diagnostics["error_message"] = str(e)

        diagnostics["startup_time_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        cls._print_diagnostics_report(diagnostics)
        return diagnostics

    @classmethod
    def _print_diagnostics_report(cls, diagnostics: dict):
        report = [
            "==================================================",
            "🧠 ChromaDB Startup Check",
            "=========================",
            "",
            f"📁 Path: {diagnostics['path']}",
            f"🏷 ChromaDB Version: {diagnostics['chroma_version']}",
            f"🛢 SQLite Version: {diagnostics['sqlite_version']}",
            f"📦 Collections Found: {diagnostics['collections_count']}",
            f"💾 Disk Space Available: {diagnostics['disk_space']}",
            f"⏱ Startup Time: {diagnostics['startup_time_ms']} ms",
            ""
        ]
        if diagnostics["status"] == "success":
            report.append("✅ ChromaDB Connected Successfully")
        else:
            report.append("❌ ChromaDB Connection Failed")
            report.append(f"Error: {diagnostics['error_message']}")
        report.append("=======================")
        
        safe_print("\n".join(report))


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

class DummyEmbeddingFunction:
    """A dummy embedding function to prevent ChromaDB from initializing its heavy default ONNX model."""
    def __call__(self, input):
        return [[0.0] * 384 for _ in input]

    @staticmethod
    def name() -> str:
        return "dummy"



async def collection_is_empty(collection_name: str) -> bool:
    """Check if a ChromaDB collection is empty or does not exist."""
    try:
        client = await asyncio.to_thread(ChromaManager.get_client)
        if client is None:
            return True
            
        def _check():
            try:
                col = client.get_collection(name=collection_name, embedding_function=DummyEmbeddingFunction())
                count = col.count()
                logger.info(f"ChromaDB Collection '{collection_name}' count: {count} documents.")
                return count == 0
            except Exception as e:
                err_msg = str(e).lower()
                if "does not exist" in err_msg or "not found" in err_msg:
                    logger.info(f"ChromaDB Collection '{collection_name}' does not exist.")
                    return True
                # If any other exception occurs, it might be corrupted or locked
                logger.error(f"ChromaDB Collection '{collection_name}' check failed (possibly corrupted): {e}")
                # Recreate recovery: delete collection so it gets recreated fresh
                try:
                    logger.warning(f"Attempting to delete possibly corrupted collection '{collection_name}' for automatic recovery...")
                    client.delete_collection(name=collection_name)
                    logger.info(f"Deleted collection '{collection_name}' successfully.")
                except Exception as del_err:
                    logger.error(f"Failed to delete corrupted collection '{collection_name}': {del_err}")
                return True
                
        return await run_with_retry_async(_check)
    except Exception as e:
        logger.error(f"Error checking if collection {collection_name} is empty: {e}")
        return True
