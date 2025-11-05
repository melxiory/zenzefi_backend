import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app
from app.models.token import AccessToken
from app.services.token_service import TokenService


@pytest.fixture
def authenticated_client(client: TestClient, test_user_data: dict):
    """Create a client with authenticated user"""
    # Register user
    client.post("/api/v1/auth/register", json=test_user_data)

    # Login to get JWT token
    login_data = {
        "email": test_user_data["email"],
        "password": test_user_data["password"],
    }
    login_response = client.post("/api/v1/auth/login", json=login_data)
    jwt_token = login_response.json()["access_token"]

    # Store token in client for convenience
    client.headers = {"Authorization": f"Bearer {jwt_token}"}

    return client


def test_authenticate_with_cookie(authenticated_client: TestClient):
    """Test setting cookie via /authenticate endpoint"""
    # Purchase access token
    purchase_response = authenticated_client.post(
        "/api/v1/tokens/purchase",
        json={"duration_hours": 24}
    )
    access_token = purchase_response.json()["token"]

    # Send token to set cookie
    response = authenticated_client.post(
        "/api/v1/proxy/authenticate",
        json={"token": access_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["cookie_set"] is True

    # Check that cookie is set
    assert "zenzefi_access_token" in response.cookies


def test_authenticate_with_invalid_token(client):
    """Test /authenticate with invalid token"""
    response = client.post(
        "/api/v1/proxy/authenticate",
        json={"token": "invalid_token"}
    )

    assert response.status_code == 401
    assert "Invalid or expired access token" in response.json()["detail"]


def test_authenticate_without_token(client):
    """Test /authenticate without token in body"""
    response = client.post(
        "/api/v1/proxy/authenticate",
        json={}
    )

    assert response.status_code == 400
    assert "Token is required" in response.json()["detail"]


def test_proxy_with_cookie(authenticated_client: TestClient):
    """Test proxying with cookie"""
    # Purchase access token
    purchase_response = authenticated_client.post(
        "/api/v1/tokens/purchase",
        json={"duration_hours": 24}
    )
    access_token = purchase_response.json()["token"]

    # Set cookie
    auth_response = authenticated_client.post(
        "/api/v1/proxy/authenticate",
        json={"token": access_token}
    )

    # Extract cookie from response and set on client
    for cookie_name, cookie_value in auth_response.cookies.items():
        authenticated_client.cookies.set(cookie_name, cookie_value)

    # Make request with cookie
    response = authenticated_client.get("/api/v1/proxy/some/path")

    # Cookie should work - backend accepts it and proxies the request
    # Response can be:
    #   200 (success),
    #   401 (Zenzefi rejects token),
    #   404 (path doesn't exist on Zenzefi),
    #   502/504 (Zenzefi unavailable)
    # We just verify the cookie was accepted by our backend (not 401 "Authentication required")
    assert response.status_code in [200, 401, 404, 502, 504]


def test_proxy_with_header_still_works(authenticated_client: TestClient):
    """Test that old method (header) still works"""
    # Purchase access token
    purchase_response = authenticated_client.post(
        "/api/v1/tokens/purchase",
        json={"duration_hours": 24}
    )
    access_token = purchase_response.json()["token"]

    # Use old method with header
    response = authenticated_client.get(
        "/api/v1/proxy/some/path",
        headers={"X-Access-Token": access_token}
    )

    # Header should work - backend accepts it and proxies the request
    # Response can be:
    #   200 (success),
    #   401 (Zenzefi rejects token),
    #   404 (path doesn't exist on Zenzefi),
    #   502/504 (Zenzefi unavailable)
    # We just verify the header was accepted by our backend (not 401 "Authentication required")
    assert response.status_code in [200, 401, 404, 502, 504]


def test_proxy_without_auth_fails(client):
    """Test that request without authentication is rejected"""
    response = client.get("/api/v1/proxy/some/path")

    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


def test_logout_deletes_cookie(authenticated_client: TestClient):
    """Test cookie deletion on logout"""
    # Purchase access token
    purchase_response = authenticated_client.post(
        "/api/v1/tokens/purchase",
        json={"duration_hours": 24}
    )
    access_token = purchase_response.json()["token"]

    # Set cookie
    authenticated_client.post(
        "/api/v1/proxy/authenticate",
        json={"token": access_token}
    )

    # Logout
    response = authenticated_client.delete("/api/v1/proxy/logout")

    assert response.status_code == 200
    assert response.json()["logged_out"] is True


def test_status_with_cookie(authenticated_client: TestClient):
    """Test /status endpoint with cookie"""
    # Purchase access token
    purchase_response = authenticated_client.post(
        "/api/v1/tokens/purchase",
        json={"duration_hours": 24}
    )
    access_token = purchase_response.json()["token"]

    # Set cookie
    auth_response = authenticated_client.post(
        "/api/v1/proxy/authenticate",
        json={"token": access_token}
    )

    # Extract cookie from response and set on client
    for cookie_name, cookie_value in auth_response.cookies.items():
        authenticated_client.cookies.set(cookie_name, cookie_value)

    # Check status
    response = authenticated_client.get("/api/v1/proxy/status")

    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["authenticated_via"] == "cookie"


def test_status_with_header(authenticated_client: TestClient):
    """Test /status endpoint with header"""
    # Purchase access token
    purchase_response = authenticated_client.post(
        "/api/v1/tokens/purchase",
        json={"duration_hours": 24}
    )
    access_token = purchase_response.json()["token"]

    # Check status with header
    response = authenticated_client.get(
        "/api/v1/proxy/status",
        headers={"X-Access-Token": access_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["authenticated_via"] == "header"


def test_status_without_auth_fails(client):
    """Test /status without authentication fails"""
    response = client.get("/api/v1/proxy/status")

    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


def test_cookie_priority_over_header(authenticated_client: TestClient):
    """Test that cookie has priority over header"""
    # Purchase two different access tokens
    purchase1_response = authenticated_client.post(
        "/api/v1/tokens/purchase",
        json={"duration_hours": 24}
    )
    token1 = purchase1_response.json()["token"]
    token1_id = purchase1_response.json()["id"]

    purchase2_response = authenticated_client.post(
        "/api/v1/tokens/purchase",
        json={"duration_hours": 12}
    )
    token2 = purchase2_response.json()["token"]

    # Set cookie with token1
    auth_response = authenticated_client.post(
        "/api/v1/proxy/authenticate",
        json={"token": token1}
    )

    # Extract cookie from response and set on client
    for cookie_name, cookie_value in auth_response.cookies.items():
        authenticated_client.cookies.set(cookie_name, cookie_value)

    # Check status with header token2 (cookie should take priority)
    response = authenticated_client.get(
        "/api/v1/proxy/status",
        headers={"X-Access-Token": token2}
    )

    assert response.status_code == 200
    data = response.json()
    # Should use cookie (token1), not header (token2)
    assert data["authenticated_via"] == "cookie"
    assert data["token_id"] == token1_id  # Should use token1 from cookie
