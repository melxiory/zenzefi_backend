from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.schemas.auth import LoginRequest, JWTTokenResponse
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    ref: Optional[str] = Query(None, description="Referral code from existing user (12 characters)")
):
    """
    Register a new user.

    Args:
        user_data: User registration data (email, username, password, full_name)
        db: Database session
        ref: Optional referral code (query parameter)

    Returns:
        Created user data with generated referral_code

    Raises:
        HTTPException:
            - 400: Email/username already exists or invalid referral code

    Example:
        POST /api/v1/auth/register?ref=A7B9C2D4E6F8
        Body: {"email": "user@example.com", "username": "user", "password": "password123"}
    """
    try:
        user = AuthService.register_user(user_data, db, referral_code=ref)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=JWTTokenResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login and get JWT access token

    Args:
        login_data: Login credentials (email and password)
        db: Database session

    Returns:
        JWT access token

    Raises:
        HTTPException: If credentials are invalid
    """
    user = AuthService.authenticate_user(login_data.email, login_data.password, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_response = AuthService.create_user_token(user)
    return token_response
