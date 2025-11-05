"""
Health Check Service

Service for performing health checks on all system components.
"""

import asyncio
import json
from datetime import datetime
from time import time
from typing import Optional

import httpx
from loguru import logger
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import SessionLocal
from app.core.redis import get_redis_client
from app.schemas.health import (
    HealthChecks,
    HealthOverall,
    HealthResponse,
    OverallStatus,
    ServiceCheck,
    ServiceStatus,
)


class HealthCheckService:
    """Service for performing health checks"""

    REDIS_HEALTH_KEY = "health:status"
    REDIS_HEALTH_TTL = 120  # 2 minutes TTL for health data

    @staticmethod
    async def check_database() -> ServiceCheck:
        """
        Check PostgreSQL database connectivity and performance

        Returns:
            ServiceCheck with database status
        """
        start_time = time()
        db: Optional[Session] = None

        try:
            db = SessionLocal()
            # Simple query to check connectivity
            db.execute(text("SELECT 1"))
            db.commit()

            latency_ms = (time() - start_time) * 1000

            logger.debug(f"Database check: OK (latency: {latency_ms:.2f}ms)")

            return ServiceCheck(
                status=ServiceStatus.UP,
                latency_ms=round(latency_ms, 2),
                error=None,
                url=None,
            )

        except Exception as e:
            latency_ms = (time() - start_time) * 1000
            error_msg = f"Database connection failed: {str(e)}"
            logger.error(error_msg)

            return ServiceCheck(
                status=ServiceStatus.DOWN,
                latency_ms=round(latency_ms, 2),
                error=error_msg,
                url=None,
            )

        finally:
            if db:
                db.close()

    @staticmethod
    async def check_redis() -> ServiceCheck:
        """
        Check Redis connectivity and performance

        Returns:
            ServiceCheck with Redis status
        """
        start_time = time()
        redis_client: Optional[Redis] = None

        try:
            redis_client = get_redis_client()
            # Ping Redis
            redis_client.ping()

            latency_ms = (time() - start_time) * 1000

            logger.debug(f"Redis check: OK (latency: {latency_ms:.2f}ms)")

            return ServiceCheck(
                status=ServiceStatus.UP,
                latency_ms=round(latency_ms, 2),
                error=None,
                url=None,
            )

        except Exception as e:
            latency_ms = (time() - start_time) * 1000
            error_msg = f"Redis connection failed: {str(e)}"
            logger.error(error_msg)

            return ServiceCheck(
                status=ServiceStatus.DOWN,
                latency_ms=round(latency_ms, 2),
                error=error_msg,
                url=None,
            )

    @staticmethod
    async def check_zenzefi() -> ServiceCheck:
        """
        Check Zenzefi server connectivity

        Returns:
            ServiceCheck with Zenzefi status
        """
        start_time = time()
        zenzefi_url = settings.ZENZEFI_TARGET_URL

        try:
            # HEAD request to check server availability
            async with httpx.AsyncClient(
                timeout=settings.HEALTH_CHECK_TIMEOUT, verify=False
            ) as client:
                response = await client.head(zenzefi_url)

            latency_ms = (time() - start_time) * 1000

            # Consider 2xx and 3xx as successful
            if response.status_code < 400:
                logger.debug(
                    f"Zenzefi check: OK (latency: {latency_ms:.2f}ms, status: {response.status_code})"
                )

                return ServiceCheck(
                    status=ServiceStatus.UP,
                    latency_ms=round(latency_ms, 2),
                    error=None,
                    url=zenzefi_url,
                )
            else:
                error_msg = f"Zenzefi returned status {response.status_code}"
                logger.warning(error_msg)

                return ServiceCheck(
                    status=ServiceStatus.DOWN,
                    latency_ms=round(latency_ms, 2),
                    error=error_msg,
                    url=zenzefi_url,
                )

        except Exception as e:
            latency_ms = (time() - start_time) * 1000
            error_msg = f"Zenzefi connection failed: {str(e)}"
            logger.error(error_msg)

            return ServiceCheck(
                status=ServiceStatus.DOWN,
                latency_ms=round(latency_ms, 2),
                error=error_msg,
                url=zenzefi_url,
            )

    @staticmethod
    def determine_overall_status(checks: HealthChecks) -> OverallStatus:
        """
        Determine overall system status based on individual checks

        Logic:
        - HEALTHY: All services are up
        - DEGRADED: Zenzefi is down, but DB + Redis are up (non-critical)
        - UNHEALTHY: DB or Redis is down (critical services)

        Args:
            checks: Individual service checks

        Returns:
            Overall system status
        """
        db_up = checks.database.status == ServiceStatus.UP
        redis_up = checks.redis.status == ServiceStatus.UP
        zenzefi_up = checks.zenzefi.status == ServiceStatus.UP

        # Critical services down = UNHEALTHY
        if not db_up or not redis_up:
            return OverallStatus.UNHEALTHY

        # All services up = HEALTHY
        if db_up and redis_up and zenzefi_up:
            return OverallStatus.HEALTHY

        # Non-critical service down = DEGRADED
        return OverallStatus.DEGRADED

    @classmethod
    async def perform_health_check(cls) -> HealthResponse:
        """
        Perform all health checks and aggregate results

        Returns:
            HealthResponse with all check results
        """
        logger.info("Performing health checks...")

        # Run all checks concurrently
        db_check, redis_check, zenzefi_check = await asyncio.gather(
            cls.check_database(), cls.check_redis(), cls.check_zenzefi()
        )

        # Aggregate checks
        checks = HealthChecks(
            database=db_check, redis=redis_check, zenzefi=zenzefi_check
        )

        # Calculate statistics
        healthy_count = sum(
            1
            for check in [db_check, redis_check, zenzefi_check]
            if check.status == ServiceStatus.UP
        )

        overall = HealthOverall(healthy_count=healthy_count, total_count=3)

        # Determine overall status
        status = cls.determine_overall_status(checks)

        # Create response
        response = HealthResponse(
            status=status, timestamp=datetime.utcnow(), checks=checks, overall=overall
        )

        logger.info(
            f"Health check complete: {status.value} ({healthy_count}/3 services up)"
        )

        return response

    @classmethod
    async def save_health_to_redis(cls, health: HealthResponse) -> None:
        """
        Save health check results to Redis

        Args:
            health: Health check response to save
        """
        try:
            redis_client = get_redis_client()

            # Serialize to JSON
            health_json = health.model_dump_json()

            # Save to Redis with TTL
            redis_client.setex(cls.REDIS_HEALTH_KEY, cls.REDIS_HEALTH_TTL, health_json)

            logger.debug(f"Health status saved to Redis: {health.status.value}")

        except Exception as e:
            logger.error(f"Failed to save health status to Redis: {e}")

    @classmethod
    def get_health_from_redis(cls) -> Optional[HealthResponse]:
        """
        Retrieve cached health check results from Redis

        Returns:
            HealthResponse if cached, None if not found or error
        """
        try:
            redis_client = get_redis_client()

            # Get from Redis
            health_json = redis_client.get(cls.REDIS_HEALTH_KEY)

            if not health_json:
                logger.debug("No cached health status in Redis")
                return None

            # Deserialize from JSON
            health_dict = json.loads(health_json)
            health = HealthResponse(**health_dict)

            logger.debug(f"Retrieved health status from Redis: {health.status.value}")

            return health

        except Exception as e:
            logger.error(f"Failed to retrieve health status from Redis: {e}")
            return None

    @classmethod
    async def perform_and_cache_health_check(cls) -> HealthResponse:
        """
        Perform health check and cache results in Redis

        Returns:
            HealthResponse with all check results
        """
        # Perform checks
        health = await cls.perform_health_check()

        # Cache in Redis
        await cls.save_health_to_redis(health)

        return health
