"""
Tests for Health Check Service

Tests for health check functionality including database, Redis, and Zenzefi checks.
"""

import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy.orm import Session

from app.services.health_service import HealthCheckService
from app.schemas.health import (
    ServiceStatus,
    OverallStatus,
    HealthChecks,
    ServiceCheck,
)


class TestHealthCheckDatabase:
    """Tests for database health check"""

    @pytest.mark.asyncio
    async def test_check_database_success(self, test_db: Session):
        """Test successful database health check"""
        result = await HealthCheckService.check_database()

        assert result.status == ServiceStatus.UP
        assert result.latency_ms is not None
        assert result.latency_ms > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_check_database_failure(self):
        """Test database health check failure"""
        # Mock SessionLocal to raise exception
        with patch("app.services.health_service.SessionLocal") as mock_session:
            mock_session.return_value.execute.side_effect = Exception(
                "Connection refused"
            )

            result = await HealthCheckService.check_database()

            assert result.status == ServiceStatus.DOWN
            assert result.latency_ms is not None
            assert result.error is not None
            assert "Connection refused" in result.error


class TestHealthCheckRedis:
    """Tests for Redis health check"""

    @pytest.mark.asyncio
    async def test_check_redis_success(self, fake_redis):
        """Test successful Redis health check"""
        result = await HealthCheckService.check_redis()

        assert result.status == ServiceStatus.UP
        assert result.latency_ms is not None
        assert result.latency_ms > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_check_redis_failure(self):
        """Test Redis health check failure"""
        # Mock get_redis_client to raise exception
        with patch("app.services.health_service.get_redis_client") as mock_redis:
            mock_redis.return_value.ping.side_effect = Exception("Connection refused")

            result = await HealthCheckService.check_redis()

            assert result.status == ServiceStatus.DOWN
            assert result.latency_ms is not None
            assert result.error is not None
            assert "Connection refused" in result.error


class TestHealthCheckZenzefi:
    """Tests for Zenzefi server health check"""

    @pytest.mark.asyncio
    async def test_check_zenzefi_success(self):
        """Test successful Zenzefi health check"""
        # Mock httpx client
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                return_value=mock_response
            )

            result = await HealthCheckService.check_zenzefi()

            assert result.status == ServiceStatus.UP
            assert result.latency_ms is not None
            assert result.error is None
            assert result.url is not None

    @pytest.mark.asyncio
    async def test_check_zenzefi_failure_404(self):
        """Test Zenzefi health check with 404 response"""
        # Mock httpx client
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 404
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                return_value=mock_response
            )

            result = await HealthCheckService.check_zenzefi()

            assert result.status == ServiceStatus.DOWN
            assert result.error is not None
            assert "404" in result.error

    @pytest.mark.asyncio
    async def test_check_zenzefi_connection_error(self):
        """Test Zenzefi health check with connection error"""
        # Mock httpx client to raise exception
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                side_effect=Exception("Connection refused")
            )

            result = await HealthCheckService.check_zenzefi()

            assert result.status == ServiceStatus.DOWN
            assert result.error is not None
            assert "Connection refused" in result.error


class TestOverallStatus:
    """Tests for overall status determination"""

    def test_all_services_up(self):
        """Test when all services are up"""
        checks = HealthChecks(
            database=ServiceCheck(status=ServiceStatus.UP, latency_ms=10),
            redis=ServiceCheck(status=ServiceStatus.UP, latency_ms=1),
            zenzefi=ServiceCheck(status=ServiceStatus.UP, latency_ms=150),
        )

        status = HealthCheckService.determine_overall_status(checks)

        assert status == OverallStatus.HEALTHY

    def test_database_down(self):
        """Test when database is down (critical)"""
        checks = HealthChecks(
            database=ServiceCheck(
                status=ServiceStatus.DOWN, error="Connection failed"
            ),
            redis=ServiceCheck(status=ServiceStatus.UP, latency_ms=1),
            zenzefi=ServiceCheck(status=ServiceStatus.UP, latency_ms=150),
        )

        status = HealthCheckService.determine_overall_status(checks)

        assert status == OverallStatus.UNHEALTHY

    def test_redis_down(self):
        """Test when Redis is down (critical)"""
        checks = HealthChecks(
            database=ServiceCheck(status=ServiceStatus.UP, latency_ms=10),
            redis=ServiceCheck(status=ServiceStatus.DOWN, error="Connection failed"),
            zenzefi=ServiceCheck(status=ServiceStatus.UP, latency_ms=150),
        )

        status = HealthCheckService.determine_overall_status(checks)

        assert status == OverallStatus.UNHEALTHY

    def test_zenzefi_down(self):
        """Test when only Zenzefi is down (non-critical)"""
        checks = HealthChecks(
            database=ServiceCheck(status=ServiceStatus.UP, latency_ms=10),
            redis=ServiceCheck(status=ServiceStatus.UP, latency_ms=1),
            zenzefi=ServiceCheck(status=ServiceStatus.DOWN, error="Connection failed"),
        )

        status = HealthCheckService.determine_overall_status(checks)

        assert status == OverallStatus.DEGRADED

    def test_all_services_down(self):
        """Test when all services are down"""
        checks = HealthChecks(
            database=ServiceCheck(
                status=ServiceStatus.DOWN, error="Connection failed"
            ),
            redis=ServiceCheck(status=ServiceStatus.DOWN, error="Connection failed"),
            zenzefi=ServiceCheck(status=ServiceStatus.DOWN, error="Connection failed"),
        )

        status = HealthCheckService.determine_overall_status(checks)

        assert status == OverallStatus.UNHEALTHY


class TestHealthCheckIntegration:
    """Integration tests for full health check"""

    @pytest.mark.asyncio
    async def test_perform_health_check_success(self, test_db: Session, fake_redis):
        """Test full health check with all services up"""
        # Mock Zenzefi check
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                return_value=mock_response
            )

            result = await HealthCheckService.perform_health_check()

            assert result.status == OverallStatus.HEALTHY
            assert result.checks.database.status == ServiceStatus.UP
            assert result.checks.redis.status == ServiceStatus.UP
            assert result.checks.zenzefi.status == ServiceStatus.UP
            assert result.overall.healthy_count == 3
            assert result.overall.total_count == 3

    @pytest.mark.asyncio
    async def test_save_and_retrieve_health_from_redis(
        self, test_db: Session, fake_redis
    ):
        """Test saving and retrieving health status from Redis"""
        # Mock Zenzefi check
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                return_value=mock_response
            )

            # Perform health check
            health = await HealthCheckService.perform_health_check()

            # Save to Redis
            await HealthCheckService.save_health_to_redis(health)

            # Retrieve from Redis
            cached_health = HealthCheckService.get_health_from_redis()

            assert cached_health is not None
            assert cached_health.status == health.status
            assert cached_health.checks.database.status == health.checks.database.status
            assert cached_health.checks.redis.status == health.checks.redis.status
            assert cached_health.checks.zenzefi.status == health.checks.zenzefi.status
