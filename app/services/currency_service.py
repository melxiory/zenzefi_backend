from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import User, Transaction, TransactionType


class CurrencyService:
    """Service for managing user currency balance and transactions"""

    @staticmethod
    def get_balance(user_id: UUID, db: Session) -> Decimal:
        """
        Get user's current currency balance.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            Decimal: Current balance in ZNC

        Raises:
            ValueError: If user not found
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        return user.currency_balance

    @staticmethod
    def get_transactions(
        user_id: UUID,
        limit: int,
        offset: int,
        transaction_type: Optional[TransactionType],
        db: Session
    ) -> tuple[list[Transaction], int]:
        """
        Get user's transaction history with pagination.

        Args:
            user_id: User ID
            limit: Number of transactions to return
            offset: Number of transactions to skip
            transaction_type: Filter by type (optional)
            db: Database session

        Returns:
            tuple[list[Transaction], int]: (transactions, total_count)
        """
        query = db.query(Transaction).filter(Transaction.user_id == user_id)

        # Apply type filter if provided
        if transaction_type:
            query = query.filter(Transaction.transaction_type == transaction_type)

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        transactions = (
            query.order_by(desc(Transaction.created_at))
            .limit(limit)
            .offset(offset)
            .all()
        )

        return transactions, total

    @staticmethod
    def add_transaction(
        user_id: UUID,
        amount: Decimal,
        transaction_type: TransactionType,
        description: str,
        payment_id: Optional[str],
        db: Session
    ) -> Transaction:
        """
        Create a new transaction record.

        NOTE: This does NOT modify user balance - use credit_balance() for that.
        This method only creates the transaction record for audit trail.

        Args:
            user_id: User ID
            amount: Amount in ZNC (+ for deposit/refund, - for purchase)
            transaction_type: Type of transaction
            description: Human-readable description
            payment_id: External payment gateway ID (optional)
            db: Database session

        Returns:
            Transaction: Created transaction

        Raises:
            ValueError: If user not found
        """
        # Verify user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        # Create transaction
        transaction = Transaction(
            user_id=user_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description,
            payment_id=payment_id,
            created_at=datetime.now(timezone.utc)
        )

        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        return transaction

    @staticmethod
    def credit_balance(
        user_id: UUID,
        amount: Decimal,
        description: str,
        payment_id: Optional[str],
        db: Session
    ) -> Decimal:
        """
        Credit user balance (add money) and create transaction record.

        This is an atomic operation that updates balance and creates transaction.

        Args:
            user_id: User ID
            amount: Amount to add in ZNC (must be positive)
            description: Human-readable description
            payment_id: External payment gateway ID (optional)
            db: Database session

        Returns:
            Decimal: New balance after credit

        Raises:
            ValueError: If user not found or amount is negative
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        # Get user with row lock (for atomic operation)
        user = db.query(User).filter(User.id == user_id).with_for_update().first()
        if not user:
            raise ValueError("User not found")

        # Update balance
        user.currency_balance += amount

        # Create transaction record
        transaction = Transaction(
            user_id=user_id,
            amount=amount,
            transaction_type=TransactionType.DEPOSIT,
            description=description,
            payment_id=payment_id,
            created_at=datetime.now(timezone.utc)
        )

        db.add(transaction)
        db.commit()

        return user.currency_balance
