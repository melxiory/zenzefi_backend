"""
API endpoints for token bundle operations.

Provides endpoints for:
- Listing available bundles
- Purchasing bundles
- Managing bundles (admin)
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_active_user, get_current_superuser
from app.models.user import User
from app.services.bundle_service import BundleService
from app.schemas.bundle import (
    BundleResponse,
    BundlePurchaseResponse,
    BundleCreate,
    BundleUpdate
)

router = APIRouter(tags=["bundles"])


@router.get("/", response_model=dict)
async def list_bundles(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get list of available token bundles.

    Query Parameters:
        active_only (bool): Show only active bundles (default: True)

    Returns:
        {
            "items": [
                {
                    "id": "uuid",
                    "name": "Starter Pack",
                    "description": "5 tokens for beginners - 10% off",
                    "token_count": 5,
                    "duration_hours": 24,
                    "scope": "full",
                    "discount_percent": 10.00,
                    "base_price": 90.00,
                    "total_price": 81.00,
                    "savings": 9.00,
                    "price_per_token": 16.20,
                    "is_active": true,
                    "created_at": "2025-XX-XXT...",
                    "updated_at": "2025-XX-XXT..."
                },
                ...
            ]
        }

    Note: No authentication required (public endpoint)
    """
    bundles = BundleService.get_available_bundles(db, active_only=active_only)

    return {
        "items": [
            {
                "id": str(b.id),
                "name": b.name,
                "description": b.description,
                "token_count": b.token_count,
                "duration_hours": b.duration_hours,
                "scope": b.scope,
                "discount_percent": b.discount_percent,
                "base_price": b.base_price,
                "total_price": b.total_price,
                "savings": b.savings,
                "price_per_token": b.price_per_token,
                "is_active": b.is_active,
                "created_at": b.created_at.isoformat(),
                "updated_at": b.updated_at.isoformat() if b.updated_at else None
            }
            for b in bundles
        ]
    }


@router.get("/{bundle_id}", response_model=dict)
async def get_bundle(
    bundle_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get specific bundle by ID.

    Path Parameters:
        bundle_id: Bundle UUID

    Returns:
        Bundle details (same format as list_bundles items)

    Errors:
        404: Bundle not found or inactive

    Note: No authentication required (public endpoint)
    """
    bundle = BundleService.get_bundle_by_id(db, bundle_id)

    return {
        "id": str(bundle.id),
        "name": bundle.name,
        "description": bundle.description,
        "token_count": bundle.token_count,
        "duration_hours": bundle.duration_hours,
        "scope": bundle.scope,
        "discount_percent": bundle.discount_percent,
        "base_price": bundle.base_price,
        "total_price": bundle.total_price,
        "savings": bundle.savings,
        "price_per_token": bundle.price_per_token,
        "is_active": bundle.is_active,
        "created_at": bundle.created_at.isoformat(),
        "updated_at": bundle.updated_at.isoformat() if bundle.updated_at else None
    }


@router.post("/{bundle_id}/purchase", response_model=BundlePurchaseResponse)
async def purchase_bundle(
    bundle_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Purchase a token bundle.

    Requirements:
        - JWT authentication (Bearer token)
        - Sufficient ZNC balance

    Process:
        1. Validate bundle exists and is active
        2. Check user balance
        3. Deduct bundle cost
        4. Generate all tokens in bundle
        5. Create PURCHASE transaction

    Path Parameters:
        bundle_id: Bundle UUID to purchase

    Returns:
        {
            "bundle_name": "Starter Pack",
            "tokens_generated": 5,
            "cost_znc": 81.00,
            "new_balance": 19.00,
            "tokens": [
                {
                    "id": "uuid",
                    "token": "...",
                    "duration_hours": 24,
                    "scope": "full",
                    "activated_at": null,
                    "expires_at": null,
                    "is_active": true,
                    "created_at": "..."
                },
                ...
            ]
        }

    Errors:
        401: Not authenticated
        402: Insufficient balance
        404: Bundle not found or inactive

    Security:
        - Row-level locking prevents balance race conditions
        - Atomic transaction ensures consistency
    """
    result = BundleService.purchase_bundle(
        bundle_id=bundle_id,
        user_id=current_user.id,
        db=db
    )

    return result


@router.post("/", response_model=BundleResponse, status_code=status.HTTP_201_CREATED)
async def create_bundle(
    bundle_data: BundleCreate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """
    Create a new bundle (admin only).

    Requires:
        - Superuser permissions

    Body:
        {
            "name": "New Bundle",
            "description": "Description",
            "token_count": 10,
            "duration_hours": 24,
            "scope": "full",
            "discount_percent": 15.00,
            "base_price": 180.00,
            "total_price": 153.00,
            "is_active": true
        }

    Returns:
        Created bundle object

    Errors:
        401: Not authenticated
        403: Not a superuser
    """
    bundle = BundleService.create_bundle(
        db=db,
        **bundle_data.model_dump()
    )

    return bundle


@router.patch("/{bundle_id}", response_model=BundleResponse)
async def update_bundle(
    bundle_id: UUID,
    bundle_data: BundleUpdate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """
    Update bundle (admin only).

    Requires:
        - Superuser permissions

    Path Parameters:
        bundle_id: Bundle UUID

    Body:
        Any fields from BundleUpdate (all optional)

    Returns:
        Updated bundle object

    Errors:
        401: Not authenticated
        403: Not a superuser
        404: Bundle not found
    """
    bundle = BundleService.update_bundle(
        db=db,
        bundle_id=bundle_id,
        **bundle_data.model_dump(exclude_unset=True)
    )

    return bundle


@router.delete("/{bundle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bundle(
    bundle_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """
    Soft delete bundle (set is_active=False) (admin only).

    Requires:
        - Superuser permissions

    Path Parameters:
        bundle_id: Bundle UUID

    Returns:
        204 No Content on success

    Errors:
        401: Not authenticated
        403: Not a superuser
        404: Bundle not found

    Note: This is a soft delete - bundle is not removed from database
    """
    BundleService.delete_bundle(db=db, bundle_id=bundle_id)
    return None
