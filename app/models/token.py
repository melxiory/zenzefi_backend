import uuid
from datetime import datetime, timedelta
from typing import Optional

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
    activated_at = Column(DateTime, nullable=True)  # When first used (NULL = not activated)
    is_active = Column(Boolean, default=True, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    # Note: expires_at is calculated dynamically as activated_at + timedelta(hours=duration_hours)
    # This eliminates data duplication and potential sync issues

    # Relationships
    user = relationship("User", back_populates="tokens")

    @property
    def expires_at(self) -> Optional[datetime]:
        """
        Calculate expiration time dynamically from activation time.

        Returns:
            datetime if token is activated, None if not activated yet
        """
        if self.activated_at is None:
            return None
        return self.activated_at + timedelta(hours=self.duration_hours)

    def __repr__(self):
        return f"<AccessToken {self.id} user={self.user_id} expires={self.expires_at}>"
