from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.schemas.token import (
    TokenCreate,
    TokenResponse,
    TokenRevokeResponse,
)
from app.services.token_service import TokenService
from app.services.currency_service import CurrencyService

router = APIRouter()


@router.post("/purchase", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def purchase_token(
    token_data: TokenCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Purchase (create) a new access token with balance deduction.

    Token can have scope:
    - "full": full access to all Zenzefi endpoints
    - "certificates_only": access only to /certificates/* endpoints

    Args:
        token_data: Token creation data (duration_hours, scope)
        current_user: Current authenticated user
        db: Database session

    Returns:
        Created access token with cost information

    Raises:
        HTTPException:
            - 400: Invalid duration or scope
            - 402: Insufficient balance
    """
    try:
        token, cost = TokenService.generate_access_token(
            str(current_user.id), token_data.duration_hours, token_data.scope, db
        )

        # cost_znc is now automatically calculated via @property in AccessToken model
        return TokenResponse.model_validate(token)
    except ValueError as e:
        error_msg = str(e)
        # Check if insufficient balance error
        if "Insufficient balance" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=error_msg,
            )
        # Other ValueError (invalid duration, user not found, etc.)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
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


@router.delete("/{token_id}", response_model=TokenRevokeResponse)
def revoke_token(
    token_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Revoke (delete) an access token with full refund.

    Only non-activated tokens can be revoked. Once a token is activated
    (used for the first time), it cannot be refunded.

    Refund policy:
    - Not activated: 100% refund (allowed)
    - Activated: Cannot revoke (error)

    Args:
        token_id: UUID of the token to revoke
        current_user: Current authenticated user
        db: Database session

    Returns:
        TokenRevokeResponse: Revocation status, refund amount, new balance

    Raises:
        HTTPException:
            - 404: Token not found or already revoked
            - 400: Token is already activated (cannot revoke)
            - 403: Token belongs to another user
    """
    try:
        # Revoke token and get refund amount
        success, refund_amount = TokenService.revoke_token(
            token_id=token_id,
            user_id=current_user.id,
            db=db,
        )

        # Get new balance
        new_balance = CurrencyService.get_balance(current_user.id, db)

        return TokenRevokeResponse(
            revoked=success,
            refund_amount=refund_amount,
            new_balance=new_balance,
            message=f"Token revoked. Refund: {refund_amount} ZNC. New balance: {new_balance} ZNC.",
        )
    except ValueError as e:
        error_msg = str(e)
        # Check if token not found
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        # Other ValueError
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )
