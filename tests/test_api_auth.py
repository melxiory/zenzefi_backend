"""
Tests for API auth endpoints (app/api/v1/auth.py)
"""
import pytest
from fastapi.testclient import TestClient


class TestAuthRegisterEndpoint:
    """Tests for POST /api/v1/auth/register endpoint"""

    def test_register_success(self, client: TestClient, test_user_data: dict):
        """Test successful user registration"""
        response = client.post("/api/v1/auth/register", json=test_user_data)

        # Check status code
        assert response.status_code == 201

        # Check response data
        data = response.json()
        assert data["email"] == test_user_data["email"]
        assert data["username"] == test_user_data["username"]
        assert data["full_name"] == test_user_data["full_name"]
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data

        # Password should not be in response
        assert "password" not in data
        assert "hashed_password" not in data

    def test_register_duplicate_email(
        self, client: TestClient, test_user_data: dict, test_user_data_2: dict
    ):
        """Test registration with duplicate email"""
        # Register first user
        client.post("/api/v1/auth/register", json=test_user_data)

        # Try to register with same email
        duplicate_data = test_user_data_2.copy()
        duplicate_data["email"] = test_user_data["email"]

        response = client.post("/api/v1/auth/register", json=duplicate_data)

        # Should fail
        assert response.status_code == 400
        assert "Email already registered" in response.json()["detail"]

    def test_register_duplicate_username(
        self, client: TestClient, test_user_data: dict, test_user_data_2: dict
    ):
        """Test registration with duplicate username"""
        # Register first user
        client.post("/api/v1/auth/register", json=test_user_data)

        # Try to register with same username
        duplicate_data = test_user_data_2.copy()
        duplicate_data["username"] = test_user_data["username"]

        response = client.post("/api/v1/auth/register", json=duplicate_data)

        # Should fail
        assert response.status_code == 400
        assert "Username already taken" in response.json()["detail"]

    def test_register_invalid_email(self, client: TestClient):
        """Test registration with invalid email format"""
        invalid_data = {
            "email": "not-an-email",
            "username": "testuser",
            "password": "TestPass123!",
        }

        response = client.post("/api/v1/auth/register", json=invalid_data)

        # Should fail validation
        assert response.status_code == 422

    def test_register_missing_required_fields(self, client: TestClient):
        """Test registration with missing required fields"""
        incomplete_data = {
            "email": "test@example.com",
            # Missing username and password
        }

        response = client.post("/api/v1/auth/register", json=incomplete_data)

        # Should fail validation
        assert response.status_code == 422

    def test_register_without_full_name(self, client: TestClient):
        """Test registration without optional full_name field"""
        data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "TestPass123!",
        }

        response = client.post("/api/v1/auth/register", json=data)

        # Should succeed
        assert response.status_code == 201
        assert response.json()["full_name"] is None


class TestAuthLoginEndpoint:
    """Tests for POST /api/v1/auth/login endpoint"""

    def test_login_success(self, client: TestClient, test_user_data: dict):
        """Test successful login"""
        # Register user first
        client.post("/api/v1/auth/register", json=test_user_data)

        # Login
        login_data = {
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        }
        response = client.post("/api/v1/auth/login", json=login_data)

        # Check status code
        assert response.status_code == 200

        # Check response data
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 3600  # 1 hour in seconds

        # Token should be a string
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0

    def test_login_wrong_password(self, client: TestClient, test_user_data: dict):
        """Test login with wrong password"""
        # Register user
        client.post("/api/v1/auth/register", json=test_user_data)

        # Try to login with wrong password
        login_data = {
            "email": test_user_data["email"],
            "password": "WrongPassword123!",
        }
        response = client.post("/api/v1/auth/login", json=login_data)

        # Should fail
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_login_nonexistent_email(self, client: TestClient):
        """Test login with non-existent email"""
        login_data = {
            "email": "nonexistent@example.com",
            "password": "AnyPassword123!",
        }
        response = client.post("/api/v1/auth/login", json=login_data)

        # Should fail
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_login_missing_fields(self, client: TestClient):
        """Test login with missing fields"""
        # Missing password
        response = client.post(
            "/api/v1/auth/login", json={"email": "test@example.com"}
        )

        # Should fail validation
        assert response.status_code == 422

    def test_login_token_can_be_decoded(
        self, client: TestClient, test_user_data: dict
    ):
        """Test that login token can be decoded"""
        from app.core.security import decode_access_token

        # Register and login
        register_response = client.post("/api/v1/auth/register", json=test_user_data)
        user_id = register_response.json()["id"]

        login_data = {
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        }
        login_response = client.post("/api/v1/auth/login", json=login_data)

        # Decode token
        token = login_response.json()["access_token"]
        decoded = decode_access_token(token)

        # Check decoded data
        assert decoded is not None
        assert decoded["sub"] == user_id
        assert decoded["username"] == test_user_data["username"]


class TestAuthEndpointsIntegration:
    """Integration tests for auth endpoints"""

    def test_register_login_flow(self, client: TestClient, test_user_data: dict):
        """Test complete register -> login flow"""
        # Step 1: Register
        register_response = client.post("/api/v1/auth/register", json=test_user_data)
        assert register_response.status_code == 201
        user_data = register_response.json()

        # Step 2: Login
        login_data = {
            "email": test_user_data["email"],
            "password": test_user_data["password"],
        }
        login_response = client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        token_data = login_response.json()

        # Step 3: Use token to access protected endpoint (users/me)
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        me_response = client.get("/api/v1/users/me", headers=headers)

        # Should be able to access protected route
        assert me_response.status_code == 200
        me_data = me_response.json()

        # User data should match
        assert me_data["id"] == user_data["id"]
        assert me_data["email"] == user_data["email"]
        assert me_data["username"] == user_data["username"]

    def test_multiple_users_registration(
        self, client: TestClient, test_user_data: dict, test_user_data_2: dict
    ):
        """Test registering multiple different users"""
        # Register first user
        response1 = client.post("/api/v1/auth/register", json=test_user_data)
        assert response1.status_code == 201

        # Register second user
        response2 = client.post("/api/v1/auth/register", json=test_user_data_2)
        assert response2.status_code == 201

        # Both should have different IDs
        user1_id = response1.json()["id"]
        user2_id = response2.json()["id"]
        assert user1_id != user2_id
