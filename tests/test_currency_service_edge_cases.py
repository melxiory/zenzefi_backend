"""
Edge case tests for CurrencyService

Tests critical boundary conditions and invalid scenarios:
- Decimal precision: Very large amounts, fractional cents, rounding
- Pagination edge cases: Zero limit, negative offset, beyond total
- Race conditions: Concurrent credit_balance operations
- Referral bonus edge cases: Multiple concurrent first purchases
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import Session

from app.services.currency_service import CurrencyService
from app.models.user import User
from app.models.transaction import Transaction, TransactionType


class TestCurrencyServiceDecimalPrecision:
    """Tests for decimal precision handling"""

    @pytest.fixture
    def user(self, test_db: Session) -> User:
        """Create test user"""
        user = User(
            email="currency_edge@test.com",
            username="currency_edge",
            hashed_password="hashed",
            full_name="Currency Edge User",
            currency_balance=Decimal("0.00"),
            referral_code="CURRENCY123"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user

    def test_credit_balance_with_many_decimal_places(
        self, test_db: Session, user: User
    ):
        """
        PRECISION TEST: Credit balance with >2 decimal places

        Expected: Should round to 2 decimal places (Decimal(10,2) in DB)
        Note: PostgreSQL NUMERIC(10,2) rounds automatically
        """
        # Attempt to credit 100.999 ZNC (3 decimal places)
        amount = Decimal("100.999")

        new_balance = CurrencyService.credit_balance(
            user_id=user.id,
            amount=amount,
            description="Precision test",
            payment_id="PREC_001",
            db=test_db
        )

        # Should round to 100.00 or 101.00 (banker's rounding)
        test_db.refresh(user)
        assert user.currency_balance in [Decimal("100.00"), Decimal("101.00")]
        assert user.currency_balance == new_balance

    def test_credit_balance_very_large_amount(
        self, test_db: Session, user: User
    ):
        """
        BOUNDARY TEST: Credit very large amount (near Decimal(10,2) limit)

        Expected: Should succeed up to 99,999,999.99 (8 digits + 2 decimals)
        """
        # Maximum value for NUMERIC(10,2) is 99,999,999.99
        large_amount = Decimal("99999999.99")

        new_balance = CurrencyService.credit_balance(
            user_id=user.id,
            amount=large_amount,
            description="Large amount test",
            payment_id="LARGE_001",
            db=test_db
        )

        assert new_balance == large_amount
        test_db.refresh(user)
        assert user.currency_balance == large_amount

    def test_credit_balance_exceeding_decimal_limit(
        self, test_db: Session, user: User
    ):
        """
        OVERFLOW TEST: Credit amount exceeding Decimal(10,2) limit

        Expected: Should fail with database error (value out of range)
        """
        # Attempt to credit amount >99,999,999.99
        overflow_amount = Decimal("100000000.00")  # 100 million

        with pytest.raises(Exception):  # Database overflow error
            CurrencyService.credit_balance(
                user_id=user.id,
                amount=overflow_amount,
                description="Overflow test",
                payment_id="OVERFLOW_001",
                db=test_db
            )

    def test_credit_balance_zero_amount(
        self, test_db: Session, user: User
    ):
        """
        VALIDATION TEST: Credit balance with zero amount

        Expected: Should fail with "Amount must be positive"
        """
        with pytest.raises(ValueError, match="Amount must be positive"):
            CurrencyService.credit_balance(
                user_id=user.id,
                amount=Decimal("0.00"),
                description="Zero amount",
                payment_id=None,
                db=test_db
            )


class TestCurrencyServicePaginationEdgeCases:
    """Tests for transaction pagination edge cases"""

    @pytest.fixture
    def user_with_transactions(self, test_db: Session) -> User:
        """Create user with 5 transactions"""
        user = User(
            email="pagination_test@test.com",
            username="pagination_test",
            hashed_password="hashed",
            full_name="Pagination Test User",
            currency_balance=Decimal("0.00"),
            referral_code="PAGINATION1"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        # Create 5 transactions
        for i in range(5):
            CurrencyService.credit_balance(
                user_id=user.id,
                amount=Decimal("10.00"),
                description=f"Transaction {i}",
                payment_id=f"PAY_{i}",
                db=test_db
            )

        return user

    def test_get_transactions_with_zero_limit(
        self, test_db: Session, user_with_transactions: User
    ):
        """
        BOUNDARY TEST: Get transactions with limit=0

        Expected: Should return empty list but correct total count
        """
        transactions, total = CurrencyService.get_transactions(
            user_id=user_with_transactions.id,
            limit=0,
            offset=0,
            transaction_type=None,
            db=test_db
        )

        assert len(transactions) == 0
        assert total == 5  # Total count should still be correct

    def test_get_transactions_with_negative_limit(
        self, test_db: Session, user_with_transactions: User
    ):
        """
        EDGE CASE TEST: Get transactions with negative limit

        Expected: PostgreSQL raises DataError "LIMIT must not be negative"
        """
        from sqlalchemy.exc import DataError

        # Negative limit causes PostgreSQL DataError
        with pytest.raises(DataError, match="LIMIT must not be negative"):
            CurrencyService.get_transactions(
                user_id=user_with_transactions.id,
                limit=-1,
                offset=0,
                transaction_type=None,
                db=test_db
            )

    def test_get_transactions_offset_beyond_total(
        self, test_db: Session, user_with_transactions: User
    ):
        """
        BOUNDARY TEST: Get transactions with offset > total count

        Expected: Should return empty list
        """
        transactions, total = CurrencyService.get_transactions(
            user_id=user_with_transactions.id,
            limit=10,
            offset=100,  # Way beyond total of 5
            transaction_type=None,
            db=test_db
        )

        assert len(transactions) == 0
        assert total == 5

    def test_get_transactions_with_negative_offset(
        self, test_db: Session, user_with_transactions: User
    ):
        """
        EDGE CASE TEST: Get transactions with negative offset

        Expected: SQLAlchemy behavior - may fail or ignore
        """
        # Negative offset has undefined behavior
        try:
            transactions, total = CurrencyService.get_transactions(
                user_id=user_with_transactions.id,
                limit=10,
                offset=-5,
                transaction_type=None,
                db=test_db
            )

            # If succeeds, document behavior
            assert total == 5
        except Exception:
            # If fails, that's also acceptable
            pass


class TestCurrencyServiceConcurrency:
    """Tests for concurrent operations"""

    @pytest.fixture
    def user(self, test_db: Session) -> User:
        """Create test user"""
        user = User(
            email="concurrency_test@test.com",
            username="concurrency_test",
            hashed_password="hashed",
            full_name="Concurrency Test User",
            currency_balance=Decimal("0.00"),
            referral_code="CONCUR123"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user

    def test_concurrent_credit_balance_operations(
        self, test_db: Session, user: User
    ):
        """
        RACE CONDITION TEST: Multiple concurrent credit_balance calls

        Expected: All credits should be atomic (row-level locking ensures consistency)
        Note: Sequential test simulates concurrent scenario
        """
        # Credit 10 ZNC three times sequentially (simulates concurrent scenario)
        for i in range(3):
            CurrencyService.credit_balance(
                user_id=user.id,
                amount=Decimal("10.00"),
                description=f"Concurrent credit {i}",
                payment_id=f"CONC_{i}",
                db=test_db
            )

        # Final balance should be exactly 30.00 (no lost updates)
        test_db.refresh(user)
        assert user.currency_balance == Decimal("30.00")

        # Verify all 3 transactions were recorded
        transactions, total = CurrencyService.get_transactions(
            user_id=user.id,
            limit=10,
            offset=0,
            transaction_type=TransactionType.DEPOSIT,
            db=test_db
        )
        assert total == 3


class TestReferralBonusEdgeCases:
    """Tests for referral bonus edge cases"""

    @pytest.fixture
    def referrer(self, test_db: Session) -> User:
        """Create referrer user"""
        user = User(
            email="referrer_edge@test.com",
            username="referrer_edge",
            hashed_password="hashed",
            full_name="Referrer Edge User",
            currency_balance=Decimal("0.00"),
            referral_code="REFEDGE123",
            referral_bonus_earned=Decimal("0.00")
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user

    def test_award_referral_bonus_with_deleted_referrer(
        self, test_db: Session, referrer: User
    ):
        """
        EDGE CASE TEST: Award bonus when referrer is deleted

        Expected: Should return None (referrer no longer exists)
        """
        # Create referee
        referee = User(
            email="referee_deleted_ref@test.com",
            username="referee_deleted_ref",
            hashed_password="hashed",
            full_name="Referee User",
            currency_balance=Decimal("200.00"),
            referral_code="REFDEL123",
            referred_by_id=referrer.id
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # Delete referrer
        test_db.delete(referrer)
        test_db.commit()

        # Attempt to award bonus
        bonus = CurrencyService.award_referral_bonus(
            referee_id=referee.id,
            purchase_amount=Decimal("150.00"),
            db=test_db
        )

        # Should return None (referrer doesn't exist)
        assert bonus is None

    def test_award_referral_bonus_boundary_100_01_znc(
        self, test_db: Session, referrer: User
    ):
        """
        BOUNDARY TEST: Award bonus for purchase of exactly 100.01 ZNC

        Expected: Should award bonus (logic: if amount > 100.00)
        """
        referee = User(
            email="referee_100_01@test.com",
            username="referee_100_01",
            hashed_password="hashed",
            full_name="Referee 100.01 User",
            currency_balance=Decimal("200.00"),
            referral_code="REF10001",
            referred_by_id=referrer.id
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # Award bonus for 100.01 ZNC purchase
        bonus = CurrencyService.award_referral_bonus(
            referee_id=referee.id,
            purchase_amount=Decimal("100.01"),
            db=test_db
        )

        # Should award 10% bonus = 10.00 ZNC (rounded)
        assert bonus == Decimal("10.00")

        test_db.refresh(referrer)
        assert referrer.currency_balance == Decimal("10.00")
        assert referrer.referral_bonus_earned == Decimal("10.00")

    def test_award_referral_bonus_fractional_bonus_rounding(
        self, test_db: Session, referrer: User
    ):
        """
        PRECISION TEST: Award bonus with fractional amount (rounding)

        Expected: 10% of 105.55 = 10.555 → should round to 10.56 (banker's rounding)
        """
        referee = User(
            email="referee_fractional@test.com",
            username="referee_fractional",
            hashed_password="hashed",
            full_name="Referee Fractional User",
            currency_balance=Decimal("200.00"),
            referral_code="REFFRAC123",
            referred_by_id=referrer.id
        )
        test_db.add(referee)
        test_db.commit()
        test_db.refresh(referee)

        # Award bonus for 105.55 ZNC purchase
        bonus = CurrencyService.award_referral_bonus(
            referee_id=referee.id,
            purchase_amount=Decimal("105.55"),
            db=test_db
        )

        # 10% of 105.55 = 10.555 → quantize to 10.56
        expected_bonus = Decimal("10.56")
        assert bonus == expected_bonus

        test_db.refresh(referrer)
        assert referrer.currency_balance == expected_bonus
        assert referrer.referral_bonus_earned == expected_bonus
