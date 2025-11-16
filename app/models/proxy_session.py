"""
ProxySession model for tracking active proxy connections
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, BigInteger, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship

from app.core.database import Base


class ProxySession(Base):
    """
    ProxySession model - tracks active proxy connections

    Each session represents a user's connection through the proxy.
    Sessions are created automatically when a user makes their first
    proxy request and updated on each subsequent request.

    Sessions are marked as inactive after 5 minutes of no activity
    by the background cleanup task.

    Device conflict detection: Only one device can use a token at a time.
    """
    __tablename__ = "proxy_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token_id = Column(UUID(as_uuid=True), ForeignKey("access_tokens.id"), nullable=False, index=True)
    device_id = Column(String(255), nullable=False, index=True)  # Hardware-based device identifier
    ip_address = Column(INET, nullable=False)  # PostgreSQL INET type for IP addresses
    user_agent = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_activity = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    bytes_transferred = Column(BigInteger, default=0, nullable=False)
    request_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="proxy_sessions")
    token = relationship("AccessToken", back_populates="proxy_sessions")

    def __repr__(self):
        # Truncate device_id for readability
        device_id_short = self.device_id[:16] + "..." if len(self.device_id) > 16 else self.device_id
        return (
            f"<ProxySession(id={self.id}, user_id={self.user_id}, "
            f"device_id={device_id_short}, ip={self.ip_address}, "
            f"requests={self.request_count}, active={self.is_active})>"
        )
