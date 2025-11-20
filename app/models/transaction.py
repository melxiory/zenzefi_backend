import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class TransactionType(str, enum.Enum):
    """Transaction type enum"""

    DEPOSIT = "deposit"  # Balance top-up (пополнение баланса)
    PURCHASE = "purchase"  # Token purchase (покупка токена)
    REFUND = "refund"  # Token refund (возврат за неиспользованное время)
    REFERRAL_BONUS = "referral_bonus"  # Referral bonus (реферальный бонус)


class Transaction(Base):
    """Transaction model - represents financial transactions"""

    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    amount = Column(
        Numeric(10, 2), nullable=False, comment="Amount in ZNC (+ for deposit/refund, - for purchase)"
    )
    transaction_type = Column(
        SQLEnum(TransactionType), nullable=False, index=True, comment="Type of transaction"
    )
    description = Column(String, nullable=False, comment="Human-readable description")
    payment_id = Column(
        String, nullable=True, comment="External payment gateway ID (YooKassa, Stripe, etc.)"
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction {self.id} {self.transaction_type.value} {self.amount} ZNC>"
