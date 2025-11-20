"""
Edge case tests for TokenService

Tests critical boundary conditions:
- Security: Token revoke by different user
- Concurrency: Simultaneous token purchase
"""
import pytest
from decimal import Decimal
from sqlalchemy.orm import Session

from app.services.token_service import TokenService
from app.models.user import User


class TestTokenServiceEdgeCases:
    """Edge case tests for TokenService"""

    @pytest.fixture
    def user_a(self, test_db: Session) -> User:
        """Create first test user with balance"""
        user = User(
            email="user_a@test.com",
            username="user_a",
            hashed_password="hashed",
            full_name="User A",
            currency_balance=Decimal("100.00"),
            referral_code="USERA123"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user

    @pytest.fixture
    def user_b(self, test_db: Session) -> User:
        """Create second test user"""
        user = User(
            email="user_b@test.com",
            username="user_b",
            hashed_password="hashed",
            full_name="User B",
            currency_balance=Decimal("100.00"),
            referral_code="USERB456"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user

    def test_revoke_token_from_different_user(
        self, test_db: Session, user_a: User, user_b: User
    ):
        """
        SECURITY TEST: User A cannot revoke User B's token

        Expected: Raises ValueError (token not found)
        """
        # User A creates token
        token, cost = TokenService.generate_access_token(
            user_id=str(user_a.id),
            duration_hours=24,
            scope="full",
            db=test_db
        )

        # User B tries to revoke User A's token
        # Should raise ValueError because token doesn't belong to user_b
        with pytest.raises(ValueError, match="Token not found or already revoked"):
            TokenService.revoke_token(
                token_id=token.id,
                user_id=user_b.id,  # Different user!
                db=test_db
            )

        # Token should still be active
        test_db.refresh(token)
        assert token.is_active is True
        assert token.revoked_at is None

    def test_concurrent_token_purchase_insufficient_balance(
        self, test_db: Session, user_a: User
    ):
        """
        RACE CONDITION TEST: Two simultaneous purchases with balance for only one

        Expected: One succeeds, one fails with insufficient balance
        """
        # Set balance to exactly 18 ZNC (enough for one 24h token)
        user_a.currency_balance = Decimal("18.00")
        test_db.commit()

        # First purchase should succeed
        token1, cost1 = TokenService.generate_access_token(
            user_id=str(user_a.id),
            duration_hours=24,
            scope="full",
            db=test_db
        )
        assert token1 is not None

        # Refresh balance
        test_db.refresh(user_a)
        assert user_a.currency_balance == Decimal("0.00")

        # Second purchase should fail (insufficient balance)
        with pytest.raises(ValueError, match="Insufficient balance"):
            TokenService.generate_access_token(
                user_id=str(user_a.id),
                duration_hours=24,
                scope="full",
                db=test_db
            )
