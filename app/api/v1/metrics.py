"""
Prometheus Metrics endpoint

Exposes application metrics for monitoring with Prometheus.
Tracks key performance indicators:
- Request counters (proxy, auth, token purchases)
- Gauges (active tokens, sessions, users)
- Histograms (latency measurements)
"""
from fastapi import APIRouter, Response
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)
from sqlalchemy import select, func
from loguru import logger

from app.core.database import get_db
from app.core.redis import get_redis_client
from app.models.user import User
from app.models.token import AccessToken
from app.models.proxy_session import ProxySession

router = APIRouter()

# Custom registry for our metrics
registry = CollectorRegistry()

# ===== COUNTERS =====
# Count total requests by type
proxy_requests_total = Counter(
    "proxy_requests_total",
    "Total number of proxy requests",
    ["method", "status_code"],
    registry=registry,
)

auth_attempts_total = Counter(
    "auth_attempts_total",
    "Total number of authentication attempts",
    ["result"],  # success or failure
    registry=registry,
)

token_purchases_total = Counter(
    "token_purchases_total",
    "Total number of token purchases",
    ["duration_hours"],
    registry=registry,
)

token_revocations_total = Counter(
    "token_revocations_total",
    "Total number of token revocations",
    registry=registry,
)

balance_deposits_total = Counter(
    "balance_deposits_total",
    "Total number of balance deposits (ZNC)",
    registry=registry,
)

# ===== GAUGES =====
# Current state metrics
active_tokens_gauge = Gauge(
    "active_tokens",
    "Number of currently active access tokens",
    registry=registry,
)

active_sessions_gauge = Gauge(
    "active_sessions",
    "Number of currently active proxy sessions",
    registry=registry,
)

total_users_gauge = Gauge(
    "total_users",
    "Total number of registered users",
    registry=registry,
)

redis_connected_gauge = Gauge(
    "redis_connected",
    "Redis connection status (1=connected, 0=disconnected)",
    registry=registry,
)

database_connected_gauge = Gauge(
    "database_connected",
    "Database connection status (1=connected, 0=disconnected)",
    registry=registry,
)

# ===== HISTOGRAMS =====
# Latency measurements
proxy_latency_seconds = Histogram(
    "proxy_latency_seconds",
    "Latency of proxy requests in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Duration of database queries in seconds",
    ["query_type"],  # select, insert, update, delete
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=registry,
)

redis_operation_duration_seconds = Histogram(
    "redis_operation_duration_seconds",
    "Duration of Redis operations in seconds",
    ["operation"],  # get, set, zadd, etc.
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1),
    registry=registry,
)


def update_gauge_metrics():
    """
    Update gauge metrics with current database values

    Called on every /metrics request to provide real-time statistics.
    Uses efficient queries with COUNT aggregates.
    """
    try:
        db = next(get_db())

        # Count active tokens (is_active=True, not revoked, not expired)
        active_tokens = db.execute(
            select(func.count(AccessToken.id))
            .where(AccessToken.is_active == True)
            .where(AccessToken.revoked_at == None)
        ).scalar() or 0
        active_tokens_gauge.set(active_tokens)

        # Count active proxy sessions
        active_sessions = db.execute(
            select(func.count(ProxySession.id))
            .where(ProxySession.is_active == True)
        ).scalar() or 0
        active_sessions_gauge.set(active_sessions)

        # Count total users
        total_users = db.execute(
            select(func.count(User.id))
        ).scalar() or 0
        total_users_gauge.set(total_users)

        # Database is connected if we got here
        database_connected_gauge.set(1)

    except Exception as e:
        logger.error(f"Error updating gauge metrics: {e}")
        database_connected_gauge.set(0)

    # Check Redis connection
    try:
        redis = get_redis_client()
        redis.ping()
        redis_connected_gauge.set(1)
    except Exception as e:
        logger.error(f"Redis connection check failed: {e}")
        redis_connected_gauge.set(0)


@router.get("/metrics", include_in_schema=False)
async def metrics():
    """
    Prometheus metrics endpoint

    Returns metrics in Prometheus text format for scraping.
    Updates gauge metrics on every request to provide real-time data.

    Metrics exposed:
    - Counters: proxy_requests, auth_attempts, token_purchases, etc.
    - Gauges: active_tokens, active_sessions, total_users
    - Histograms: proxy_latency, db_query_duration, redis_operation_duration

    Returns:
        Response: Prometheus metrics in text format
    """
    # Update real-time metrics
    update_gauge_metrics()

    # Generate Prometheus text format
    metrics_output = generate_latest(registry)

    return Response(
        content=metrics_output,
        media_type=CONTENT_TYPE_LATEST,
    )
