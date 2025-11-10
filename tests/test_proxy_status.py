"""
Tests for /api/v1/proxy/status endpoint - ensuring it doesn't activate tokens
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.auth_service import AuthService
from app.services.token_service import TokenService
from app.schemas.user import UserCreate


class TestProxyStatusEndpoint:
    """Tests for GET /api/v1/proxy/status"""

    def test_status_does_not_activate_token(
        self, client: TestClient, test_db: Session, test_user_data: dict
    ):
        """
        Test that /proxy/status does NOT activate the token

        This is critical: users should be able to check token status
        without starting the expiration countdown.
        """
        # Create user and token
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, scope="full", db=test_db
        )

        # Verify token is not activated yet
        assert token.activated_at is None
        assert token.expires_at is None

        # Call /proxy/status endpoint
        response = client.get(
            "/api/v1/proxy/status",
            headers={"X-Access-Token": token.token}
        )

        # Status check should succeed
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data["connected"] is True
        assert data["user_id"] == str(user.id)
        assert data["token_id"] == str(token.id)
        assert data["is_activated"] is False
        assert data["expires_at"] is None
        assert data["time_remaining_seconds"] is None
        assert data["status"] == "ready"
        assert data["duration_hours"] == 24

        # CRITICAL: Verify token is STILL not activated in database
        test_db.refresh(token)
        assert token.activated_at is None, "Token should NOT be activated by /proxy/status!"
        assert token.expires_at is None, "expires_at should still be NULL!"

    def test_status_for_activated_token(
        self, client: TestClient, test_db: Session, test_user_data: dict
    ):
        """
        Test /proxy/status for an already-activated token

        Should return time remaining and activated status.
        """
        # Create user and token
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, scope="full", db=test_db
        )

        # Activate token by validating it
        TokenService.validate_token(token.token, test_db)
        test_db.refresh(token)

        # Verify token is now activated
        assert token.activated_at is not None
        assert token.expires_at is not None

        # Call /proxy/status endpoint
        response = client.get(
            "/api/v1/proxy/status",
            headers={"X-Access-Token": token.token}
        )

        # Status check should succeed
        assert response.status_code == 200
        data = response.json()

        # Verify response for activated token
        assert data["connected"] is True
        assert data["is_activated"] is True
        assert data["expires_at"] is not None
        assert data["time_remaining_seconds"] is not None
        assert data["time_remaining_seconds"] > 0
        assert data["status"] == "active"

    def test_status_with_invalid_token(self, client: TestClient):
        """Test /proxy/status with invalid token returns 401"""
        response = client.get(
            "/api/v1/proxy/status",
            headers={"X-Access-Token": "invalid-token-xyz"}
        )

        assert response.status_code == 401
        assert "Invalid or expired" in response.json()["detail"]

    def test_status_without_token(self, client: TestClient):
        """Test /proxy/status without token header returns 401"""
        response = client.get("/api/v1/proxy/status")

        # Should return 401 when no authentication is provided (neither cookie nor header)
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]
