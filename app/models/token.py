import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class AccessToken(Base):
    """AccessToken model - represents access tokens for Zenzefi proxy"""

    __tablename__ = "access_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token = Column(
        String, unique=True, nullable=False, index=True
    )  # Random string or JWT
    duration_hours = Column(Integer, nullable=False)  # 1, 12, 24, 168, 720
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # Set on first activation
    activated_at = Column(DateTime, nullable=True)  # When first used
    is_active = Column(Boolean, default=True, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="tokens")

    def __repr__(self):
        return f"<AccessToken {self.id} user={self.user_id} expires={self.expires_at}>"
