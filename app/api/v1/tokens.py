from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.token import (
    TokenCreate,
    TokenResponse,
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
