"""
Edge case tests for Referral System

Tests critical boundary conditions:
- Security: Self-referral prevention
- Business logic: Referral bonus at 100 ZNC boundary
"""
import pytest
from decimal import Decimal
from sqlalchemy.orm import Session

from app.services.currency_service import CurrencyService
from app.models.user import User


class TestReferralSystemEdgeCases:
    """Edge case tests for Referral System"""

    @pytest.fixture
    def referrer(self, test_db: Session) -> User:
        """Create referrer user"""
        user = User(
            email="referrer@test.com",
            username="referrer",
            hashed_password="hashed",
            full_name="Referrer User",
            currency_balance=Decimal("0.00"),
            referral_code="REFERRER123"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user

    def test_register_with_own_referral_code(
        self, test_db: Session
    ):
        """
        SECURITY TEST: User cannot use their own referral code

        Expected: Registration should fail or ignore self-referral
        Note: Currently no validation - documents potential exploit
        """
        # Create user
        user = User(
            email="selfreferral@test.com",
            username="selfreferral",
            hashed_password="hashed",
            full_name="Self Referral User",
            currency_balance=Decimal("0.00"),
            referral_code="SELFREF123"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        # Set referred_by_id to own id (self-referral)
        user.referred_by_id = user.id
        test_db.commit()

        # BUG: This should fail with constraint, but currently allowed!
        test_db.refresh(user)
        assert user.referred_by_id == user.id  # Self-referral allowed!

    def test_referral_bonus_exactly_100_znc(
        self, test_db: Session, referrer: User
    ):
        """
        BOUNDARY TEST: Referral bonus for purchase of exactly 100.00 ZNC

        Expected: Should NOT award bonus (logic: if amount <= 100.00)
        """
        # Create referee
        referee = User(
            email="referee_100@test.com",
            username="referee_100",
            hashed_password="hashed",
            full_name="Referee 100 ZNC",
            currency_balance=Decimal("100.00"),
            referral_code="REFEREE100",
            referred_by_id=referrer.id
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # Purchase exactly 100.00 ZNC (boundary)
        awarded = CurrencyService.award_referral_bonus(
            referee_id=referee.id,
            purchase_amount=Decimal("100.00"),
            db=test_db
        )

        # Should NOT award bonus (amount <= 100.00)
        assert awarded is None

        # Referrer should have no bonus
        test_db.refresh(referrer)
        assert referrer.currency_balance == Decimal("0.00")

    def test_referral_bonus_exactly_100_01_znc(
        self, test_db: Session, referrer: User
    ):
        """
        BOUNDARY TEST: Referral bonus for purchase of exactly 100.01 ZNC

        Expected: SHOULD award bonus (logic: if amount > 100.00)
        """
        # Create referee
        referee = User(
            email="referee_10001@test.com",
            username="referee_10001",
            hashed_password="hashed",
            full_name="Referee 100.01 ZNC",
            currency_balance=Decimal("100.01"),
            referral_code="REFEREE10001",
            referred_by_id=referrer.id
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # Purchase 100.01 ZNC (just over boundary)
        awarded = CurrencyService.award_referral_bonus(
            referee_id=referee.id,
            purchase_amount=Decimal("100.01"),
            db=test_db
        )

        # Should award bonus (amount > 100.00)
        assert awarded is not None
        assert awarded == Decimal("10.00")  # 10% of 100.01 = 10.001 → 10.00

        # Referrer should receive bonus
        test_db.refresh(referrer)
        assert referrer.currency_balance == Decimal("10.00")
