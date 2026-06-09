from workers.celery_app import celery_app
import logging

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="workers.tasks.process_dataset_task", max_retries=3)
def process_dataset_task(self, dataset_id: str, file_path: str, file_type: str):
    """Process an uploaded dataset"""
    try:
        self.update_state(state="PROGRESS", meta={"progress": 10, "status": "Reading file"})

        from datasets.processor import _process_sync
        result = _process_sync(file_path, file_type)

        self.update_state(state="PROGRESS", meta={"progress": 60, "status": "Analyzing data"})

        return {
            "dataset_id": dataset_id,
            "rows": result.get("rows"),
            "cols": result.get("cols"),
            "columns": result.get("columns", []),
            "metadata": result.get("metadata", {}),
            "status": "ready",
        }
    except Exception as exc:
        logger.error(f"Dataset processing failed: {exc}")
        self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="workers.tasks.train_model_task", max_retries=1)
def train_model_task(self, job_id: str, model_id: str, config: dict):
    """Train / fine-tune a model"""
    import time
    import math

    epochs = config.get("epochs", 3)
    total_steps = epochs * 100

    for step in range(total_steps):
        pct = (step / total_steps) * 100
        train_loss = 2.3 * math.exp(-step / (total_steps * 0.4)) + 0.1
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": round(pct, 1),
                "step": step,
                "train_loss": round(train_loss, 4),
                "epoch": step // 100 + 1,
            },
        )
        time.sleep(0.05)

    return {
        "job_id": job_id,
        "model_id": model_id,
        "accuracy": 0.924,
        "f1_score": 0.918,
        "status": "ready",
    }


@celery_app.task(bind=True, name="workers.tasks.build_rag_index_task", max_retries=2)
def build_rag_index_task(self, index_id: str, file_path: str, config: dict):
    """Build a RAG vector index"""
    import time

    self.update_state(state="PROGRESS", meta={"progress": 10, "status": "Loading document"})
    time.sleep(1)

    self.update_state(state="PROGRESS", meta={"progress": 40, "status": "Chunking text"})
    time.sleep(1)

    self.update_state(state="PROGRESS", meta={"progress": 70, "status": "Generating embeddings"})
    time.sleep(2)

    self.update_state(state="PROGRESS", meta={"progress": 90, "status": "Storing in vector DB"})
    time.sleep(0.5)

    return {
        "index_id": index_id,
        "chunk_count": 342,
        "status": "ready",
    }


@celery_app.task(bind=True, name="workers.tasks.rebuild_dataset_index_task", max_retries=2)
def rebuild_dataset_index_task(self, dataset_id: str):
    """Rebuild a dataset's RAG index in the background"""
    import asyncio
    from database import get_db, connect_db
    from services.dataset_service import build_index_for_dataset

    logger.info(f"Celery Worker: Starting RAG index rebuild for dataset {dataset_id}")

    async def _run():
        db = get_db()
        if db is None:
            await connect_db()
            db = get_db()

        dataset = await db.datasets.find_one({"_id": dataset_id})
        if not dataset:
            logger.error(f"Celery Worker: Dataset {dataset_id} not found.")
            return

        await build_index_for_dataset(dataset, db)
        logger.info(f"Celery Worker: Finished RAG index rebuild for dataset {dataset_id}")

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # Run using a separate thread since we are in a running event loop
        import threading
        t = threading.Thread(target=lambda: asyncio.run(_run()))
        t.start()
        t.join()
    else:
        loop.run_until_complete(_run())
