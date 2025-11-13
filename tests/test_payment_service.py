"""
Tests for PaymentService and MockPaymentProvider
"""
import pytest
from decimal import Decimal
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.transaction import Transaction, TransactionType
from app.services.payment_service import MockPaymentProvider


class TestMockPaymentProvider:
    """Tests for MockPaymentProvider"""

    @pytest.mark.asyncio
    async def test_create_payment(self, test_user: User, test_db: Session):
        """Test creating a mock payment"""
        # Create payment
        payment_data = await MockPaymentProvider.create_payment(
            amount_znc=Decimal("100.00"),
            user_id=test_user.id,
            return_url="https://example.com/success",
            db=test_db
        )

        # Verify payment data structure
        assert "payment_id" in payment_data
        assert payment_data["payment_id"].startswith("MOCK_PAY_")
        assert "payment_url" in payment_data
        assert payment_data["amount_znc"] == Decimal("100.00")
        assert payment_data["amount_rub"] == Decimal("1000.00")  # 100 * 10 conversion rate
        assert payment_data["status"] == "pending"

        # Verify transaction created in database
        transaction = test_db.query(Transaction).filter(
            Transaction.payment_id == payment_data["payment_id"]
        ).first()

        assert transaction is not None
        assert transaction.user_id == test_user.id
        assert transaction.amount == Decimal("100.00")
        assert transaction.transaction_type == TransactionType.DEPOSIT
        assert "(pending)" in transaction.description

    @pytest.mark.asyncio
    async def test_simulate_payment_success(self, test_user: User, test_db: Session):
        """Test simulating successful payment completion"""
        # Create payment first
        payment_data = await MockPaymentProvider.create_payment(
            amount_znc=Decimal("50.00"),
            user_id=test_user.id,
            return_url="https://example.com/success",
            db=test_db
        )
        payment_id = payment_data["payment_id"]

        # Check initial balance
        initial_balance = test_user.currency_balance
        test_db.refresh(test_user)

        # Simulate payment success
        success = await MockPaymentProvider.simulate_payment_success(payment_id, test_db)

        assert success is True

        # Verify balance increased
        test_db.refresh(test_user)
        assert test_user.currency_balance == initial_balance + Decimal("50.00")

        # Verify transaction description updated
        transaction = test_db.query(Transaction).filter(
            Transaction.payment_id == payment_id
        ).first()
        assert "(succeeded)" in transaction.description
        assert "(pending)" not in transaction.description

    @pytest.mark.asyncio
    async def test_simulate_payment_not_found(self, test_db: Session):
        """Test simulating payment with non-existent payment_id"""
        # Try to simulate non-existent payment
        success = await MockPaymentProvider.simulate_payment_success(
            "FAKE_PAYMENT_ID",
            test_db
        )

        assert success is False

    @pytest.mark.asyncio
    async def test_handle_webhook_succeeded(self, test_user: User, test_db: Session):
        """Test webhook handler for succeeded payment"""
        # Create payment first
        payment_data = await MockPaymentProvider.create_payment(
            amount_znc=Decimal("75.00"),
            user_id=test_user.id,
            return_url="https://example.com/success",
            db=test_db
        )
        payment_id = payment_data["payment_id"]

        # Check initial balance
        initial_balance = test_user.currency_balance
        test_db.refresh(test_user)

        # Send webhook with succeeded status
        webhook_data = {
            "payment_id": payment_id,
            "status": "succeeded"
        }
        success = await MockPaymentProvider.handle_webhook(webhook_data, test_db)

        assert success is True

        # Verify balance increased
        test_db.refresh(test_user)
        assert test_user.currency_balance == initial_balance + Decimal("75.00")

        # Verify transaction description updated
        transaction = test_db.query(Transaction).filter(
            Transaction.payment_id == payment_id
        ).first()
        assert "(succeeded)" in transaction.description

    @pytest.mark.asyncio
    async def test_handle_webhook_canceled(self, test_user: User, test_db: Session):
        """Test webhook handler for canceled payment"""
        # Create payment first
        payment_data = await MockPaymentProvider.create_payment(
            amount_znc=Decimal("25.00"),
            user_id=test_user.id,
            return_url="https://example.com/success",
            db=test_db
        )
        payment_id = payment_data["payment_id"]

        # Check initial balance
        initial_balance = test_user.currency_balance
        test_db.refresh(test_user)

        # Send webhook with canceled status
        webhook_data = {
            "payment_id": payment_id,
            "status": "canceled"
        }
        success = await MockPaymentProvider.handle_webhook(webhook_data, test_db)

        assert success is False

        # Verify balance NOT changed
        test_db.refresh(test_user)
        assert test_user.currency_balance == initial_balance

        # Verify transaction description updated
        transaction = test_db.query(Transaction).filter(
            Transaction.payment_id == payment_id
        ).first()
        assert "(canceled)" in transaction.description
        assert "(pending)" not in transaction.description
