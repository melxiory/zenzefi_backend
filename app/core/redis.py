from typing import Optional
import redis

from app.config import settings

# Redis client singleton
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """
    Get Redis client singleton.
    Creates client on first call, returns same instance on subsequent calls.

    Returns:
        Redis client instance
    """
    global _redis_client

    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True,  # Auto-decode responses to strings
            socket_connect_timeout=5,
            socket_timeout=5,
        )

    return _redis_client


def close_redis_client():
    """Close Redis connection"""
    global _redis_client

    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None
