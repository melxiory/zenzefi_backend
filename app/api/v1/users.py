from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from decimal import Decimal

from app.core.database import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.transaction import Transaction, TransactionType
from app.schemas.user import UserResponse, UserUpdate, ReferralStatsResponse, ReferredUserInfo
from app.core.security import get_password_hash
from app.config import settings

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_active_user)):
    """
    Get current user profile

    Args:
        current_user: Current authenticated user

    Returns:
        User profile data
    """
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_current_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Update current user profile

    Args:
        user_update: User update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated user profile data
    """
    # Update full_name if provided
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name

    # Update password if provided
    if user_update.password is not None:
        current_user.hashed_password = get_password_hash(user_update.password)

    db.commit()
    db.refresh(current_user)

    return current_user


@router.get("/me/referrals", response_model=ReferralStatsResponse)
def get_referral_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get current user's referral statistics.

    Returns:
        - referral_code: User's unique referral code
        - total_referrals: Total number of users referred
        - qualifying_referrals: Number who made purchase >100 ZNC
        - total_bonus_earned: Total ZNC earned from referrals
        - referral_link: Shareable registration link
        - referred_users: List of referred users with purchase status

    Example response:
        {
            "referral_code": "A7B9C2D4E6F8",
            "total_referrals": 5,
            "qualifying_referrals": 3,
            "total_bonus_earned": 45.50,
            "referral_link": "http://localhost:8000/register?ref=A7B9C2D4E6F8",
            "referred_users": [...]
        }
    """
    # Get all users referred by current user
    referred_users = db.query(User).filter(User.referred_by_id == current_user.id).all()

    # Build referred user info list
    referred_user_info = []
    qualifying_count = 0

    for user in referred_users:
        # Check if user made qualifying purchase (>100 ZNC)
        qualifying_purchase = db.query(Transaction).filter(
            Transaction.user_id == user.id,
            Transaction.transaction_type == TransactionType.PURCHASE,
            Transaction.amount <= Decimal("-100.00")  # Negative because purchases are stored as negative
        ).first()

        has_qualifying = qualifying_purchase is not None
        if has_qualifying:
            qualifying_count += 1

        referred_user_info.append(
            ReferredUserInfo(
                id=user.id,
                username=user.username,
                email=user.email,
                created_at=user.created_at,
                has_made_qualifying_purchase=has_qualifying
            )
        )

    # Build referral link
    referral_link = f"{settings.BACKEND_URL}/register?ref={current_user.referral_code}"

    return ReferralStatsResponse(
        referral_code=current_user.referral_code,
        total_referrals=len(referred_users),
        qualifying_referrals=qualifying_count,
        total_bonus_earned=float(current_user.referral_bonus_earned),
        referral_link=referral_link,
        referred_users=referred_user_info
    )
