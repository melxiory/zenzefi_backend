
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, String, Boolean, DateTime, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    """User model - represents registered users"""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    currency_balance = Column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False, index=True, comment="Balance in ZNC (Zenzefi Credits)"
    )

    # Referral System (Phase 5)
    referral_code = Column(
        String(12), unique=True, nullable=False, index=True, comment="Unique 12-char referral code for this user"
    )
    referred_by_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True, comment="User who referred this user"
    )
    referral_bonus_earned = Column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False, comment="Total ZNC earned from referrals"
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    tokens = relationship("AccessToken", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    proxy_sessions = relationship("ProxySession", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")

    # Referral relationships
    referrer = relationship("User", remote_side=[id], foreign_keys=[referred_by_id], backref="referrals")

    def __repr__(self):
        return f"<User {self.username} ({self.email})>"
