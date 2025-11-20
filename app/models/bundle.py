"""
Token Bundle model for package deals with discounts.

Provides bulk purchase options with progressive discounts to increase AOV.
"""
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, Numeric, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.core.database import Base


class TokenBundle(Base):
    """
    Token bundle model for bulk purchases with discounts.

    Example: "Starter Pack" - 5 tokens x 24h for 81 ZNC instead of 90 ZNC (10% off)

    Attributes:
        id: Unique bundle identifier
        name: Bundle name (e.g., "Starter Pack", "Pro Bundle")
        description: Marketing description of the bundle
        token_count: Number of tokens in this bundle
        duration_hours: Duration of each token in hours (1, 12, 24, 168, 720)
        scope: Token scope ("full" or "certificates_only")
        discount_percent: Discount percentage (10.00 = 10%)
        base_price: Price without discount
        total_price: Final price after discount
        is_active: Whether bundle is currently available for purchase
        created_at: Bundle creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "token_bundles"

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
        nullable=False
    )

    # Bundle details
    name = Column(
        String(100),
        nullable=False,
        comment="Bundle name (e.g., 'Starter Pack')"
    )

    description = Column(
        Text,
        nullable=True,
        comment="Marketing description"
    )

    # Token specifications
    token_count = Column(
        Integer,
        nullable=False,
        comment="Number of tokens in bundle"
    )

    duration_hours = Column(
        Integer,
        nullable=False,
        comment="Duration of each token in hours"
    )

    scope = Column(
        String(50),
        nullable=False,
        default="full",
        comment="Token scope: 'full' or 'certificates_only'"
    )

    # Pricing
    discount_percent = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Discount percentage (10.00 = 10%)"
    )

    base_price = Column(
        Numeric(10, 2),
        nullable=False,
        comment="Price without discount"
    )

    total_price = Column(
        Numeric(10, 2),
        nullable=False,
        comment="Final price with discount"
    )

    # Availability
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether bundle is available for purchase"
    )

    # Metadata
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Bundle creation timestamp"
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Last update timestamp"
    )

    def __repr__(self):
        """String representation of TokenBundle."""
        return (
            f"<TokenBundle {self.name} "
            f"({self.token_count}x{self.duration_hours}h) - "
            f"{self.total_price} ZNC>"
        )

    @property
    def savings(self) -> Decimal:
        """Calculate savings amount (base_price - total_price)."""
        return self.base_price - self.total_price

    @property
    def price_per_token(self) -> Decimal:
        """Calculate price per token in the bundle."""
        if self.token_count > 0:
            return self.total_price / Decimal(self.token_count)
        return Decimal("0.00")
