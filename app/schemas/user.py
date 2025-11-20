from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserBase(BaseModel):
    """Base User schema"""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user"""

    password: str = Field(..., min_length=8, description="Password (8-72 bytes, bcrypt limitation)")

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        """Validate password byte length for bcrypt compatibility"""
        password_bytes = v.encode("utf-8")
        if len(password_bytes) > 72:
            raise ValueError(
                f"Password is too long ({len(password_bytes)} bytes). "
                f"Maximum is 72 bytes. Use shorter password or avoid special characters."
            )
        return v


class UserUpdate(BaseModel):
    """Schema for updating user data"""

    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, description="Password (8-72 bytes, bcrypt limitation)")

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: Optional[str]) -> Optional[str]:
        """Validate password byte length for bcrypt compatibility"""
        if v is None:
            return v
        password_bytes = v.encode("utf-8")
        if len(password_bytes) > 72:
            raise ValueError(
                f"Password is too long ({len(password_bytes)} bytes). "
                f"Maximum is 72 bytes. Use shorter password or avoid special characters."
            )
        return v


class UserResponse(UserBase):
    """Schema for User response"""

    id: UUID
    is_active: bool
    is_superuser: bool
    referral_code: str  # User's unique referral code (Phase 5)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Referral System Schemas (Phase 5)


class ReferredUserInfo(BaseModel):
    """Information about a referred user"""

    id: UUID
    username: str
    email: EmailStr
    created_at: datetime
    has_made_qualifying_purchase: bool  # Has made purchase >100 ZNC

    class Config:
        from_attributes = True


class ReferralStatsResponse(BaseModel):
    """Referral statistics for a user"""

    referral_code: str  # User's unique referral code
    total_referrals: int  # Total number of users referred
    qualifying_referrals: int  # Number who made purchase >100 ZNC
    total_bonus_earned: float  # Total ZNC earned from referrals
    referral_link: str  # Shareable registration link with code
    referred_users: list[ReferredUserInfo]  # List of referred users

    class Config:
        from_attributes = True
