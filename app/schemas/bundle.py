"""
Pydantic schemas for Token Bundle operations.
"""
from decimal import Decimal
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.token import TokenResponse


class BundleBase(BaseModel):
    """Base bundle schema with common fields."""
    name: str = Field(..., max_length=100, description="Bundle name")
    description: Optional[str] = Field(None, description="Marketing description")
    token_count: int = Field(..., gt=0, description="Number of tokens in bundle")
    duration_hours: int = Field(..., gt=0, description="Duration of each token in hours")
    scope: str = Field(default="full", description="Token scope")
    discount_percent: Decimal = Field(..., ge=0, le=100, description="Discount percentage")
    base_price: Decimal = Field(..., gt=0, description="Price without discount")
    total_price: Decimal = Field(..., gt=0, description="Final price with discount")


class BundleCreate(BundleBase):
    """Schema for creating a new bundle (admin only)."""
    is_active: bool = Field(default=True, description="Whether bundle is active")


class BundleUpdate(BaseModel):
    """Schema for updating a bundle (admin only)."""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    token_count: Optional[int] = Field(None, gt=0)
    duration_hours: Optional[int] = Field(None, gt=0)
    scope: Optional[str] = None
    discount_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    base_price: Optional[Decimal] = Field(None, gt=0)
    total_price: Optional[Decimal] = Field(None, gt=0)
    is_active: Optional[bool] = None


class BundleResponse(BundleBase):
    """Schema for bundle in API responses."""
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Computed fields
    savings: Decimal = Field(..., description="Amount saved (base_price - total_price)")
    price_per_token: Decimal = Field(..., description="Price per token in bundle")

    model_config = ConfigDict(from_attributes=True)


class BundleListResponse(BaseModel):
    """Schema for list of bundles response."""
    items: List[BundleResponse]


class BundlePurchaseResponse(BaseModel):
    """Schema for bundle purchase response."""
    bundle_name: str = Field(..., description="Name of purchased bundle")
    tokens_generated: int = Field(..., description="Number of tokens created")
    cost_znc: Decimal = Field(..., description="Total cost in ZNC")
    new_balance: Decimal = Field(..., description="User's balance after purchase")
    tokens: List[TokenResponse] = Field(..., description="Generated access tokens")


class BundleStatsResponse(BaseModel):
    """Schema for bundle statistics (admin)."""
    bundle_id: UUID
    bundle_name: str
    total_purchases: int = Field(..., description="Total times this bundle was purchased")
    total_revenue: Decimal = Field(..., description="Total revenue from this bundle")
    total_tokens_generated: int = Field(..., description="Total tokens created from this bundle")
    avg_purchase_time: Optional[datetime] = Field(None, description="Average purchase timestamp")
