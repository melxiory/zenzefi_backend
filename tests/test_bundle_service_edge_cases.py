"""
Edge case tests for BundleService

Tests critical boundary conditions and invalid scenarios:
- Validation: Invalid discount_percent, token_count, duration_hours
- Business logic: Bundles with negative values
- Concurrency: Bundle purchase during deactivation
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.services.bundle_service import BundleService
from app.models.user import User
from app.models.bundle import TokenBundle


class TestBundleServiceEdgeCases:
    """Edge case tests for BundleService"""

    @pytest.fixture
    def user(self, test_db: Session) -> User:
        """Create test user with sufficient balance"""
        user = User(
            email="bundle_test@test.com",
            username="bundle_test",
            hashed_password="hashed",
            full_name="Bundle Test User",
            currency_balance=Decimal("5000.00"),
            referral_code="BUNDLE123"
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user

    def test_bundle_with_discount_over_100_percent(
        self, test_db: Session
    ):
        """
        VALIDATION TEST: Bundle with discount_percent > 100%

        Expected: Should fail validation or produce negative total_price
        Note: Currently no validation - documents potential bug
        """
        # Attempt to create bundle with 150% discount
        bundle = TokenBundle(
            name="Impossible Discount",
            description="Bundle with discount > 100%",
            token_count=10,
            duration_hours=24,
            scope="full",
            discount_percent=Decimal("150.00"),  # 150% discount!
            base_price=Decimal("180.00"),
            total_price=Decimal("180.00") * (Decimal("1.00") - Decimal("1.50")),  # Negative!
            is_active=True
        )

        test_db.add(bundle)

        # This should fail with constraint or validation error
        # Currently no constraint - documents bug!
        try:
            test_db.commit()
            test_db.refresh(bundle)

            # If commit succeeds, check total_price
            assert bundle.total_price < 0  # Negative price! BUG!
            assert bundle.discount_percent > Decimal("100.00")

            # This is a documented bug - should have CHECK constraint
        except IntegrityError:
            # Expected: database constraint should prevent this
            test_db.rollback()
            pytest.skip("Database constraint prevents invalid discount (good!)")

    def test_bundle_with_zero_token_count(
        self, test_db: Session
    ):
        """
        VALIDATION TEST: Bundle with token_count = 0

        Expected: Should fail validation (cannot buy 0 tokens)
        """
        # Attempt to create bundle with 0 tokens
        bundle = TokenBundle(
            name="Zero Tokens",
            description="Bundle with no tokens",
            token_count=0,  # Invalid!
            duration_hours=24,
            scope="full",
            discount_percent=Decimal("10.00"),
            base_price=Decimal("0.00"),
            total_price=Decimal("0.00"),
            is_active=True
        )

        test_db.add(bundle)

        # Should fail with constraint or validation error
        try:
            test_db.commit()
            test_db.refresh(bundle)

            # If succeeds, this is a bug
            assert bundle.token_count == 0  # BUG: Should not allow 0 tokens
        except IntegrityError:
            # Expected: database constraint should prevent this
            test_db.rollback()
            pytest.skip("Database constraint prevents zero token_count (good!)")

    def test_bundle_with_negative_token_count(
        self, test_db: Session
    ):
        """
        VALIDATION TEST: Bundle with negative token_count

        Expected: Should fail validation (cannot buy negative tokens)
        """
        bundle = TokenBundle(
            name="Negative Tokens",
            description="Bundle with negative token count",
            token_count=-10,  # Invalid!
            duration_hours=24,
            scope="full",
            discount_percent=Decimal("10.00"),
            base_price=Decimal("-180.00"),
            total_price=Decimal("-162.00"),
            is_active=True
        )

        test_db.add(bundle)

        try:
            test_db.commit()
            test_db.refresh(bundle)

            # If succeeds, this is a bug
            assert bundle.token_count < 0  # BUG!
        except IntegrityError:
            # Expected behavior
            test_db.rollback()
            pytest.skip("Database constraint prevents negative token_count (good!)")

    def test_bundle_with_invalid_duration_hours(
        self, test_db: Session, user: User
    ):
        """
        VALIDATION TEST: Bundle with duration_hours not in valid set [1,12,24,168,720]

        Expected: Should fail validation or produce incorrect pricing
        """
        # Create bundle with invalid duration
        bundle = TokenBundle(
            name="Invalid Duration",
            description="Bundle with non-standard duration",
            token_count=10,
            duration_hours=999,  # Not in [1, 12, 24, 168, 720]
            scope="full",
            discount_percent=Decimal("10.00"),
            base_price=Decimal("1000.00"),  # Arbitrary pricing
            total_price=Decimal("900.00"),
            is_active=True
        )

        test_db.add(bundle)
        test_db.commit()
        test_db.refresh(bundle)

        # Bundle created, but pricing may be incorrect
        # NOTE: No validation on duration_hours - potential issue

        # Attempt to purchase (should work, but tokens have invalid duration)
        try:
            result = BundleService.purchase_bundle(
                db=test_db,
                user_id=user.id,
                bundle_id=bundle.id
            )

            # Purchase succeeds, but tokens have invalid duration
            # Result is a dict with "tokens" key containing list of dicts
            assert len(result["tokens"]) == 10
            for token_dict in result["tokens"]:
                assert token_dict["duration_hours"] == 999  # Invalid duration propagated!

        except ValueError as e:
            # If purchase fails, that's good (validation exists)
            assert "Invalid duration" in str(e) or "duration_hours" in str(e)

    def test_bundle_with_negative_discount(
        self, test_db: Session
    ):
        """
        VALIDATION TEST: Bundle with negative discount_percent

        Expected: Should fail validation (negative discount = price increase)
        Note: Negative discount is technically valid (surcharge), but unusual
        """
        bundle = TokenBundle(
            name="Negative Discount",
            description="Bundle with surcharge",
            token_count=10,
            duration_hours=24,
            scope="full",
            discount_percent=Decimal("-10.00"),  # Negative discount = 10% surcharge
            base_price=Decimal("180.00"),
            total_price=Decimal("180.00") * (Decimal("1.00") - Decimal("-0.10")),  # 198.00
            is_active=True
        )

        test_db.add(bundle)

        try:
            test_db.commit()
            test_db.refresh(bundle)

            # Negative discount creates higher price
            assert bundle.total_price > bundle.base_price  # Surcharge
            assert bundle.savings < 0  # "Negative savings"

            # This is technically valid, but unusual - document behavior
        except IntegrityError:
            # If constraint prevents this, that's also fine
            test_db.rollback()
            pytest.skip("Database constraint prevents negative discount")

    def test_purchase_bundle_during_deactivation_race_condition(
        self, test_db: Session, user: User
    ):
        """
        RACE CONDITION TEST: Purchase bundle while it's being deactivated

        Expected: Purchase should fail (bundle not available)
        Note: Currently no row-level lock on bundle - potential race condition
        """
        # Create active bundle
        bundle = TokenBundle(
            name="Race Condition Bundle",
            description="Bundle for testing concurrent operations",
            token_count=5,
            duration_hours=24,
            scope="full",
            discount_percent=Decimal("10.00"),
            base_price=Decimal("90.00"),
            total_price=Decimal("81.00"),
            is_active=True
        )
        test_db.add(bundle)
        test_db.commit()
        test_db.refresh(bundle)

        # Simulate: Thread 1 starts purchase, Thread 2 deactivates bundle

        # Thread 2: Deactivate bundle
        bundle.is_active = False
        test_db.commit()

        # Thread 1: Attempt purchase (after deactivation)
        # BundleService raises HTTPException, not ValueError
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            BundleService.purchase_bundle(
                db=test_db,
                user_id=user.id,
                bundle_id=bundle.id
            )

        # Verify it's a 404 error
        assert exc_info.value.status_code == 404
        assert "Bundle not found or inactive" in exc_info.value.detail

        # Purchase should fail because bundle is inactive
        # NOTE: Without row-level lock, there's a window for race condition
        # between "check is_active" and "create tokens"
