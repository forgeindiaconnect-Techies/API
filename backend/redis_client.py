import redis.asyncio as aioredis
from config import settings
import logging

logger = logging.getLogger(__name__)

redis_client = None

def get_redis():
    global redis_client
    if redis_client is None:
        try:
            kwargs = {}
            if settings.REDIS_URL.startswith("rediss://"):
                import ssl
                kwargs["ssl_cert_reqs"] = ssl.CERT_NONE
            redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True, **kwargs)
            logger.info("Redis client initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
    return redis_client

async def close_redis():
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
            logger.info("Redis client closed.")
        except Exception as e:
            logger.error(f"Failed to close Redis client: {e}")
        redis_client = None
