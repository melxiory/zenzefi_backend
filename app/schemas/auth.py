from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Schema for login request"""

    email: EmailStr
    password: str


class TokenData(BaseModel):
    """Schema for JWT token payload data"""

    user_id: Optional[UUID] = None
    username: Optional[str] = None


class JWTTokenResponse(BaseModel):
    """Schema for JWT token response (after login)"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
