"""
Tests for API tokens endpoints (app/api/v1/tokens.py)
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authenticated_client(client: TestClient, test_user_data: dict, fake_redis, test_db):
    """Create a client with authenticated user, fake Redis, and funded balance"""
    from decimal import Decimal
    from app.models import User
    from app.services.currency_service import CurrencyService

    # Register user
    client.post("/api/v1/auth/register", json=test_user_data)

    # Login to get token
    login_data = {
        "email": test_user_data["email"],
        "password": test_user_data["password"],
    }
    login_response = client.post("/api/v1/auth/login", json=login_data)
    jwt_token = login_response.json()["access_token"]

    # Fund user balance (1000 ZNC for token purchases)
    user = test_db.query(User).filter(User.email == test_user_data["email"]).first()
    CurrencyService.credit_balance(
        user_id=user.id,
        amount=Decimal("1000.00"),
        description="Test initial balance",
        payment_id=None,
        db=test_db
    )

    # Store token in client for convenience
    client.headers = {"Authorization": f"Bearer {jwt_token}"}

    return client


class TestTokenPurchaseEndpoint:
    """Tests for POST /api/v1/tokens/purchase endpoint"""

    def test_purchase_token_success(
        self, authenticated_client: TestClient, test_user_data: dict
    ):
        """Test successful token purchase"""
        purchase_data = {"duration_hours": 24}

        response = authenticated_client.post(
            "/api/v1/tokens/purchase", json=purchase_data
        )

        # Check status code
        assert response.status_code == 201

        # Check response data
        data = response.json()
        assert "id" in data
        assert "token" in data
        assert data["duration_hours"] == 24
        assert data["is_active"] is True
        assert "expires_at" in data
        assert data["expires_at"] is None  # Not activated yet
        assert data["activated_at"] is None  # Not activated yet
        assert "created_at" in data

        # Token string should exist and have content
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 0

    def test_purchase_token_all_valid_durations(
        self, authenticated_client: TestClient
    ):
        """Test purchasing tokens with all valid durations"""
        valid_durations = [1, 12, 24, 168, 720]

        for duration in valid_durations:
            purchase_data = {"duration_hours": duration}
            response = authenticated_client.post(
                "/api/v1/tokens/purchase", json=purchase_data
            )

            assert response.status_code == 201
            assert response.json()["duration_hours"] == duration

    def test_purchase_token_invalid_duration(self, authenticated_client: TestClient):
        """Test purchasing token with invalid duration"""
        # Test durations that pass Pydantic validation but fail business logic
        invalid_durations = [2, 5, 100, 1000]

        for duration in invalid_durations:
            purchase_data = {"duration_hours": duration}
            response = authenticated_client.post(
                "/api/v1/tokens/purchase", json=purchase_data
            )

            # Should fail with 400 (business logic error)
            assert response.status_code == 400
            assert "Invalid duration" in response.json()["detail"]

        # Test duration=0 which fails Pydantic validation (ge=1)
        response = authenticated_client.post(
            "/api/v1/tokens/purchase", json={"duration_hours": 0}
        )
        assert response.status_code == 422  # Pydantic validation error

    def test_purchase_token_without_authentication(self, client: TestClient):
        """Test purchasing token without authentication"""
        purchase_data = {"duration_hours": 24}

        response = client.post("/api/v1/tokens/purchase", json=purchase_data)

        # Should fail with 403 Forbidden (FastAPI returns 403 for missing credentials)
        assert response.status_code == 403

    def test_purchase_multiple_tokens(self, authenticated_client: TestClient):
        """Test purchasing multiple tokens for same user"""
        # Purchase first token
        response1 = authenticated_client.post(
            "/api/v1/tokens/purchase", json={"duration_hours": 24}
        )
        token1_id = response1.json()["id"]

        # Purchase second token
        response2 = authenticated_client.post(
            "/api/v1/tokens/purchase", json={"duration_hours": 12}
        )
        token2_id = response2.json()["id"]

        # Both should succeed and have different IDs
        assert response1.status_code == 201
        assert response2.status_code == 201
        assert token1_id != token2_id


class TestGetMyTokensEndpoint:
    """Tests for GET /api/v1/tokens/my-tokens endpoint"""

    def test_get_my_tokens_empty(self, authenticated_client: TestClient):
        """Test getting tokens when user has no tokens"""
        response = authenticated_client.get("/api/v1/tokens/my-tokens")

        # Should succeed with empty list
        assert response.status_code == 200
        assert response.json() == []

    def test_get_my_tokens_with_tokens(self, authenticated_client: TestClient):
        """Test getting tokens when user has tokens"""
        # Purchase tokens
        authenticated_client.post(
            "/api/v1/tokens/purchase", json={"duration_hours": 24}
        )
        authenticated_client.post(
            "/api/v1/tokens/purchase", json={"duration_hours": 12}
        )

        # Get tokens
        response = authenticated_client.get("/api/v1/tokens/my-tokens")

        # Should return both tokens
        assert response.status_code == 200
        tokens = response.json()
        assert len(tokens) == 2

        # Check token structure
        for token in tokens:
            assert "id" in token
            assert "token" in token
            assert "duration_hours" in token
            assert "is_active" in token

    def test_get_my_tokens_active_only(self, authenticated_client: TestClient):
        """Test getting only active tokens"""
        # Purchase token
        response = authenticated_client.get("/api/v1/tokens/my-tokens?active_only=true")

        # Should succeed
        assert response.status_code == 200

    def test_get_my_tokens_all(self, authenticated_client: TestClient):
        """Test getting all tokens (including inactive)"""
        # Purchase token
        response = authenticated_client.get(
            "/api/v1/tokens/my-tokens?active_only=false"
        )

        # Should succeed
        assert response.status_code == 200

    def test_get_my_tokens_without_authentication(self, client: TestClient):
        """Test getting tokens without authentication"""
        response = client.get("/api/v1/tokens/my-tokens")

        # Should fail with 403 Forbidden (FastAPI returns 403 for missing credentials)
        assert response.status_code == 403


class TestTokensEndpointsIntegration:
    """Integration tests for tokens endpoints"""

    def test_full_token_lifecycle(
        self, client: TestClient, test_user_data: dict, test_user_data_2: dict, test_db
    ):
        """Test complete token lifecycle: register -> login -> purchase -> check status"""
        from decimal import Decimal
        from app.models import User
        from app.services.currency_service import CurrencyService

        # Step 1: Register user
        register_response = client.post("/api/v1/auth/register", json=test_user_data)
        assert register_response.status_code == 201

        # Fund user balance
        user = test_db.query(User).filter(User.email == test_user_data["email"]).first()
        CurrencyService.credit_balance(
            user_id=user.id,
            amount=Decimal("1000.00"),
            description="Test balance",
            payment_id=None,
            db=test_db
        )

        # Step 2: Login
        login_data = {
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        }
        login_response = client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        jwt_token = login_response.json()["access_token"]

        # Step 3: Purchase access token
        headers = {"Authorization": f"Bearer {jwt_token}"}
        purchase_response = client.post(
            "/api/v1/tokens/purchase", json={"duration_hours": 24}, headers=headers
        )
        assert purchase_response.status_code == 201
        access_token = purchase_response.json()["token"]

        # Step 4: Check token status (read-only, doesn't activate)
        status_response = client.get(
            "/api/v1/proxy/status", headers={"X-Access-Token": access_token}
        )
        assert status_response.status_code == 200
        assert status_response.json()["is_activated"] is False

        # Step 5: Get my tokens
        my_tokens_response = client.get("/api/v1/tokens/my-tokens", headers=headers)
        assert my_tokens_response.status_code == 200
        assert len(my_tokens_response.json()) == 1

    def test_different_users_different_tokens(
        self, client: TestClient, test_user_data: dict, test_user_data_2: dict, test_db
    ):
        """Test that different users get different tokens"""
        from decimal import Decimal
        from app.models import User
        from app.services.currency_service import CurrencyService

        # Register and login user 1
        client.post("/api/v1/auth/register", json=test_user_data)
        user1 = test_db.query(User).filter(User.email == test_user_data["email"]).first()
        CurrencyService.credit_balance(user1.id, Decimal("1000.00"), "Test balance", None, test_db)

        login1_response = client.post(
            "/api/v1/auth/login",
            json={"email": test_user_data["email"], "password": test_user_data["password"]},
        )
        jwt_token1 = login1_response.json()["access_token"]

        # Register and login user 2
        client.post("/api/v1/auth/register", json=test_user_data_2)
        user2 = test_db.query(User).filter(User.email == test_user_data_2["email"]).first()
        CurrencyService.credit_balance(user2.id, Decimal("1000.00"), "Test balance", None, test_db)

        login2_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user_data_2["email"],
                "password": test_user_data_2["password"],
            },
        )
        jwt_token2 = login2_response.json()["access_token"]

        # Purchase tokens for both users
        headers1 = {"Authorization": f"Bearer {jwt_token1}"}
        headers2 = {"Authorization": f"Bearer {jwt_token2}"}

        purchase1 = client.post(
            "/api/v1/tokens/purchase", json={"duration_hours": 24}, headers=headers1
        )
        purchase2 = client.post(
            "/api/v1/tokens/purchase", json={"duration_hours": 24}, headers=headers2
        )

        # Tokens should be different
        token1 = purchase1.json()["token"]
        token2 = purchase2.json()["token"]
        assert token1 != token2

        # Each user should only see their own tokens
        my_tokens1 = client.get("/api/v1/tokens/my-tokens", headers=headers1).json()
        my_tokens2 = client.get("/api/v1/tokens/my-tokens", headers=headers2).json()

        assert len(my_tokens1) == 1
        assert len(my_tokens2) == 1
        assert my_tokens1[0]["token"] == token1
        assert my_tokens2[0]["token"] == token2
