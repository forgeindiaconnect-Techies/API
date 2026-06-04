from celery import Celery
from config import settings

celery_app = Celery(
    "aistudio",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "workers.tasks.process_dataset_task": {"queue": "datasets"},
        "workers.tasks.train_model_task": {"queue": "training"},
        "workers.tasks.build_rag_index_task": {"queue": "rag"},
    },
)
