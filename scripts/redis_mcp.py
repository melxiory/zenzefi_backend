#!/usr/bin/env python3
"""Redis MCP Server for Claude Code

Provides tools to interact with Redis cache for token validation and monitoring.
"""

from fastmcp import FastMCP
import redis
import json
from typing import Dict, List, Optional

mcp = FastMCP("Redis Tools")

# Redis connection settings from environment or defaults
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0


def get_redis_client() -> redis.Redis:
    """Get Redis client instance."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )


@mcp.tool()
def get_redis_key(key: str) -> Dict:
    """Get value from Redis by key.

    Args:
        key: Redis key to retrieve

    Returns:
        Dictionary with key, value, TTL, and type information
    """
    r = get_redis_client()

    if not r.exists(key):
        return {
            "key": key,
            "exists": False,
            "value": None,
            "ttl": None,
            "type": None
        }

    value = r.get(key)
    ttl = r.ttl(key)
    key_type = r.type(key)

    return {
        "key": key,
        "exists": True,
        "value": value,
        "ttl": ttl if ttl >= 0 else "no expiration",
        "type": key_type
    }


@mcp.tool()
def scan_redis_keys(pattern: str = "*", count: int = 100) -> Dict:
    """Scan Redis keys matching a pattern.

    Args:
        pattern: Pattern to match (default: "*" for all keys)
        count: Maximum number of keys to return (default: 100)

    Returns:
        Dictionary with matched keys and their count
    """
    r = get_redis_client()
    cursor = 0
    keys = []

    while len(keys) < count:
        cursor, batch = r.scan(cursor, match=pattern, count=min(count, 100))
        keys.extend(batch)
        if cursor == 0 or len(keys) >= count:
            break

    return {
        "pattern": pattern,
        "count": len(keys),
        "keys": keys[:count]
    }


@mcp.tool()
def get_active_tokens_count() -> Dict:
    """Get count of active tokens cached in Redis.

    Returns:
        Dictionary with count of cached active tokens
    """
    r = get_redis_client()
    cursor = 0
    count = 0

    while True:
        cursor, keys = r.scan(cursor, match="active_token:*", count=1000)
        count += len(keys)
        if cursor == 0:
            break

    return {
        "active_tokens_count": count,
        "pattern": "active_token:*"
    }


@mcp.tool()
def get_token_info(token_hash: str) -> Dict:
    """Get information about a cached token.

    Args:
        token_hash: SHA256 hash of the token (without 'active_token:' prefix)

    Returns:
        Dictionary with token information from Redis cache
    """
    r = get_redis_client()
    key = f"active_token:{token_hash}"

    if not r.exists(key):
        return {
            "key": key,
            "exists": False,
            "cached": False
        }

    value = r.get(key)
    ttl = r.ttl(key)

    try:
        token_data = json.loads(value)
    except json.JSONDecodeError:
        token_data = value

    return {
        "key": key,
        "exists": True,
        "cached": True,
        "data": token_data,
        "ttl_seconds": ttl if ttl >= 0 else "no expiration"
    }


@mcp.tool()
def flush_redis_pattern(pattern: str) -> Dict:
    """Delete all keys matching a pattern.

    WARNING: This is a destructive operation!

    Args:
        pattern: Pattern to match (e.g., "active_token:*")

    Returns:
        Dictionary with number of deleted keys
    """
    r = get_redis_client()
    cursor = 0
    deleted = 0

    while True:
        cursor, keys = r.scan(cursor, match=pattern, count=1000)
        if keys:
            deleted += r.delete(*keys)
        if cursor == 0:
            break

    return {
        "pattern": pattern,
        "deleted": deleted
    }


@mcp.tool()
def redis_info(section: str = "all") -> Dict:
    """Get Redis server information.

    Args:
        section: Info section to retrieve (default: "all")
                 Options: server, clients, memory, persistence, stats, replication, cpu, keyspace

    Returns:
        Dictionary with Redis server information
    """
    r = get_redis_client()
    info = r.info(section)

    return {
        "section": section,
        "info": info
    }


@mcp.tool()
def redis_dbsize() -> Dict:
    """Get total number of keys in the current database.

    Returns:
        Dictionary with database size information
    """
    r = get_redis_client()
    size = r.dbsize()

    return {
        "db": REDIS_DB,
        "keys_count": size
    }


if __name__ == "__main__":
    mcp.run()
