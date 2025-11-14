"""
Tests for Admin API endpoints
"""
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient


class TestAdminUserEndpoints:
    """Tests for admin user management endpoints"""

    def test_list_users_requires_superuser(self, client: TestClient, test_user_with_balance):
        """Test that list users requires superuser permissions"""
        # Login as regular user
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user_with_balance.email,
                "password": "TestPass123!"
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Try to access admin endpoint
        response = client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403
        assert "Superuser permissions required" in response.json()["detail"]

    def test_list_users_as_superuser(self, client: TestClient, test_db):
        """Test listing users as superuser"""
        from app.models import User
        from app.core.security import get_password_hash

        # Create superuser
        superuser = User(
            email="admin@example.com",
            username="admin",
            hashed_password=get_password_hash("AdminPass123!"),
            is_active=True,
            is_superuser=True,
            currency_balance=Decimal("0.00")
        )
        test_db.add(superuser)
        test_db.commit()

        # Login as superuser
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "AdminPass123!"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # List users
        response = client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1  # At least the superuser

    def test_list_users_with_search(self, client: TestClient, test_db):
        """Test listing users with search filter"""
        from app.models import User
        from app.core.security import get_password_hash

        # Create superuser
        superuser = User(
            email="admin@example.com",
            username="admin",
            hashed_password=get_password_hash("AdminPass123!"),
            is_active=True,
            is_superuser=True,
            currency_balance=Decimal("0.00")
        )
        test_db.add(superuser)

        # Create test user
        test_user = User(
            email="testuser@example.com",
            username="testuser",
            hashed_password=get_password_hash("TestPass123!"),
            is_active=True,
            is_superuser=False,
            currency_balance=Decimal("0.00")
        )
        test_db.add(test_user)
        test_db.commit()

        # Login as superuser
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "AdminPass123!"}
        )
        token = login_response.json()["access_token"]

        # Search for "testuser"
        response = client.get(
            "/api/v1/admin/users?search=testuser",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["username"] == "testuser"

    def test_update_user_as_superuser(self, client: TestClient, test_db, test_user_with_balance):
        """Test updating user as superuser"""
        from app.models import User
        from app.core.security import get_password_hash

        # Create superuser
        superuser = User(
            email="admin@example.com",
            username="admin",
            hashed_password=get_password_hash("AdminPass123!"),
            is_active=True,
            is_superuser=True,
            currency_balance=Decimal("0.00")
        )
        test_db.add(superuser)
        test_db.commit()

        # Login as superuser
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "AdminPass123!"}
        )
        token = login_response.json()["access_token"]

        # Update test user
        response = client.patch(
            f"/api/v1/admin/users/{test_user_with_balance.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "is_active": False,
                "currency_balance": "500.00"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] == False
        assert Decimal(data["currency_balance"]) == Decimal("500.00")

        # Verify in database
        test_db.refresh(test_user_with_balance)
        assert test_user_with_balance.is_active == False
        assert test_user_with_balance.currency_balance == Decimal("500.00")


class TestAdminTokenEndpoints:
    """Tests for admin token management endpoints"""

    def test_list_tokens_requires_superuser(self, client: TestClient, test_user_with_balance):
        """Test that list tokens requires superuser permissions"""
        # Login as regular user
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user_with_balance.email,
                "password": "TestPass123!"
            }
        )
        token = login_response.json()["access_token"]

        # Try to access admin endpoint
        response = client.get(
            "/api/v1/admin/tokens",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    def test_list_tokens_as_superuser(self, client: TestClient, test_db, test_user_with_balance):
        """Test listing tokens as superuser"""
        from app.models import User
        from app.core.security import get_password_hash

        # Create superuser
        superuser = User(
            email="admin@example.com",
            username="admin",
            hashed_password=get_password_hash("AdminPass123!"),
            is_active=True,
            is_superuser=True,
            currency_balance=Decimal("0.00")
        )
        test_db.add(superuser)
        test_db.commit()

        # Login as superuser
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "AdminPass123!"}
        )
        token = login_response.json()["access_token"]

        # Purchase a token as test user (need to login first)
        test_user_login = client.post(
            "/api/v1/auth/login",
            json={"email": test_user_with_balance.email, "password": "TestPass123!"}
        )
        test_user_token = test_user_login.json()["access_token"]

        client.post(
            "/api/v1/tokens/purchase",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"duration_hours": 24, "scope": "full"}
        )

        # List tokens as admin
        response = client.get(
            "/api/v1/admin/tokens",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_force_revoke_token_as_superuser(self, client: TestClient, test_db, test_user_with_balance):
        """Test force revoking token as superuser (no refund)"""
        from app.models import User
        from app.core.security import get_password_hash

        # Create superuser
        superuser = User(
            email="admin@example.com",
            username="admin",
            hashed_password=get_password_hash("AdminPass123!"),
            is_active=True,
            is_superuser=True,
            currency_balance=Decimal("0.00")
        )
        test_db.add(superuser)
        test_db.commit()

        # Purchase token as test user
        test_user_login = client.post(
            "/api/v1/auth/login",
            json={"email": test_user_with_balance.email, "password": "TestPass123!"}
        )
        test_user_token = test_user_login.json()["access_token"]

        purchase_response = client.post(
            "/api/v1/tokens/purchase",
            headers={"Authorization": f"Bearer {test_user_token}"},
            json={"duration_hours": 24, "scope": "full"}
        )
        token_id = purchase_response.json()["id"]

        # Refresh to get balance after purchase
        test_db.refresh(test_user_with_balance)
        balance_after_purchase = test_user_with_balance.currency_balance

        # Login as superuser
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "AdminPass123!"}
        )
        admin_token = login_response.json()["access_token"]

        # Force revoke token (no refund)
        response = client.delete(
            f"/api/v1/admin/tokens/{token_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["revoked"] == True
        assert "no refund" in data["message"]

        # Verify balance unchanged (no refund)
        test_db.refresh(test_user_with_balance)
        assert test_user_with_balance.currency_balance == balance_after_purchase
