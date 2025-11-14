"""
Payment service with mock payment provider for development/testing.
In production, replace MockPaymentProvider with real gateway (YooKassa, Stripe).
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.transaction import Transaction, TransactionType
from app.config import settings


class MockPaymentProvider:
    """
    Mock payment gateway for development and testing.

    Simulates payment flow:
    1. create_payment() - creates pending transaction, returns mock payment URL
    2. simulate_payment_success() - simulates user completing payment (credits balance)
    3. handle_webhook() - processes payment status updates

    In production, replace with:
    - YooKassa SDK (yookassa package)
    - Stripe SDK (stripe package)
    - Or other payment gateway
    """

    @staticmethod
    async def create_payment(
        amount_znc: Decimal,
        user_id: uuid.UUID,
        return_url: str,
        db: Session
    ) -> dict:
        """
        Create mock payment for ZNC purchase.

        Args:
            amount_znc: Amount of ZNC credits to purchase
            user_id: User ID making the purchase
            return_url: URL to redirect after payment completion
            db: Database session

        Returns:
            dict with payment_id, payment_url, amounts, status
        """
        # Generate mock payment ID
        payment_id = f"MOCK_PAY_{uuid.uuid4()}"

        # Calculate RUB amount (1 ZNC = 10 RUB by default)
        amount_rub = amount_znc * settings.ZNC_TO_RUB_RATE

        # Create pending transaction
        transaction = Transaction(
            user_id=user_id,
            amount=amount_znc,
            transaction_type=TransactionType.DEPOSIT,
            description=f"Balance top-up: {amount_znc} ZNC (pending)",
            payment_id=payment_id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(transaction)
        db.commit()

        # Mock payment URL (redirects to simulation endpoint)
        mock_payment_url = f"{settings.MOCK_PAYMENT_URL}?payment_id={payment_id}"

        return {
            "payment_id": payment_id,
            "payment_url": mock_payment_url,
            "amount_znc": amount_znc,
            "amount_rub": amount_rub,
            "status": "pending"
        }

    @staticmethod
    async def simulate_payment_success(
        payment_id: str,
        db: Session
    ) -> bool:
        """
        Simulate successful payment completion (for testing/development).

        Args:
            payment_id: Payment ID to mark as succeeded
            db: Database session

        Returns:
            True if payment processed successfully, False if not found
        """
        # Find pending transaction
        transaction = db.query(Transaction).filter(
            Transaction.payment_id == payment_id,
            Transaction.transaction_type == TransactionType.DEPOSIT
        ).with_for_update().first()

        if not transaction:
            return False

        # Skip if already processed
        if "(succeeded)" in transaction.description:
            return True

        # Credit user balance
        user = db.query(User).filter(
            User.id == transaction.user_id
        ).with_for_update().first()

        if not user:
            return False

        user.currency_balance += transaction.amount

        # Update transaction description
        transaction.description = transaction.description.replace("(pending)", "(succeeded)")

        db.commit()
        return True

    @staticmethod
    async def handle_webhook(
        payment_data: dict,
        db: Session
    ) -> bool:
        """
        Handle payment webhook (status update from payment gateway).

        Args:
            payment_data: Webhook payload with payment_id and status
            db: Database session

        Returns:
            True if webhook processed successfully
        """
        payment_id = payment_data.get("payment_id")
        status = payment_data.get("status")

        if not payment_id or not status:
            return False

        # Find transaction
        transaction = db.query(Transaction).filter(
            Transaction.payment_id == payment_id
        ).with_for_update().first()

        if not transaction:
            return False

        if status == "succeeded":
            # Credit balance
            user = db.query(User).filter(
                User.id == transaction.user_id
            ).with_for_update().first()

            if not user:
                return False

            user.currency_balance += transaction.amount
            transaction.description = transaction.description.replace("(pending)", "(succeeded)")
            db.commit()
            return True

        elif status == "canceled":
            # Mark as canceled (no balance credit)
            transaction.description = transaction.description.replace("(pending)", "(canceled)")
            db.commit()
            return False

        return False
