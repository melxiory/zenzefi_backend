from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TokenCreate(BaseModel):
    """Schema for creating a new access token"""

    duration_hours: int = Field(..., ge=1, description="Duration in hours: 1, 12, 24, 168, 720")


class TokenValidate(BaseModel):
    """Schema for validating a token"""

    token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Schema for Access Token response"""

    token_id: UUID = Field(..., alias="id")
    token: str
    duration_hours: int
    created_at: datetime
    expires_at: Optional[datetime] = None  # NULL until token is activated
    activated_at: Optional[datetime] = None
    is_active: bool

    class Config:
        from_attributes = True
        populate_by_name = True


class TokenValidationResponse(BaseModel):
    """Schema for token validation response"""

    valid: bool
    user_id: Optional[UUID] = None
    token_id: Optional[UUID] = None
    expires_at: Optional[datetime] = None
    time_remaining_seconds: Optional[int] = None
    reason: Optional[str] = None
