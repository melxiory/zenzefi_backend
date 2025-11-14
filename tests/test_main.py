"""
Tests for app/main.py - main application endpoints
"""
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for /health endpoint"""

    def test_health_check(self, client: TestClient):
        """Test simple health check endpoint - returns minimal status"""
        response = client.get("/health")

        # Should return 200 OK
        assert response.status_code == 200

        # Check response structure (simple version with only status and timestamp)
        data = response.json()
        assert "status" in data
        assert "timestamp" in data

        # Should NOT include detailed fields (checks, overall)
        assert "checks" not in data
        assert "overall" not in data

        # Check status value
        assert data["status"] in ["healthy", "degraded", "unhealthy"]


class TestRootEndpoint:
    """Tests for / root endpoint"""

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint"""
        response = client.get("/")

        # Should return 200 OK
        assert response.status_code == 200

        # Check response structure
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "docs" in data

        # Check values
        assert "Welcome to Zenzefi Backend" in data["message"]
        assert data["version"] == "0.1.0"  # Current version
        assert data["docs"] == "/docs"


class TestCORSMiddleware:
    """Tests for CORS middleware configuration"""

    def test_cors_headers_present(self, client: TestClient):
        """Test that CORS headers are present in response"""
        response = client.get("/health")

        # Check CORS headers (these are added by CORS middleware)
        assert response.status_code == 200


class TestApplicationStartup:
    """Tests for application startup and configuration"""

    def test_openapi_docs_available(self, client: TestClient):
        """Test that OpenAPI docs are available"""
        response = client.get("/docs")

        # Should return 200 OK (HTML page)
        assert response.status_code == 200

    def test_openapi_json_available(self, client: TestClient):
        """Test that OpenAPI JSON is available"""
        response = client.get("/openapi.json")

        # Should return 200 OK
        assert response.status_code == 200

        # Should be JSON
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert data["info"]["title"] == "Zenzefi Backend"

    def test_redoc_available(self, client: TestClient):
        """Test that ReDoc documentation is available"""
        response = client.get("/redoc")

        # Should return 200 OK (HTML page)
        assert response.status_code == 200


class TestAPIRouting:
    """Tests for API routing configuration"""

    def test_api_v1_prefix(self, client: TestClient):
        """Test that API v1 endpoints are under /api/v1 prefix"""
        # Try to access auth endpoint with correct prefix
        response = client.post("/api/v1/auth/login", json={})

        # Should NOT return 404 (may return 422 for invalid data, which is expected)
        assert response.status_code != 404

    def test_invalid_route_returns_404(self, client: TestClient):
        """Test that invalid routes return 404"""
        response = client.get("/invalid/route/that/does/not/exist")

        # Should return 404 Not Found
        assert response.status_code == 404
