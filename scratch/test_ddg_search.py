import os
import sys
import asyncio
import logging

# Add backend directory to path at the very beginning
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_ddg_search")

from api.routes.ai import get_google_data

def test_search():
    try:
        logger.info("Calling get_google_data with query 'car'...")
        result = asyncio.run(get_google_data(query="car"))
        logger.info(f"Search result: {result}")
        assert "title" in result
        assert "source" in result
        logger.info("Search test passed successfully!")
    except Exception as e:
        logger.error(f"Search test failed: {e}", exc_info=True)

if __name__ == "__main__":
    test_search()
