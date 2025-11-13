"""
Integration tests for Payment API endpoints
"""
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User


@pytest.fixture
def authenticated_user(client: TestClient, test_user_data: dict, test_db: Session):
    """Create authenticated user with JWT token"""
    # Register user
    client.post("/api/v1/auth/register", json=test_user_data)

    # Login
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user_data["email"], "password": test_user_data["password"]}
    )
    jwt_token = login_response.json()["access_token"]

    # Get user from database
    user = test_db.query(User).filter(User.email == test_user_data["email"]).first()

    return {"Authorization": f"Bearer {jwt_token}"}, user


class TestPurchaseZNCAPI:
    """Tests for POST /api/v1/currency/purchase"""

    def test_purchase_znc_api(self, client: TestClient, authenticated_user):
        """Test creating a payment via API"""
        headers, user = authenticated_user

        # Create purchase request
        purchase_request = {
            "amount_znc": 100.00,
            "return_url": "https://example.com/payment/success"
        }

        response = client.post(
            "/api/v1/currency/purchase",
            json=purchase_request,
            headers=headers
        )

        # Verify response
        assert response.status_code == 201
        data = response.json()

        assert "payment_id" in data
        assert data["payment_id"].startswith("MOCK_PAY_")
        assert "payment_url" in data
        assert Decimal(data["amount_znc"]) == Decimal("100.00")
        assert Decimal(data["amount_rub"]) == Decimal("1000.00")  # 100 * 10 rate
        assert data["status"] == "pending"

    def test_purchase_znc_invalid_amount(self, client: TestClient, authenticated_user):
        """Test purchase with invalid amount"""
        headers, user = authenticated_user

        # Negative amount
        response = client.post(
            "/api/v1/currency/purchase",
            json={"amount_znc": -50, "return_url": "https://example.com"},
            headers=headers
        )
        assert response.status_code == 422  # Pydantic validation

        # Zero amount
        response = client.post(
            "/api/v1/currency/purchase",
            json={"amount_znc": 0, "return_url": "https://example.com"},
            headers=headers
        )
        assert response.status_code == 422

    def test_purchase_znc_unauthorized(self, client: TestClient):
        """Test purchase without authentication"""
        response = client.post(
            "/api/v1/currency/purchase",
            json={"amount_znc": 100, "return_url": "https://example.com"}
        )
        assert response.status_code == 403  # HTTPBearer returns 403


class TestSimulatePaymentAPI:
    """Tests for POST /api/v1/currency/admin/simulate-payment/{payment_id}"""

    def test_simulate_payment_api(self, client: TestClient, authenticated_user, test_db: Session):
        """Test simulating payment via admin API"""
        headers, user = authenticated_user

        # First create a payment
        purchase_response = client.post(
            "/api/v1/currency/purchase",
            json={"amount_znc": 50.00, "return_url": "https://example.com"},
            headers=headers
        )
        payment_id = purchase_response.json()["payment_id"]

        # Check balance before
        balance_before = client.get("/api/v1/currency/balance", headers=headers).json()["balance"]

        # Simulate payment success
        simulate_response = client.post(
            f"/api/v1/currency/admin/simulate-payment/{payment_id}"
        )

        assert simulate_response.status_code == 200
        data = simulate_response.json()
        assert data["success"] is True
        assert payment_id in data["message"]

        # Check balance after
        balance_after = client.get("/api/v1/currency/balance", headers=headers).json()["balance"]
        assert Decimal(balance_after) == Decimal(balance_before) + Decimal("50.00")

    def test_simulate_payment_not_found(self, client: TestClient):
        """Test simulating non-existent payment"""
        response = client.post(
            "/api/v1/currency/admin/simulate-payment/FAKE_PAYMENT_ID"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestWebhookEndpoint:
    """Tests for POST /api/v1/webhooks/payment"""

    def test_webhook_succeeded(self, client: TestClient, authenticated_user, test_db: Session):
        """Test webhook with succeeded status"""
        headers, user = authenticated_user

        # Create payment
        purchase_response = client.post(
            "/api/v1/currency/purchase",
            json={"amount_znc": 75.00, "return_url": "https://example.com"},
            headers=headers
        )
        payment_id = purchase_response.json()["payment_id"]

        # Check balance before
        balance_before = client.get("/api/v1/currency/balance", headers=headers).json()["balance"]

        # Send webhook
        webhook_data = {
            "payment_id": payment_id,
            "status": "succeeded"
        }
        webhook_response = client.post(
            "/api/v1/webhooks/payment",
            json=webhook_data
        )

        assert webhook_response.status_code == 200
        data = webhook_response.json()
        assert data["received"] is True
        assert data["processed"] is True

        # Check balance after
        balance_after = client.get("/api/v1/currency/balance", headers=headers).json()["balance"]
        assert Decimal(balance_after) == Decimal(balance_before) + Decimal("75.00")

    def test_webhook_canceled(self, client: TestClient, authenticated_user, test_db: Session):
        """Test webhook with canceled status"""
        headers, user = authenticated_user

        # Create payment
        purchase_response = client.post(
            "/api/v1/currency/purchase",
            json={"amount_znc": 25.00, "return_url": "https://example.com"},
            headers=headers
        )
        payment_id = purchase_response.json()["payment_id"]

        # Check balance before
        balance_before = client.get("/api/v1/currency/balance", headers=headers).json()["balance"]

        # Send webhook with canceled status
        webhook_data = {
            "payment_id": payment_id,
            "status": "canceled"
        }
        webhook_response = client.post(
            "/api/v1/webhooks/payment",
            json=webhook_data
        )

        assert webhook_response.status_code == 200
        data = webhook_response.json()
        assert data["received"] is True
        assert data["processed"] is False  # Canceled = not processed successfully

        # Check balance unchanged
        balance_after = client.get("/api/v1/currency/balance", headers=headers).json()["balance"]
        assert Decimal(balance_after) == Decimal(balance_before)

    def test_webhook_mock_payment_page(self, client: TestClient, authenticated_user):
        """Test GET /api/v1/webhooks/mock-payment (mock payment completion page)"""
        headers, user = authenticated_user

        # Create payment
        purchase_response = client.post(
            "/api/v1/currency/purchase",
            json={"amount_znc": 30.00, "return_url": "https://example.com"},
            headers=headers
        )
        payment_id = purchase_response.json()["payment_id"]

        # Access mock payment page
        response = client.get(f"/api/v1/webhooks/mock-payment?payment_id={payment_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert payment_id in data["message"]
        assert data["payment_id"] == payment_id

        # Verify balance increased
        balance_response = client.get("/api/v1/currency/balance", headers=headers)
        assert Decimal(balance_response.json()["balance"]) == Decimal("30.00")
