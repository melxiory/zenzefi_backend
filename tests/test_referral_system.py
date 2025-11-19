"""
Tests for Referral System (Phase 5).

Tests:
- Referral code generation and uniqueness
- User registration with referral code
- Referral bonus award logic
- Referral stats API endpoint
- Integration with token/bundle purchases
"""
import pytest
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException

from app.models.user import User
from app.models.transaction import Transaction, TransactionType
from app.services.auth_service import AuthService
from app.services.currency_service import CurrencyService
from app.schemas.user import UserCreate


class TestReferralCodeGeneration:
    """Tests for referral code generation."""

    def test_generate_unique_referral_code(self, test_db):
        """Test generating unique 12-character referral code."""
        code = AuthService.generate_referral_code(test_db)

        assert len(code) == 12
        assert code.isalnum()  # Only letters and digits
        assert code.isupper()  # Uppercase only

    def test_referral_code_uniqueness(self, test_db, test_user):
        """Test that generated codes are unique."""
        # test_user already has a referral_code
        existing_code = test_user.referral_code

        # Generate new code
        new_code = AuthService.generate_referral_code(test_db)

        # Should be different
        assert new_code != existing_code

    def test_referral_code_collision_handling(self, test_db, test_user, monkeypatch):
        """Test that collision handling works (generates different code on collision)."""
        # Mock secrets.choice to return same value first time, different second time
        call_count = [0]
        original_code = test_user.referral_code

        def mock_choice(seq):
            call_count[0] += 1
            if call_count[0] <= 12:  # First 12 calls = first code (collision)
                return original_code[call_count[0] - 1]
            else:  # After that, return different chars
                return 'Z'

        import secrets
        monkeypatch.setattr(secrets, 'choice', mock_choice)

        # Should detect collision and retry
        new_code = AuthService.generate_referral_code(test_db)
        assert new_code != original_code
        assert new_code == 'Z' * 12


class TestRegistrationWithReferralCode:
    """Tests for user registration with referral code."""

    def test_register_with_valid_referral_code(self, test_db, test_user):
        """Test successful registration with valid referral code."""
        referrer_code = test_user.referral_code

        # Register new user with referral code
        new_user_data = UserCreate(
            email="newuser@example.com",
            username="newuser",
            password="Password123!",
            full_name="New User"
        )

        new_user = AuthService.register_user(new_user_data, test_db, referral_code=referrer_code)

        assert new_user.referred_by_id == test_user.id
        assert new_user.referral_code is not None
        assert new_user.referral_code != referrer_code  # Has own unique code
        assert new_user.referral_bonus_earned == Decimal("0.00")

    def test_register_with_invalid_referral_code(self, test_db):
        """Test registration with invalid referral code fails."""
        new_user_data = UserCreate(
            email="newuser@example.com",
            username="newuser",
            password="Password123!",
            full_name="New User"
        )

        with pytest.raises(ValueError) as exc_info:
            AuthService.register_user(new_user_data, test_db, referral_code="INVALIDCODE1")

        assert "Invalid referral code" in str(exc_info.value)

    def test_register_without_referral_code(self, test_db):
        """Test registration without referral code (should succeed)."""
        new_user_data = UserCreate(
            email="newuser@example.com",
            username="newuser",
            password="Password123!",
            full_name="New User"
        )

        new_user = AuthService.register_user(new_user_data, test_db, referral_code=None)

        assert new_user.referred_by_id is None
        assert new_user.referral_code is not None  # Still gets own code
        assert new_user.referral_bonus_earned == Decimal("0.00")


class TestReferralBonusAward:
    """Tests for referral bonus award logic."""

    def test_award_bonus_on_first_qualifying_purchase(self, test_db, test_user):
        """Test bonus awarded on first purchase >100 ZNC."""
        # Create referee (referred by test_user)
        referee = User(
            email="referee@example.com",
            username="referee",
            hashed_password="hashed",
            referral_code=AuthService.generate_referral_code(test_db),
            referred_by_id=test_user.id,
            currency_balance=Decimal("200.00")
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # Create purchase transaction (150 ZNC)
        purchase_amount = Decimal("150.00")
        transaction = Transaction(
            user_id=referee.id,
            amount=-purchase_amount,  # Negative for purchase
            transaction_type=TransactionType.PURCHASE,
            description="Token purchase: 24h (full)"
        )
        test_db.add(transaction)
        test_db.commit()

        # Award referral bonus
        bonus = CurrencyService.award_referral_bonus(
            referee_id=referee.id,
            purchase_amount=purchase_amount,
            db=test_db
        )

        # Verify bonus awarded
        assert bonus == Decimal("15.00")  # 10% of 150

        # Verify referrer balance updated
        test_db.refresh(test_user)
        assert test_user.currency_balance == Decimal("15.00")
        assert test_user.referral_bonus_earned == Decimal("15.00")

        # Verify transaction created
        bonus_transaction = test_db.query(Transaction).filter(
            Transaction.user_id == test_user.id,
            Transaction.transaction_type == TransactionType.REFERRAL_BONUS
        ).first()

        assert bonus_transaction is not None
        assert bonus_transaction.amount == Decimal("15.00")
        assert "referee" in bonus_transaction.description

    def test_no_bonus_on_small_purchase(self, test_db, test_user):
        """Test no bonus for purchase <=100 ZNC."""
        # Create referee
        referee = User(
            email="referee@example.com",
            username="referee",
            hashed_password="hashed",
            referral_code=AuthService.generate_referral_code(test_db),
            referred_by_id=test_user.id,
            currency_balance=Decimal("100.00")
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # Small purchase (50 ZNC)
        bonus = CurrencyService.award_referral_bonus(
            referee_id=referee.id,
            purchase_amount=Decimal("50.00"),
            db=test_db
        )

        assert bonus is None

        # Verify no changes to referrer
        test_db.refresh(test_user)
        assert test_user.currency_balance == Decimal("0.00")
        assert test_user.referral_bonus_earned == Decimal("0.00")

    def test_no_bonus_on_second_purchase(self, test_db, test_user):
        """Test no bonus on second qualifying purchase (only first counts)."""
        # Create referee
        referee = User(
            email="referee@example.com",
            username="referee",
            hashed_password="hashed",
            referral_code=AuthService.generate_referral_code(test_db),
            referred_by_id=test_user.id,
            currency_balance=Decimal("500.00")
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # First purchase (150 ZNC)
        transaction1 = Transaction(
            user_id=referee.id,
            amount=Decimal("-150.00"),
            transaction_type=TransactionType.PURCHASE,
            description="Token purchase: 24h (full)"
        )
        test_db.add(transaction1)
        test_db.commit()

        # Award first bonus
        bonus1 = CurrencyService.award_referral_bonus(
            referee_id=referee.id,
            purchase_amount=Decimal("150.00"),
            db=test_db
        )
        assert bonus1 == Decimal("15.00")

        # Second purchase (200 ZNC)
        transaction2 = Transaction(
            user_id=referee.id,
            amount=Decimal("-200.00"),
            transaction_type=TransactionType.PURCHASE,
            description="Token purchase: 7d (full)"
        )
        test_db.add(transaction2)
        test_db.commit()

        # Try to award second bonus
        bonus2 = CurrencyService.award_referral_bonus(
            referee_id=referee.id,
            purchase_amount=Decimal("200.00"),
            db=test_db
        )

        assert bonus2 is None  # No bonus on second purchase

        # Verify referrer balance unchanged from first bonus
        test_db.refresh(test_user)
        assert test_user.referral_bonus_earned == Decimal("15.00")

    def test_no_bonus_if_user_not_referred(self, test_db):
        """Test no bonus if user was not referred by anyone."""
        # Create user WITHOUT referrer
        user = User(
            email="user@example.com",
            username="user",
            hashed_password="hashed",
            referral_code=AuthService.generate_referral_code(test_db),
            referred_by_id=None,  # No referrer
            currency_balance=Decimal("200.00")
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        # Try to award bonus
        bonus = CurrencyService.award_referral_bonus(
            referee_id=user.id,
            purchase_amount=Decimal("150.00"),
            db=test_db
        )

        assert bonus is None


class TestReferralStatsAPI:
    """Tests for referral stats API endpoint."""

    def test_get_referral_stats_no_referrals(self, client, test_user):
        """Test getting stats when user has no referrals."""
        from app.core.security import create_access_token

        token = create_access_token(data={"sub": str(test_user.id), "username": test_user.username})

        response = client.get(
            "/api/v1/users/me/referrals",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["referral_code"] == test_user.referral_code
        assert data["total_referrals"] == 0
        assert data["qualifying_referrals"] == 0
        assert data["total_bonus_earned"] == 0.0
        assert test_user.referral_code in data["referral_link"]
        assert len(data["referred_users"]) == 0

    def test_get_referral_stats_with_referrals(self, client, test_db, test_user):
        """Test getting stats with multiple referrals (some qualifying)."""
        from app.core.security import create_access_token

        # Create referee 1 (qualifying purchase)
        referee1 = User(
            email="referee1@example.com",
            username="referee1",
            hashed_password="hashed",
            referral_code=AuthService.generate_referral_code(test_db),
            referred_by_id=test_user.id,
            currency_balance=Decimal("0.00")
        )
        test_db.add(referee1)
        test_db.commit()
        test_db.refresh(referee1)

        # Add qualifying purchase for referee1
        transaction1 = Transaction(
            user_id=referee1.id,
            amount=Decimal("-150.00"),
            transaction_type=TransactionType.PURCHASE,
            description="Token purchase"
        )
        test_db.add(transaction1)

        # Create referee 2 (no purchase yet)
        referee2 = User(
            email="referee2@example.com",
            username="referee2",
            hashed_password="hashed",
            referral_code=AuthService.generate_referral_code(test_db),
            referred_by_id=test_user.id,
            currency_balance=Decimal("0.00")
        )
        test_db.add(referee2)
        test_db.commit()
        test_db.refresh(referee2)

        # Award bonus for referee1
        test_user.currency_balance = Decimal("15.00")
        test_user.referral_bonus_earned = Decimal("15.00")
        test_db.commit()

        token = create_access_token(data={"sub": str(test_user.id), "username": test_user.username})

        response = client.get(
            "/api/v1/users/me/referrals",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total_referrals"] == 2
        assert data["qualifying_referrals"] == 1  # Only referee1
        assert data["total_bonus_earned"] == 15.0
        assert len(data["referred_users"]) == 2

        # Check referred users info
        usernames = [u["username"] for u in data["referred_users"]]
        assert "referee1" in usernames
        assert "referee2" in usernames

        # Check qualifying status
        referee1_info = next(u for u in data["referred_users"] if u["username"] == "referee1")
        referee2_info = next(u for u in data["referred_users"] if u["username"] == "referee2")

        assert referee1_info["has_made_qualifying_purchase"] is True
        assert referee2_info["has_made_qualifying_purchase"] is False


class TestReferralIntegration:
    """Integration tests for referral system with token/bundle purchases."""

    def test_token_purchase_triggers_referral_bonus(self, test_db, test_user):
        """Test that token purchase automatically awards referral bonus."""
        from app.services.token_service import TokenService

        # Create referee with sufficient balance for 30d token (300 ZNC)
        referee = User(
            email="referee@example.com",
            username="referee",
            hashed_password="hashed",
            referral_code=AuthService.generate_referral_code(test_db),
            referred_by_id=test_user.id,
            currency_balance=Decimal("400.00")
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # Purchase token (cost: 300 ZNC for 30d, >100 ZNC to qualify for referral bonus)
        token, cost = TokenService.generate_access_token(
            user_id=str(referee.id),
            duration_hours=720,  # 30 days = 300 ZNC
            scope="full",
            db=test_db
        )

        # Verify bonus awarded to referrer
        test_db.refresh(test_user)
        assert test_user.currency_balance == Decimal("30.00")  # 10% of 300
        assert test_user.referral_bonus_earned == Decimal("30.00")

        # Verify transaction created
        bonus_transaction = test_db.query(Transaction).filter(
            Transaction.user_id == test_user.id,
            Transaction.transaction_type == TransactionType.REFERRAL_BONUS
        ).first()

        assert bonus_transaction is not None
        assert bonus_transaction.amount == Decimal("30.00")

    def test_bundle_purchase_triggers_referral_bonus(self, test_db, test_user):
        """Test that bundle purchase automatically awards referral bonus."""
        from app.services.bundle_service import BundleService
        from app.models.bundle import TokenBundle

        # Create bundle
        bundle = TokenBundle(
            name="Test Bundle",
            description="Test",
            token_count=10,
            duration_hours=24,
            scope="full",
            discount_percent=Decimal("15.00"),
            base_price=Decimal("180.00"),
            total_price=Decimal("153.00")
        )
        test_db.add(bundle)
        test_db.commit()
        test_db.refresh(bundle)

        # Create referee with balance
        referee = User(
            email="referee@example.com",
            username="referee",
            hashed_password="hashed",
            referral_code=AuthService.generate_referral_code(test_db),
            referred_by_id=test_user.id,
            currency_balance=Decimal("200.00")
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # Purchase bundle
        result = BundleService.purchase_bundle(
            bundle_id=bundle.id,
            user_id=referee.id,
            db=test_db
        )

        # Verify bonus awarded (10% of 153 = 15.30)
        test_db.refresh(test_user)
        assert test_user.currency_balance == Decimal("15.30")
        assert test_user.referral_bonus_earned == Decimal("15.30")
