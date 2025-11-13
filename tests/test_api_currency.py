"""
Integration tests for Currency API endpoints (app/api/v1/currency.py)
"""
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.services.currency_service import CurrencyService
from app.services.token_service import TokenService


@pytest.fixture
def authenticated_user_with_balance(client: TestClient, test_user_data: dict, test_db: Session):
    """Create authenticated user with JWT token and 500 ZNC balance"""
    # Register user
    client.post("/api/v1/auth/register", json=test_user_data)

    # Fund balance
    user = test_db.query(User).filter(User.email == test_user_data["email"]).first()
    CurrencyService.credit_balance(
        user_id=user.id,
        amount=Decimal("500.00"),
        description="Test initial balance",
        payment_id="TEST_INIT",
        db=test_db
    )

    # Login
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": test_user_data["email"], "password": test_user_data["password"]}
    )
    jwt_token = login_response.json()["access_token"]

    return {"Authorization": f"Bearer {jwt_token}"}, user


class TestGetBalanceEndpoint:
    """Tests for GET /api/v1/currency/balance"""

    def test_get_balance_success(
        self, client: TestClient, authenticated_user_with_balance
    ):
        """Test getting balance for authenticated user"""
        headers, user = authenticated_user_with_balance

        response = client.get("/api/v1/currency/balance", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["balance"] == "500.00"
        assert data["currency"] == "ZNC"

    def test_get_balance_unauthorized(self, client: TestClient):
        """Test getting balance without authentication"""
        response = client.get("/api/v1/currency/balance")

        assert response.status_code == 403  # HTTPBearer returns 403 when no auth provided


class TestGetTransactionsEndpoint:
    """Tests for GET /api/v1/currency/transactions"""

    def test_get_transactions_default(
        self, client: TestClient, authenticated_user_with_balance, test_db: Session
    ):
        """Test getting transactions with default pagination"""
        headers, user = authenticated_user_with_balance

        response = client.get("/api/v1/currency/transactions", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert data["total"] == 1  # Initial deposit
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert len(data["items"]) == 1

    def test_get_transactions_pagination(
        self, client: TestClient, authenticated_user_with_balance, test_db: Session
    ):
        """Test pagination parameters"""
        headers, user = authenticated_user_with_balance

        # Create additional transactions
        for i in range(15):
            CurrencyService.credit_balance(
                user_id=user.id,
                amount=Decimal("10.00"),
                description=f"Test transaction {i}",
                payment_id=f"TEST_{i}",
                db=test_db
            )

        # Test first page
        response = client.get("/api/v1/currency/transactions?limit=5&offset=0", headers=headers)
        data = response.json()
        assert data["total"] == 16  # 1 initial + 15 new
        assert len(data["items"]) == 5

        # Test second page
        response = client.get("/api/v1/currency/transactions?limit=5&offset=5", headers=headers)
        data = response.json()
        assert len(data["items"]) == 5

    def test_get_transactions_filtering_by_type(
        self, client: TestClient, authenticated_user_with_balance, test_db: Session
    ):
        """Test filtering by transaction type"""
        headers, user = authenticated_user_with_balance

        # Create a purchase transaction
        TokenService.generate_access_token(
            user_id=str(user.id),
            duration_hours=1,
            scope="full",
            db=test_db
        )

        # Get all transactions
        response = client.get("/api/v1/currency/transactions", headers=headers)
        assert response.json()["total"] == 2  # 1 deposit + 1 purchase

        # Get only deposits
        response = client.get(
            "/api/v1/currency/transactions?transaction_type=deposit",
            headers=headers
        )
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["transaction_type"] == "deposit"

        # Get only purchases
        response = client.get(
            "/api/v1/currency/transactions?transaction_type=purchase",
            headers=headers
        )
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["transaction_type"] == "purchase"

    def test_get_transactions_unauthorized(self, client: TestClient):
        """Test getting transactions without authentication"""
        response = client.get("/api/v1/currency/transactions")
        assert response.status_code == 403  # HTTPBearer returns 403 when no auth provided


class TestMockPurchaseEndpoint:
    """Tests for POST /api/v1/currency/mock-purchase"""

    def test_mock_purchase_success(
        self, client: TestClient, authenticated_user_with_balance
    ):
        """Test successful mock balance purchase"""
        headers, user = authenticated_user_with_balance

        purchase_data = {"amount": 100}
        response = client.post(
            "/api/v1/currency/mock-purchase",
            json=purchase_data,
            headers=headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert Decimal(data["amount"]) == Decimal("100")
        assert Decimal(data["new_balance"]) == Decimal("600")  # 500 + 100
        assert "Successfully added" in data["message"]

    def test_mock_purchase_invalid_amount(
        self, client: TestClient, authenticated_user_with_balance
    ):
        """Test mock purchase with invalid amount"""
        headers, user = authenticated_user_with_balance

        # Test negative amount (Pydantic validation)
        response = client.post(
            "/api/v1/currency/mock-purchase",
            json={"amount": -50},
            headers=headers
        )
        assert response.status_code == 422  # Pydantic validation error (gt=0 constraint)

        # Test zero amount (Pydantic validation)
        response = client.post(
            "/api/v1/currency/mock-purchase",
            json={"amount": 0},
            headers=headers
        )
        assert response.status_code == 422  # Pydantic validation error (gt=0 constraint)

    def test_mock_purchase_unauthorized(self, client: TestClient):
        """Test mock purchase without authentication"""
        response = client.post(
            "/api/v1/currency/mock-purchase",
            json={"amount": 100}
        )
        assert response.status_code == 403  # HTTPBearer returns 403 when no auth provided


class TestRevokeTokenEndpoint:
    """Tests for DELETE /api/v1/tokens/{token_id}"""

    def test_revoke_token_full_refund(
        self, client: TestClient, authenticated_user_with_balance, test_db: Session
    ):
        """Test revoking non-activated token (full refund)"""
        headers, user = authenticated_user_with_balance

        # Purchase token
        purchase_response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24},
            headers=headers
        )
        token_id = purchase_response.json()["id"]

        # Check balance after purchase
        balance_response = client.get("/api/v1/currency/balance", headers=headers)
        assert balance_response.json()["balance"] == "482.00"  # 500 - 18

        # Revoke token
        revoke_response = client.delete(
            f"/api/v1/tokens/{token_id}",
            headers=headers
        )

        assert revoke_response.status_code == 200
        data = revoke_response.json()
        assert data["revoked"] is True
        assert data["refund_amount"] == "18.00"  # Full refund
        assert data["new_balance"] == "500.00"  # Back to original
        assert "Token revoked" in data["message"]

    def test_revoke_token_not_found(
        self, client: TestClient, authenticated_user_with_balance
    ):
        """Test revoking non-existent token"""
        import uuid
        headers, user = authenticated_user_with_balance

        fake_token_id = str(uuid.uuid4())
        response = client.delete(
            f"/api/v1/tokens/{fake_token_id}",
            headers=headers
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_revoke_token_unauthorized(self, client: TestClient):
        """Test revoking token without authentication"""
        import uuid

        fake_token_id = str(uuid.uuid4())
        response = client.delete(f"/api/v1/tokens/{fake_token_id}")

        assert response.status_code == 403  # HTTPBearer returns 403 when no auth provided


class TestCurrencyAPIIntegration:
    """Integration tests for full currency workflow"""

    def test_full_currency_workflow(
        self, client: TestClient, test_user_data: dict, test_db: Session
    ):
        """Test complete workflow: register -> mock purchase -> buy token -> revoke -> check transactions"""
        # Step 1: Register and login
        client.post("/api/v1/auth/register", json=test_user_data)
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": test_user_data["email"], "password": test_user_data["password"]}
        )
        headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        # Step 2: Check initial balance (should be 0)
        balance_response = client.get("/api/v1/currency/balance", headers=headers)
        assert balance_response.json()["balance"] == "0.00"

        # Step 3: Mock purchase 100 ZNC
        purchase_response = client.post(
            "/api/v1/currency/mock-purchase",
            json={"amount": 100},
            headers=headers
        )
        assert purchase_response.json()["new_balance"] == "100.00"

        # Step 4: Buy 24h token (costs 18 ZNC)
        token_response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24},
            headers=headers
        )
        assert token_response.status_code == 201
        token_id = token_response.json()["id"]

        # Step 5: Check balance after purchase
        balance_response = client.get("/api/v1/currency/balance", headers=headers)
        assert balance_response.json()["balance"] == "82.00"  # 100 - 18

        # Step 6: Revoke token (full refund)
        revoke_response = client.delete(f"/api/v1/tokens/{token_id}", headers=headers)
        assert revoke_response.json()["new_balance"] == "100.00"

        # Step 7: Check transaction history
        transactions_response = client.get("/api/v1/currency/transactions", headers=headers)
        data = transactions_response.json()
        assert data["total"] == 3  # 1 deposit + 1 purchase + 1 refund

        # Verify transaction types
        transaction_types = [t["transaction_type"] for t in data["items"]]
        assert "deposit" in transaction_types
        assert "purchase" in transaction_types
        assert "refund" in transaction_types
