"""
Integration tests for token scopes functionality
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.auth_service import AuthService
from app.services.token_service import TokenService
from app.schemas.user import UserCreate


@pytest.fixture
def auth_headers(client: TestClient, test_db: Session, test_user_data: dict) -> dict:
    """Create user, login, and return authentication headers"""
    # Register user
    user_create = UserCreate(**test_user_data)
    AuthService.register_user(user_create, test_db)

    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user_data["email"], "password": test_user_data["password"]}
    )
    token = response.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


class TestTokenScopePurchase:
    """Tests for purchasing tokens with scope"""

    def test_purchase_full_scope_token(
        self, client: TestClient, test_db: Session, test_user_data: dict, auth_headers: dict
    ):
        """Test purchasing token with full scope"""
        response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24, "scope": "full"},
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["scope"] == "full"
        assert data["duration_hours"] == 24

    def test_purchase_certificates_scope_token(
        self, client: TestClient, test_db: Session, test_user_data: dict, auth_headers: dict
    ):
        """Test purchasing token with certificates_only scope"""
        response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24, "scope": "certificates_only"},
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["scope"] == "certificates_only"

    def test_default_scope_is_full(
        self, client: TestClient, test_db: Session, test_user_data: dict, auth_headers: dict
    ):
        """Test that default scope is full"""
        response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24},
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["scope"] == "full"

    def test_invalid_scope_rejected(
        self, client: TestClient, test_db: Session, test_user_data: dict, auth_headers: dict
    ):
        """Test that invalid scope is rejected"""
        response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24, "scope": "invalid_scope"},
            headers=auth_headers
        )
        assert response.status_code == 422  # Pydantic validation error


class TestTokenScopeValidation:
    """Tests for scope-based path validation"""

    def test_full_scope_accesses_all_paths(
        self, client: TestClient, test_db: Session, test_user_data: dict
    ):
        """Test that full scope token can access all paths"""
        # Create user and full scope token
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, scope="full", db=test_db
        )

        # Test various paths (will fail to proxy but should not be 403)
        paths = [
            "certificates/filter",
            "users/currentUser",
            "system/version",
        ]

        for path in paths:
            response = client.get(
                f"/api/v1/proxy/{path}",
                headers={"X-Access-Token": token.token}
            )
            # May be 502 (proxy error) but NOT 403 (forbidden)
            assert response.status_code != 403, f"Full scope should allow {path}"

    def test_certificates_scope_allows_certificate_paths(
        self, client: TestClient, test_db: Session, test_user_data: dict
    ):
        """Test that certificates_only token can access certificate paths"""
        # Create user and certificates_only scope token
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, scope="certificates_only", db=test_db
        )

        # Test certificate paths
        certificate_paths = [
            "certificates/filter",
            "certificates/details/123",
            "certificates/export/456",
        ]

        for path in certificate_paths:
            response = client.get(
                f"/api/v1/proxy/{path}",
                headers={"X-Access-Token": token.token}
            )
            # May be 502 (proxy error) but NOT 403 (forbidden)
            assert response.status_code != 403, f"Should allow {path}"

    def test_certificates_scope_blocks_other_paths(
        self, client: TestClient, test_db: Session, test_user_data: dict
    ):
        """Test that certificates_only token blocks non-certificate paths"""
        # Create user and certificates_only scope token
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, scope="certificates_only", db=test_db
        )

        # Test blocked paths
        blocked_paths = [
            "users/currentUser",
            "system/version",
            "logs/filter",
        ]

        for path in blocked_paths:
            response = client.get(
                f"/api/v1/proxy/{path}",
                headers={"X-Access-Token": token.token}
            )
            assert response.status_code == 403, f"Should block {path}"
            assert "does not allow access" in response.json()["detail"]
