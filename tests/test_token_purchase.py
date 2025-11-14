"""Tests for token purchase with balance deduction"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.services.token_service import TokenService
from app.services.currency_service import CurrencyService
from app.models import User, AccessToken, Transaction, TransactionType


def test_generate_token_insufficient_balance(test_db: Session, test_user: User):
    """Test token generation with insufficient balance (should raise ValueError)"""
    # User has 0 balance by default
    balance = CurrencyService.get_balance(test_user.id, test_db)
    assert balance == Decimal("0.00")

    # Try to purchase 24h token (costs 18 ZNC)
    with pytest.raises(ValueError, match="Insufficient balance"):
        TokenService.generate_access_token(
            user_id=str(test_user.id),
            duration_hours=24,
            scope="full",
            db=test_db
        )


def test_generate_token_with_balance(test_db: Session, test_user: User):
    """Test token generation with sufficient balance"""
    # Credit 100 ZNC
    CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Test deposit",
        payment_id="TEST",
        db=test_db
    )

    # Purchase 24h token (costs 18 ZNC)
    token, cost = TokenService.generate_access_token(
        user_id=str(test_user.id),
        duration_hours=24,
        scope="full",
        db=test_db
    )

    # Verify token created
    assert token.id is not None
    assert token.duration_hours == 24
    assert token.scope == "full"
    assert token.is_active is True
    assert cost == Decimal("18.00")

    # Verify balance deducted
    new_balance = CurrencyService.get_balance(test_user.id, test_db)
    assert new_balance == Decimal("82.00")  # 100 - 18


def test_generate_token_creates_transaction(test_db: Session, test_user: User):
    """Test that token generation creates a PURCHASE transaction"""
    # Credit 100 ZNC
    CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Test deposit",
        payment_id="TEST",
        db=test_db
    )

    # Purchase token
    token, cost = TokenService.generate_access_token(
        user_id=str(test_user.id),
        duration_hours=24,
        scope="full",
        db=test_db
    )

    # Get transactions
    transactions, total = CurrencyService.get_transactions(
        user_id=test_user.id,
        limit=10,
        offset=0,
        transaction_type=TransactionType.PURCHASE,
        db=test_db
    )

    assert total == 1
    assert transactions[0].amount == Decimal("-18.00")  # Negative for purchase
    assert transactions[0].transaction_type == TransactionType.PURCHASE
    assert "24h" in transactions[0].description
    assert transactions[0].payment_id is None


def test_revoke_token_full_refund(test_db: Session, test_user: User):
    """Test revoking a non-activated token (full refund)"""
    # Credit balance and purchase token
    CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Test",
        payment_id=None,
        db=test_db
    )

    token, cost = TokenService.generate_access_token(
        user_id=str(test_user.id),
        duration_hours=24,
        scope="full",
        db=test_db
    )

    # Revoke immediately (not activated)
    success, refund = TokenService.revoke_token(
        token_id=token.id,
        user_id=test_user.id,
        db=test_db
    )

    assert success is True
    assert refund == Decimal("18.00")  # Full refund

    # Verify balance restored
    balance = CurrencyService.get_balance(test_user.id, test_db)
    assert balance == Decimal("100.00")  # Back to original

    # Verify token revoked
    test_db.refresh(token)
    assert token.is_active is False
    assert token.revoked_at is not None


def test_revoke_token_partial_refund(test_db: Session, test_user: User):
    """Test that revoking an activated token raises ValueError (cannot revoke)"""
    # Credit balance and purchase token
    CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Test",
        payment_id=None,
        db=test_db
    )

    token, cost = TokenService.generate_access_token(
        user_id=str(test_user.id),
        duration_hours=24,
        scope="full",
        db=test_db
    )

    # Simulate token activation 12 hours ago (50% used)
    past_time = datetime.now(timezone.utc) - timedelta(hours=12)
    token.activated_at = past_time
    test_db.commit()
    test_db.refresh(token)

    # Try to revoke activated token - should raise ValueError
    with pytest.raises(ValueError, match="Cannot revoke activated token"):
        TokenService.revoke_token(
            token_id=token.id,
            user_id=test_user.id,
            db=test_db
        )

    # Verify balance unchanged (no refund was processed)
    balance = CurrencyService.get_balance(test_user.id, test_db)
    assert balance == Decimal("82.00")  # Original balance after purchase

    # Verify token still active (revocation failed)
    test_db.refresh(token)
    assert token.is_active is True
    assert token.revoked_at is None


def test_revoke_token_no_refund(test_db: Session, test_user: User):
    """Test that revoking an expired token raises ValueError (cannot revoke activated tokens)"""
    # Credit balance and purchase token
    CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Test",
        payment_id=None,
        db=test_db
    )

    token, cost = TokenService.generate_access_token(
        user_id=str(test_user.id),
        duration_hours=24,
        scope="full",
        db=test_db
    )

    # Simulate token activation 25 hours ago (expired)
    past_time = datetime.now(timezone.utc) - timedelta(hours=25)
    token.activated_at = past_time
    test_db.commit()
    test_db.refresh(token)

    # Try to revoke expired token - should raise ValueError (still activated)
    with pytest.raises(ValueError, match="Cannot revoke activated token"):
        TokenService.revoke_token(
            token_id=token.id,
            user_id=test_user.id,
            db=test_db
        )

    # Balance should remain at 82 (no refund processed)
    balance = CurrencyService.get_balance(test_user.id, test_db)
    assert balance == Decimal("82.00")


def test_revoke_token_creates_transaction(test_db: Session, test_user: User):
    """Test that token revocation creates a REFUND transaction"""
    # Credit balance and purchase token
    CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Test",
        payment_id=None,
        db=test_db
    )

    token, cost = TokenService.generate_access_token(
        user_id=str(test_user.id),
        duration_hours=24,
        scope="full",
        db=test_db
    )

    # Revoke (full refund)
    success, refund = TokenService.revoke_token(
        token_id=token.id,
        user_id=test_user.id,
        db=test_db
    )

    # Get refund transactions
    transactions, total = CurrencyService.get_transactions(
        user_id=test_user.id,
        limit=10,
        offset=0,
        transaction_type=TransactionType.REFUND,
        db=test_db
    )

    assert total == 1
    assert transactions[0].amount == Decimal("18.00")  # Positive for refund
    assert transactions[0].transaction_type == TransactionType.REFUND
    assert "refund" in transactions[0].description.lower()
    assert "not activated" in transactions[0].description.lower()


def test_revoke_token_not_found(test_db: Session, test_user: User):
    """Test revoking non-existent token"""
    import uuid

    fake_token_id = uuid.uuid4()

    with pytest.raises(ValueError, match="Token not found or already revoked"):
        TokenService.revoke_token(
            token_id=fake_token_id,
            user_id=test_user.id,
            db=test_db
        )
