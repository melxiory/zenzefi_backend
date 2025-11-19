"""
Bundle service for managing token bundle purchases.

Provides business logic for bulk token purchases with discounts.
"""
from decimal import Decimal
from typing import List, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.bundle import TokenBundle
from app.models.user import User
from app.models.transaction import Transaction, TransactionType
from app.services.token_service import TokenService


class BundleService:
    """Service for managing token bundles and purchases."""

    @staticmethod
    def get_available_bundles(db: Session, active_only: bool = True) -> List[TokenBundle]:
        """
        Get list of available bundles, sorted by price.

        Args:
            db: Database session
            active_only: If True, return only active bundles (default: True)

        Returns:
            List of TokenBundle objects sorted by total_price
        """
        query = db.query(TokenBundle)

        if active_only:
            query = query.filter(TokenBundle.is_active == True)

        return query.order_by(TokenBundle.total_price).all()

    @staticmethod
    def get_bundle_by_id(db: Session, bundle_id: UUID) -> TokenBundle:
        """
        Get bundle by ID.

        Args:
            db: Database session
            bundle_id: Bundle UUID

        Returns:
            TokenBundle object

        Raises:
            HTTPException: 404 if bundle not found or inactive
        """
        bundle = db.query(TokenBundle).filter(
            TokenBundle.id == bundle_id,
            TokenBundle.is_active == True
        ).first()

        if not bundle:
            raise HTTPException(
                status_code=404,
                detail="Bundle not found or inactive"
            )

        return bundle

    @staticmethod
    def purchase_bundle(
        bundle_id: UUID,
        user_id: UUID,
        db: Session
    ) -> Dict[str, Any]:
        """
        Purchase a token bundle.

        Process:
            1. Validate bundle exists and is active
            2. Lock user row and check balance
            3. Deduct bundle cost from balance
            4. Generate all tokens in the bundle
            5. Create PURCHASE transaction
            6. Commit everything atomically

        Args:
            bundle_id: ID of bundle to purchase
            user_id: ID of user making purchase
            db: Database session

        Returns:
            Dictionary with:
                - bundle_name: str
                - tokens_generated: int
                - cost_znc: Decimal
                - new_balance: Decimal
                - tokens: List[dict] - generated tokens

        Raises:
            HTTPException:
                - 404: Bundle not found or inactive
                - 404: User not found
                - 402: Insufficient balance

        Security:
            - Row-level locking (with_for_update) prevents race conditions
            - Atomic transaction ensures consistency
        """
        # Get bundle and validate
        bundle = BundleService.get_bundle_by_id(db, bundle_id)

        # Get user with row-level lock (prevents race conditions on balance)
        user = db.query(User).filter(User.id == user_id).with_for_update().first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check balance
        if user.currency_balance < bundle.total_price:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Insufficient balance. "
                    f"Required: {bundle.total_price} ZNC, "
                    f"Available: {user.currency_balance} ZNC"
                )
            )

        # Deduct cost from balance
        user.currency_balance -= bundle.total_price

        # Generate tokens WITHOUT additional balance deduction (balance already deducted above)
        tokens = []
        for i in range(bundle.token_count):
            token = TokenService.create_token_without_charge(
                user_id=user.id,
                duration_hours=bundle.duration_hours,
                scope=bundle.scope,
                db=db
            )
            tokens.append(token)

        # Create transaction record (single transaction for entire bundle)
        transaction = Transaction(
            user_id=user.id,
            amount=-bundle.total_price,  # Negative for purchase
            transaction_type=TransactionType.PURCHASE,
            description=(
                f"Bundle purchase: {bundle.name} "
                f"({bundle.token_count} tokens x {bundle.duration_hours}h)"
            )
        )
        db.add(transaction)

        # Commit all changes atomically
        db.commit()
        db.refresh(user)

        # Award referral bonus if applicable (Phase 5)
        from app.services.currency_service import CurrencyService
        CurrencyService.award_referral_bonus(
            referee_id=user_id,
            purchase_amount=bundle.total_price,
            db=db
        )

        return {
            "bundle_name": bundle.name,
            "tokens_generated": len(tokens),
            "cost_znc": bundle.total_price,  # Keep as Decimal for proper serialization
            "new_balance": user.currency_balance,  # Keep as Decimal for proper serialization
            "tokens": tokens
        }

    @staticmethod
    def create_bundle(
        db: Session,
        name: str,
        description: str,
        token_count: int,
        duration_hours: int,
        scope: str,
        discount_percent: Decimal,
        base_price: Decimal,
        total_price: Decimal,
        is_active: bool = True
    ) -> TokenBundle:
        """
        Create a new bundle (admin only).

        Args:
            db: Database session
            name: Bundle name
            description: Bundle description
            token_count: Number of tokens
            duration_hours: Duration per token
            scope: Token scope
            discount_percent: Discount percentage
            base_price: Price without discount
            total_price: Price with discount
            is_active: Whether bundle is active

        Returns:
            Created TokenBundle
        """
        bundle = TokenBundle(
            name=name,
            description=description,
            token_count=token_count,
            duration_hours=duration_hours,
            scope=scope,
            discount_percent=discount_percent,
            base_price=base_price,
            total_price=total_price,
            is_active=is_active
        )

        db.add(bundle)
        db.commit()
        db.refresh(bundle)

        return bundle

    @staticmethod
    def update_bundle(
        db: Session,
        bundle_id: UUID,
        **kwargs
    ) -> TokenBundle:
        """
        Update bundle (admin only).

        Args:
            db: Database session
            bundle_id: Bundle UUID
            **kwargs: Fields to update

        Returns:
            Updated TokenBundle

        Raises:
            HTTPException: 404 if bundle not found
        """
        bundle = db.query(TokenBundle).filter(TokenBundle.id == bundle_id).first()

        if not bundle:
            raise HTTPException(status_code=404, detail="Bundle not found")

        for key, value in kwargs.items():
            if value is not None and hasattr(bundle, key):
                setattr(bundle, key, value)

        db.commit()
        db.refresh(bundle)

        return bundle

    @staticmethod
    def delete_bundle(db: Session, bundle_id: UUID) -> bool:
        """
        Soft delete bundle by setting is_active=False (admin only).

        Args:
            db: Database session
            bundle_id: Bundle UUID

        Returns:
            True if deleted successfully

        Raises:
            HTTPException: 404 if bundle not found
        """
        bundle = db.query(TokenBundle).filter(TokenBundle.id == bundle_id).first()

        if not bundle:
            raise HTTPException(status_code=404, detail="Bundle not found")

        bundle.is_active = False
        db.commit()

        return True
