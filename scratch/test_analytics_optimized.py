import os
import sys
import asyncio
import logging

# Add backend directory to path at the very beginning
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_analytics_optimized")

from api.routes.analytics import get_dashboard, get_usage
from database import connect_db

async def run_tests():
    # Initialize DB
    await connect_db()
    
    current_user = {
        "_id": "6a2a8ce94af4f2be830e5d28",
        "username": "demo@aistudio.com"
    }
    
    logger.info("Calling get_dashboard optimized route directly...")
    dashboard_res = await get_dashboard(current_user=current_user)
    logger.info(f"Dashboard response keys: {list(dashboard_res.keys())}")
    logger.info(f"Dashboard total requests: {dashboard_res.get('total_requests')}")
    logger.info(f"Dashboard total tokens: {dashboard_res.get('total_tokens')}")
    
    assert "total_requests" in dashboard_res
    assert "total_tokens" in dashboard_res
    assert "daily_requests" in dashboard_res
    logger.info("Dashboard optimized route test passed!")
    
    logger.info("Calling get_usage optimized route directly...")
    usage_res = await get_usage(days=7, current_user=current_user)
    logger.info(f"Usage response keys: {list(usage_res.keys())}")
    logger.info(f"Usage data points count: {len(usage_res.get('data', []))}")
    
    assert "period" in usage_res
    assert "data" in usage_res
    logger.info("Usage optimized route test passed!")

if __name__ == "__main__":
    asyncio.run(run_tests())
