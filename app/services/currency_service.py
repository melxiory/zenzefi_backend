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

    @staticmethod
    def award_referral_bonus(
        referee_id: UUID,
        purchase_amount: Decimal,
        db: Session
    ) -> Optional[Decimal]:
        """
        Award referral bonus to referrer when referee makes qualifying purchase.

        Rules:
        - Only triggered on FIRST purchase >100 ZNC by referee
        - Referrer receives 10% of purchase amount
        - Bonus tracked in referrer's referral_bonus_earned

        Args:
            referee_id: User ID of person making purchase (who was referred)
            purchase_amount: Amount of purchase in ZNC
            db: Database session

        Returns:
            Decimal: Bonus amount awarded to referrer, or None if no bonus awarded

        Note:
            This method should be called AFTER successful purchase transaction.
        """
        # Get referee
        referee = db.query(User).filter(User.id == referee_id).first()
        if not referee or not referee.referred_by_id:
            return None  # User wasn't referred by anyone

        # Check if purchase qualifies (>100 ZNC)
        if purchase_amount <= Decimal("100.00"):
            return None  # Purchase too small

        # Check if this is referee's first qualifying purchase
        # Count previous PURCHASE transactions >100 ZNC
        previous_purchases = db.query(Transaction).filter(
            Transaction.user_id == referee_id,
            Transaction.transaction_type == TransactionType.PURCHASE,
            Transaction.amount <= Decimal("-100.00")  # Negative because purchases are stored as negative
        ).count()

        if previous_purchases > 1:  # Current purchase is already in DB, so >1 means not first
            return None  # Not first qualifying purchase

        # Calculate 10% bonus
        bonus_amount = (purchase_amount * Decimal("0.10")).quantize(Decimal("0.01"))

        # Get referrer with row lock
        referrer = db.query(User).filter(
            User.id == referee.referred_by_id
        ).with_for_update().first()

        if not referrer:
            return None  # Referrer no longer exists

        # Award bonus
        referrer.currency_balance += bonus_amount
        referrer.referral_bonus_earned += bonus_amount

        # Create transaction for referrer
        transaction = Transaction(
            user_id=referrer.id,
            amount=bonus_amount,
            transaction_type=TransactionType.REFERRAL_BONUS,
            description=f"Referral bonus from {referee.username} (first purchase {purchase_amount} ZNC)",
            payment_id=None,
            created_at=datetime.now(timezone.utc)
        )

        db.add(transaction)
        db.commit()

        return bonus_amount
