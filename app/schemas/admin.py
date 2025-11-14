"""
Admin schemas for administrative operations

These schemas are used for admin-only endpoints that allow
superusers to manage users, tokens, and other system resources.
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, EmailStr, ConfigDict


# ========== User Management Schemas ==========

class AdminUserUpdate(BaseModel):
    """
    Schema for admin user updates

    Allows superusers to update user fields that regular users cannot,
    such as is_active, is_superuser, and currency_balance.
    """
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    currency_balance: Optional[Decimal] = None


class AdminUserResponse(BaseModel):
    """
    Detailed user response for admin endpoints

    Includes all user fields including sensitive admin fields.
    """
    id: UUID
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    currency_balance: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedUsersResponse(BaseModel):
    """Paginated list of users"""
    items: List[AdminUserResponse]
    total: int
    limit: int
    offset: int


# ========== Token Management Schemas ==========

class AdminTokenResponse(BaseModel):
    """
    Detailed token response for admin endpoints

    Includes all token fields including user information.
    """
    id: UUID
    user_id: UUID
    token: str  # Full token string (admin can see)
    duration_hours: int
    scope: str
    created_at: datetime
    activated_at: Optional[datetime] = None
    is_active: bool
    revoked_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None  # Computed property
    cost_znc: Optional[Decimal] = None  # Computed property

    # User info
    user_email: Optional[str] = None
    user_username: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedTokensResponse(BaseModel):
    """Paginated list of tokens"""
    items: List[AdminTokenResponse]
    total: int
    limit: int
    offset: int


class AdminTokenRevokeResponse(BaseModel):
    """Response for admin token revocation (no refund)"""
    revoked: bool
    token_id: UUID
    message: str
