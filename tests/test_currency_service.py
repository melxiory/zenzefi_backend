import pytest
from decimal import Decimal
from sqlalchemy.orm import Session

from app.services.currency_service import CurrencyService
from app.models import User, Transaction, TransactionType


def test_get_balance_new_user(test_db: Session, test_user: User):
    """Test getting balance for a new user (should be 0.00)"""
    balance = CurrencyService.get_balance(test_user.id, test_db)

    assert balance == Decimal("0.00")


def test_get_balance_after_transaction(test_db: Session, test_user: User):
    """Test getting balance after adding a transaction"""
    # Credit balance
    new_balance = CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Test deposit",
        payment_id="TEST_PAY_123",
        db=test_db
    )

    assert new_balance == Decimal("100.00")

    # Verify balance query
    balance = CurrencyService.get_balance(test_user.id, test_db)
    assert balance == Decimal("100.00")


def test_add_transaction_deposit(test_db: Session, test_user: User):
    """Test adding a DEPOSIT transaction"""
    transaction = CurrencyService.add_transaction(
        user_id=test_user.id,
        amount=Decimal("50.00"),
        transaction_type=TransactionType.DEPOSIT,
        description="Test deposit",
        payment_id="TEST_PAY_456",
        db=test_db
    )

    assert transaction.id is not None
    assert transaction.user_id == test_user.id
    assert transaction.amount == Decimal("50.00")
    assert transaction.transaction_type == TransactionType.DEPOSIT
    assert transaction.description == "Test deposit"
    assert transaction.payment_id == "TEST_PAY_456"
    assert transaction.created_at is not None


def test_add_transaction_purchase(test_db: Session, test_user: User):
    """Test adding a PURCHASE transaction (negative amount)"""
    transaction = CurrencyService.add_transaction(
        user_id=test_user.id,
        amount=Decimal("-18.00"),
        transaction_type=TransactionType.PURCHASE,
        description="Token purchase: 24h",
        payment_id=None,
        db=test_db
    )

    assert transaction.amount == Decimal("-18.00")
    assert transaction.transaction_type == TransactionType.PURCHASE
    assert transaction.payment_id is None


def test_add_transaction_refund(test_db: Session, test_user: User):
    """Test adding a REFUND transaction"""
    transaction = CurrencyService.add_transaction(
        user_id=test_user.id,
        amount=Decimal("9.00"),
        transaction_type=TransactionType.REFUND,
        description="Token refund: 12h unused",
        payment_id=None,
        db=test_db
    )

    assert transaction.amount == Decimal("9.00")
    assert transaction.transaction_type == TransactionType.REFUND


def test_get_transactions_pagination(test_db: Session, test_user: User):
    """Test transaction pagination"""
    # Create 10 transactions
    for i in range(10):
        CurrencyService.credit_balance(
            user_id=test_user.id,
            amount=Decimal("10.00"),
            description=f"Deposit {i}",
            payment_id=f"PAY_{i}",
            db=test_db
        )

    # Get first page (5 transactions)
    transactions_page1, total = CurrencyService.get_transactions(
        user_id=test_user.id,
        limit=5,
        offset=0,
        transaction_type=None,
        db=test_db
    )

    assert len(transactions_page1) == 5
    assert total == 10

    # Get second page (5 transactions)
    transactions_page2, total = CurrencyService.get_transactions(
        user_id=test_user.id,
        limit=5,
        offset=5,
        transaction_type=None,
        db=test_db
    )

    assert len(transactions_page2) == 5
    assert total == 10

    # Ensure different transactions
    page1_ids = {t.id for t in transactions_page1}
    page2_ids = {t.id for t in transactions_page2}
    assert page1_ids.isdisjoint(page2_ids)


def test_get_transactions_filter_by_type(test_db: Session, test_user: User):
    """Test filtering transactions by type"""
    # Create deposits
    CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Deposit 1",
        payment_id="PAY_1",
        db=test_db
    )
    CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("50.00"),
        description="Deposit 2",
        payment_id="PAY_2",
        db=test_db
    )

    # Create purchase (manually via add_transaction)
    CurrencyService.add_transaction(
        user_id=test_user.id,
        amount=Decimal("-18.00"),
        transaction_type=TransactionType.PURCHASE,
        description="Token purchase",
        payment_id=None,
        db=test_db
    )

    # Get only DEPOSIT transactions
    deposits, total = CurrencyService.get_transactions(
        user_id=test_user.id,
        limit=10,
        offset=0,
        transaction_type=TransactionType.DEPOSIT,
        db=test_db
    )

    assert total == 2
    assert all(t.transaction_type == TransactionType.DEPOSIT for t in deposits)

    # Get only PURCHASE transactions
    purchases, total = CurrencyService.get_transactions(
        user_id=test_user.id,
        limit=10,
        offset=0,
        transaction_type=TransactionType.PURCHASE,
        db=test_db
    )

    assert total == 1
    assert purchases[0].transaction_type == TransactionType.PURCHASE


def test_credit_balance(test_db: Session, test_user: User):
    """Test crediting user balance (atomic operation)"""
    initial_balance = CurrencyService.get_balance(test_user.id, test_db)
    assert initial_balance == Decimal("0.00")

    # Credit 100 ZNC
    new_balance = CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Test credit",
        payment_id="TEST_CREDIT_1",
        db=test_db
    )

    assert new_balance == Decimal("100.00")

    # Verify transaction was created
    transactions, total = CurrencyService.get_transactions(
        user_id=test_user.id,
        limit=10,
        offset=0,
        transaction_type=TransactionType.DEPOSIT,
        db=test_db
    )

    assert total == 1
    assert transactions[0].amount == Decimal("100.00")
    assert transactions[0].payment_id == "TEST_CREDIT_1"


def test_credit_balance_negative_amount(test_db: Session, test_user: User):
    """Test that credit_balance rejects negative amounts"""
    with pytest.raises(ValueError, match="Amount must be positive"):
        CurrencyService.credit_balance(
            user_id=test_user.id,
            amount=Decimal("-10.00"),
            description="Invalid negative",
            payment_id=None,
            db=test_db
        )


def test_get_balance_user_not_found(test_db: Session):
    """Test getting balance for non-existent user"""
    import uuid

    fake_user_id = uuid.uuid4()

    with pytest.raises(ValueError, match="User not found"):
        CurrencyService.get_balance(fake_user_id, test_db)
