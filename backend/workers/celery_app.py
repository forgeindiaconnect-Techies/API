from celery import Celery
from config import settings
import ssl

# Render Redis service uses TLS and requires rediss://. Bypassing certificate checks
# for internal self-signed certs via ssl_cert_reqs=ssl.CERT_NONE.
ssl_conf = None
if settings.CELERY_BROKER_URL.startswith("rediss://") or settings.CELERY_RESULT_BACKEND.startswith("rediss://"):
    ssl_conf = {
        "ssl_cert_reqs": ssl.CERT_NONE
    }

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
    broker_use_ssl=ssl_conf,
    redis_backend_use_ssl=ssl_conf,
    broker_pool_limit=10,
    broker_connection_retry_on_startup=True,
    redis_socket_keepalive=True,
    redis_retry_on_timeout=True,
    redis_socket_timeout=30.0,
    redis_socket_connect_timeout=30.0,
    task_routes={
        "workers.tasks.process_dataset_task": {"queue": "datasets"},
        "workers.tasks.rebuild_dataset_index_task": {"queue": "datasets"},
        "workers.tasks.train_model_task": {"queue": "training"},
        "workers.tasks.build_rag_index_task": {"queue": "rag"},
    },
)
