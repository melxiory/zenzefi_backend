from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.token import (
    TokenCreate,
    TokenResponse,
    TokenValidate,
    TokenValidationResponse,
)
from app.services.token_service import TokenService

router = APIRouter()


@router.post("/purchase", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def purchase_token(
    token_data: TokenCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Purchase (create) a new access token (MVP: бесплатно)

    Args:
        token_data: Token creation data (duration_hours)
        current_user: Current authenticated user
        db: Database session

    Returns:
        Created access token

    Raises:
        HTTPException: If invalid duration
    """
    try:
        token = TokenService.generate_access_token(
            str(current_user.id), token_data.duration_hours, db
        )
        return token
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/my-tokens", response_model=list[TokenResponse])
def get_my_tokens(
    active_only: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get all tokens for current user

    Args:
        active_only: If True, return only active tokens
        current_user: Current authenticated user
        db: Database session

    Returns:
        List of access tokens
    """
    tokens = TokenService.get_user_tokens(str(current_user.id), active_only, db)
    return tokens


@router.post("/validate", response_model=TokenValidationResponse)
def validate_token(token_data: TokenValidate, db: Session = Depends(get_db)):
    """
    Validate an access token

    Args:
        token_data: Token to validate
        db: Database session

    Returns:
        Token validation result
    """
    valid, data = TokenService.validate_token(token_data.token, db)

    if valid and data:
        expires_at = datetime.fromisoformat(data["expires_at"])
        time_remaining = int((expires_at - datetime.utcnow()).total_seconds())

        return TokenValidationResponse(
            valid=True,
            user_id=data["user_id"],
            token_id=data["token_id"],
            expires_at=expires_at,
            time_remaining_seconds=max(0, time_remaining),
        )
    else:
        return TokenValidationResponse(valid=False, reason="Token expired or invalid")
