import sys
import os
import asyncio

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from database import connect_db, get_db, DatabaseWrapper, MockDB
from workers.celery_app import celery_app
from services.startup_rebuild import dispatch_rebuild_task
import database

async def test_devops_config():
    print("=== Testing Celery Conf ===")
    print("Celery Broker URL:", celery_app.conf.broker_url)
    print("Celery Result Backend:", celery_app.conf.result_backend)
    print("Celery Keepalive:", celery_app.conf.redis_socket_keepalive)
    print("Celery Retry on Timeout:", celery_app.conf.redis_retry_on_timeout)
    print("Celery Socket Timeout:", celery_app.conf.redis_socket_timeout)
    print("Celery Pool Limit:", celery_app.conf.broker_pool_limit)
    
    # Verify we can configure task queues
    print("Celery Task Routes Defined:", len(celery_app.conf.task_routes) if celery_app.conf.task_routes else 0)

    # 2. Test startup rebuild dispatching
    print("\n=== Testing Rebuild Dispatching ===")
    mock_db = DatabaseWrapper(MockDB())
    database.db = mock_db
    
    # We stub run_rebuild_locally to verify it's called
    rebuild_called = []
    async def mock_run_rebuild_locally(dataset_id: str):
        print(f"Mock run_rebuild_locally called for dataset: {dataset_id}")
        rebuild_called.append(dataset_id)
        
    import services.startup_rebuild
    services.startup_rebuild.run_rebuild_locally = mock_run_rebuild_locally
    
    print("Dispatching rebuild task...")
    dispatch_rebuild_task("test_dataset_id_123")
    
    # Let event loop process tasks
    await asyncio.sleep(0.5)
    print("Rebuild executed locally:", "test_dataset_id_123" in rebuild_called)

if __name__ == '__main__':
    asyncio.run(test_devops_config())
