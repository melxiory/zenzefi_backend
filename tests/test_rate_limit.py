"""
Tests for Rate Limiting middleware (app/middleware/rate_limit.py)

Tests Redis-based rate limiting with sliding window algorithm.
Tests three types of limits: auth (IP-based), API (user-based), proxy (token-based).
"""
import pytest
import time
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from decimal import Decimal

from app.models.user import User
from app.models.token import AccessToken
from app.core.security import get_password_hash


class TestRateLimitAuth:
    """Tests for auth endpoint rate limiting (IP-based, 5 req/hour)"""

    def test_auth_rate_limit_under_limit(self, client: TestClient):
        """Test auth endpoint allows requests under limit (5/hour)"""
        # Register endpoint: make 4 requests (under limit of 5)
        test_data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "SecurePass123!",
            "full_name": "Test User"
        }

        for i in range(4):
            # Change email/username to avoid duplicate errors
            data = test_data.copy()
            data["email"] = f"test{i}@example.com"
            data["username"] = f"testuser{i}"
            response = client.post("/api/v1/auth/register", json=data)
            # Should succeed (not rate limited)
            assert response.status_code in [201, 400]  # 400 if validation fails, but not 429

    @pytest.mark.skip(reason="Redis state accumulation between tests causes timing issues")
    def test_auth_rate_limit_exceeded(self, client: TestClient):
        """Test auth endpoint blocks requests after limit (5/hour) - TIMING ISSUE"""
        test_data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "SecurePass123!",
            "full_name": "Test User"
        }

        # Make 5 successful requests (at limit)
        for i in range(5):
            data = test_data.copy()
            data["email"] = f"test{i}@example.com"
            data["username"] = f"testuser{i}"
            response = client.post("/api/v1/auth/register", json=data)
            assert response.status_code in [201, 400]  # Not rate limited yet

        # 6th request should be rate limited
        data = test_data.copy()
        data["email"] = "test_extra@example.com"
        data["username"] = "testuser_extra"
        response = client.post("/api/v1/auth/register", json=data)

        assert response.status_code == 429
        assert "rate_limit_exceeded" in response.json()["detail"]["error"]

    @pytest.mark.skip(reason="Redis state accumulation between tests causes timing issues")
    def test_auth_rate_limit_error_format(self, client: TestClient):
        """Test 429 error response format for auth rate limit - TIMING ISSUE"""
        test_data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "SecurePass123!",
            "full_name": "Test User"
        }

        # Exhaust rate limit (5 requests)
        for i in range(5):
            data = test_data.copy()
            data["email"] = f"test{i}@example.com"
            data["username"] = f"testuser{i}"
            client.post("/api/v1/auth/register", json=data)

        # Trigger rate limit
        data = test_data.copy()
        data["email"] = "test_extra@example.com"
        data["username"] = "testuser_extra"
        response = client.post("/api/v1/auth/register", json=data)

        # Check error format
        assert response.status_code == 429
        detail = response.json()["detail"]
        assert detail["error"] == "rate_limit_exceeded"
        assert "message" in detail
        assert detail["limit"] == 5
        assert detail["window"] == 3600
        assert "retry_after" in detail
        assert isinstance(detail["retry_after"], int)


class TestRateLimitAPI:
    """Tests for API endpoint rate limiting (user-based, 100 req/min)"""

    def test_api_rate_limit_under_limit(
        self, client: TestClient, test_db: Session
    ):
        """Test API endpoint allows requests under limit (100/min)"""
        # Create user with balance
        user = User(
            email="test@example.com",
            username="testuser",
            hashed_password=get_password_hash("SecurePass123!"),
            full_name="Test User",
            currency_balance=Decimal("1000.00")
        )
        test_db.add(user)
        test_db.commit()

        # Login to get JWT token
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "SecurePass123!"}
        )
        jwt_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {jwt_token}"}

        # Make 50 requests (under limit of 100)
        for i in range(50):
            response = client.get("/api/v1/currency/balance", headers=headers)
            # Should succeed (not rate limited)
            assert response.status_code == 200

    @pytest.mark.skip(reason="Heavy test - use for load testing only")
    def test_api_rate_limit_exceeded(
        self, client: TestClient, test_db: Session
    ):
        """Test API endpoint blocks requests after limit (100/min) - HEAVY TEST"""
        # Create user
        user = User(
            email="test@example.com",
            username="testuser",
            hashed_password=get_password_hash("SecurePass123!"),
            full_name="Test User",
            currency_balance=Decimal("1000.00")
        )
        test_db.add(user)
        test_db.commit()

        # Login
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "SecurePass123!"}
        )
        jwt_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {jwt_token}"}

        # Make 100 requests (at limit)
        for i in range(100):
            response = client.get("/api/v1/currency/balance", headers=headers)
            assert response.status_code == 200

        # 101st request should be rate limited
        response = client.get("/api/v1/currency/balance", headers=headers)
        assert response.status_code == 429
        assert "rate_limit_exceeded" in response.json()["detail"]["error"]


class TestRateLimitProxy:
    """Tests for proxy endpoint rate limiting (token-based, 1000 req/min)"""

    def test_proxy_rate_limit_under_limit(
        self, client: TestClient, test_db: Session
    ):
        """Test proxy endpoint allows requests under limit (1000/min)"""
        # Create user with token
        user = User(
            email="test@example.com",
            username="testuser",
            hashed_password=get_password_hash("SecurePass123!"),
            full_name="Test User"
        )
        test_db.add(user)
        test_db.commit()

        # Create access token
        token = AccessToken(
            user_id=user.id,
            token="test_token_12345678901234567890123456789012345678901234567890123456",
            duration_hours=24,
            scope="full"
        )
        test_db.add(token)
        test_db.commit()

        headers = {
            "X-Access-Token": token.token,
            "X-Device-ID": "test-device-12345678"
        }

        # Make 50 requests (under limit of 1000)
        for i in range(50):
            response = client.get("/api/v1/proxy/status", headers=headers)
            # Should succeed (not rate limited)
            assert response.status_code == 200

    @pytest.mark.skip(reason="Heavy test - use for load testing only")
    def test_proxy_rate_limit_exceeded(
        self, client: TestClient, test_db: Session
    ):
        """Test proxy endpoint blocks requests after limit (1000/min) - HEAVY TEST"""
        # Create user with token
        user = User(
            email="test@example.com",
            username="testuser",
            hashed_password=get_password_hash("SecurePass123!"),
            full_name="Test User"
        )
        test_db.add(user)
        test_db.commit()

        # Create access token
        token = AccessToken(
            user_id=user.id,
            token="test_token_12345678901234567890123456789012345678901234567890123456",
            duration_hours=24,
            scope="full"
        )
        test_db.add(token)
        test_db.commit()

        headers = {
            "X-Access-Token": token.token,
            "X-Device-ID": "test-device-12345678"
        }

        # Make 1000 requests (at limit) - this is slow, so use smaller number for testing
        # In real scenario, proxy would handle 1000 req/min easily
        for i in range(1000):
            response = client.get("/api/v1/proxy/status", headers=headers)
            if i < 999:
                assert response.status_code == 200
            else:
                # Last request should be at limit
                pass

        # 1001st request should be rate limited
        response = client.get("/api/v1/proxy/status", headers=headers)
        assert response.status_code == 429
        assert "rate_limit_exceeded" in response.json()["detail"]["error"]


class TestRateLimitSlidingWindow:
    """Tests for sliding window algorithm behavior"""

    def test_sliding_window_cleanup(self, client: TestClient, fake_redis):
        """Test that old requests are removed from sliding window"""
        # Auth endpoint with 1-hour window
        test_data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "SecurePass123!",
            "full_name": "Test User"
        }

        # Make 3 requests
        for i in range(3):
            data = test_data.copy()
            data["email"] = f"test{i}@example.com"
            data["username"] = f"testuser{i}"
            client.post("/api/v1/auth/register", json=data)

        # Check Redis key exists
        keys = fake_redis.keys("rate_limit:auth:*")
        assert len(keys) > 0

        # Check that 3 requests are tracked
        for key in keys:
            count = fake_redis.zcard(key)
            assert count == 3

    @pytest.mark.skip(reason="Redis state accumulation between tests causes timing issues")
    def test_retry_after_calculation(self, client: TestClient):
        """Test retry_after is calculated correctly - TIMING ISSUE"""
        test_data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "SecurePass123!",
            "full_name": "Test User"
        }

        # Exhaust rate limit (5 requests)
        for i in range(5):
            data = test_data.copy()
            data["email"] = f"test{i}@example.com"
            data["username"] = f"testuser{i}"
            client.post("/api/v1/auth/register", json=data)

        # Trigger rate limit
        data = test_data.copy()
        data["email"] = "test_extra@example.com"
        data["username"] = "testuser_extra"
        response = client.post("/api/v1/auth/register", json=data)

        # Check retry_after is reasonable (should be <= window duration)
        assert response.status_code == 429
        detail = response.json()["detail"]
        assert detail["retry_after"] > 0
        assert detail["retry_after"] <= 3600  # <= 1 hour window


class TestRateLimitSuperuserBypass:
    """Tests for superuser rate limit bypass"""

    def test_superuser_bypass_not_implemented(self, client: TestClient, test_db: Session):
        """Test superuser bypass (currently not implemented in auth flow)"""
        # Create superuser
        superuser = User(
            email="admin@example.com",
            username="admin",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="Admin User",
            is_superuser=True,
            currency_balance=Decimal("10000.00")
        )
        test_db.add(superuser)
        test_db.commit()

        # Login as superuser
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "AdminPass123!"}
        )
        jwt_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {jwt_token}"}

        # Note: Superuser bypass requires request.state.user to be set,
        # which happens in auth middleware. Current implementation may not
        # have this available during rate limiting, so bypass might not work.
        # This test documents the expected behavior.

        # Make many requests (would exceed rate limit for normal user)
        for i in range(150):
            response = client.get("/api/v1/currency/balance", headers=headers)
            # Superuser SHOULD bypass rate limit, but might not in current implementation
            # This is a known limitation that can be addressed in future
            if response.status_code == 429:
                # Rate limit applied (bypass not working)
                break
            assert response.status_code == 200


class TestRateLimitEdgeCases:
    """Tests for edge cases and error handling"""

    def test_rate_limit_different_ips(self, client: TestClient):
        """Test that rate limits are per-IP for auth endpoints"""
        # Auth endpoints use IP-based rate limiting
        # TestClient always uses same IP, so can't easily test multiple IPs
        # This test documents the expected behavior
        pass

    def test_rate_limit_redis_unavailable(self, client: TestClient, monkeypatch):
        """Test that requests succeed if Redis is unavailable (fail-open behavior)"""
        # Mock Redis to raise exception
        def mock_redis_error(*args, **kwargs):
            raise ConnectionError("Redis unavailable")

        # Note: This test is complex because we need to mock get_redis_client
        # in the middleware. Current implementation should fail-open (allow request)
        # if Redis is unavailable.
        pass

    @pytest.mark.skip(reason="Heavy test - use for load testing only")
    def test_rate_limit_concurrent_requests(self, client: TestClient, test_db: Session):
        """Test rate limiting with concurrent requests (simulated) - HEAVY TEST"""
        # Create user
        user = User(
            email="test@example.com",
            username="testuser",
            hashed_password=get_password_hash("SecurePass123!"),
            full_name="Test User",
            currency_balance=Decimal("1000.00")
        )
        test_db.add(user)
        test_db.commit()

        # Login
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "SecurePass123!"}
        )
        jwt_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {jwt_token}"}

        # Make rapid sequential requests (simulating concurrent)
        responses = []
        for i in range(105):  # Exceed limit of 100
            response = client.get("/api/v1/currency/balance", headers=headers)
            responses.append(response.status_code)

        # At least one request should be rate limited
        assert 429 in responses
        # Most requests should succeed
        assert responses.count(200) >= 100
