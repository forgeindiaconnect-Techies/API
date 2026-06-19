import json
import logging
import time
from typing import Any, Optional
from datetime import datetime

from redis_client import get_redis

logger = logging.getLogger(__name__)

# In-memory fallback cache structure: {key: (value, expiry_timestamp)}
_in_memory_cache = {}

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Redis Circuit Breaker State
_redis_healthy = True
_redis_disabled_until = 0

def is_redis_available() -> bool:
    global _redis_healthy, _redis_disabled_until
    if not _redis_healthy and time.time() < _redis_disabled_until:
        return False
    return True

def report_redis_failure(operation: str, key: str, err: Exception):
    global _redis_healthy, _redis_disabled_until
    if _redis_healthy:
        _redis_healthy = False
        logger.warning(
            f"Redis connection failed during {operation} (key: {key}). "
            f"Temporarily disabling Redis cache for 60 seconds to prevent log spam and latency. Error: {err}"
        )
    else:
        logger.debug(f"Redis connection still down during {operation} (key: {key}). Error: {err}")
    _redis_disabled_until = time.time() + 60

def report_redis_success():
    global _redis_healthy
    if not _redis_healthy:
        _redis_healthy = True
        logger.info("Redis connection recovered. Re-enabling Redis cache.")

async def cache_get(key: str) -> Optional[Any]:
    # Try Redis first if available
    if is_redis_available():
        redis = get_redis()
        if redis:
            try:
                val = await redis.get(key)
                report_redis_success()
                if val is not None:
                    return json.loads(val)
            except Exception as e:
                report_redis_failure("cache_get", key, e)
    
    # Fallback to in-memory
    if key in _in_memory_cache:
        val, expiry = _in_memory_cache[key]
        if expiry is None or expiry > time.time():
            return val
        else:
            # Clean up expired entry
            try:
                del _in_memory_cache[key]
            except KeyError:
                pass
    return None

async def cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    # Set to Redis if available
    redis_ok = False
    if is_redis_available():
        redis = get_redis()
        if redis:
            try:
                serialized = json.dumps(value, cls=DateTimeEncoder)
                await redis.setex(key, ttl, serialized)
                report_redis_success()
                redis_ok = True
            except Exception as e:
                report_redis_failure("cache_set", key, e)
            
    # Always update in-memory cache as fallback/mirrored copy
    expiry = time.time() + ttl
    _in_memory_cache[key] = (value, expiry)
    return redis_ok

async def cache_delete(key: str):
    # Delete from Redis if available
    if is_redis_available():
        redis = get_redis()
        if redis:
            try:
                await redis.delete(key)
                report_redis_success()
            except Exception as e:
                report_redis_failure("cache_delete", key, e)
            
    # Delete from in-memory
    if key in _in_memory_cache:
        try:
            del _in_memory_cache[key]
        except KeyError:
            pass

async def cache_clear_user(user_id: str):
    """Clear all cached keys for a specific user."""
    if is_redis_available():
        redis = get_redis()
        if redis:
            try:
                # Clear standard keys matching patterns
                patterns = [f"*:user:{user_id}*", f"*:{user_id}:*"]
                for pat in patterns:
                    async for key in redis.scan_iter(match=pat):
                        await redis.delete(key)
                report_redis_success()
            except Exception as e:
                report_redis_failure("cache_clear_user", f"user:{user_id}", e)
            
    # Clear from in-memory
    global _in_memory_cache
    keys_to_del = []
    for k in _in_memory_cache.keys():
        if f"user:{user_id}" in k or f"_{user_id}_" in k or f":{user_id}" in k:
            keys_to_del.append(k)
    for k in keys_to_del:
        try:
            del _in_memory_cache[k]
        except KeyError:
            pass
