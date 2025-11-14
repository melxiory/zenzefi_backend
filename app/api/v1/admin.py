"""
Admin API endpoints

Administrative endpoints for managing users, tokens, and system resources.
All endpoints require superuser permissions.
"""
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional
from loguru import logger

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_superuser
from app.models import User, AccessToken, AuditLog
from app.services.token_service import TokenService
from app.services.audit_service import AuditService
from app.schemas.admin import (
    AdminUserUpdate,
    AdminUserResponse,
    PaginatedUsersResponse,
    AdminTokenResponse,
    PaginatedTokensResponse,
    AdminTokenRevokeResponse,
    AuditLogResponse,
    PaginatedAuditLogsResponse,
)

router = APIRouter()


# ========== User Management ==========

@router.get("/users", response_model=PaginatedUsersResponse)
async def list_users(
    limit: int = Query(50, le=100, description="Number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    search: Optional[str] = Query(None, description="Search by email or username"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """
    List all users (superuser only)

    Query parameters:
    - limit: Maximum number of users to return (default: 50, max: 100)
    - offset: Number of users to skip for pagination
    - search: Optional search string (matches email or username)
    - is_active: Optional filter by active status

    Returns:
        Paginated list of users with total count
    """
    query = db.query(User)

    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (User.email.ilike(search_pattern)) |
            (User.username.ilike(search_pattern))
        )

    # Apply is_active filter
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    # Get total count
    total = query.count()

    # Apply pagination and ordering
    users = query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()

    return PaginatedUsersResponse(
        items=[AdminUserResponse.model_validate(u) for u in users],
        total=total,
        limit=limit,
        offset=offset
    )


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    request: AdminUserUpdate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """
    Update user (superuser only)

    Allows updating admin-only fields:
    - is_active: Enable/disable user account
    - is_superuser: Grant/revoke superuser permissions
    - currency_balance: Manually adjust user balance

    Args:
        user_id: UUID of user to update
        request: Update data

    Returns:
        Updated user object

    Raises:
        404: User not found
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Track changed fields for audit log
    changed_fields = {}

    # Update fields if provided
    if request.is_active is not None:
        changed_fields["is_active"] = {"old": user.is_active, "new": request.is_active}
        user.is_active = request.is_active
        logger.info(f"Admin {current_user.username} set user {user.username} is_active={request.is_active}")

    if request.is_superuser is not None:
        changed_fields["is_superuser"] = {"old": user.is_superuser, "new": request.is_superuser}
        user.is_superuser = request.is_superuser
        logger.info(f"Admin {current_user.username} set user {user.username} is_superuser={request.is_superuser}")

    if request.currency_balance is not None:
        old_balance = user.currency_balance
        changed_fields["currency_balance"] = {"old": float(old_balance), "new": float(request.currency_balance)}
        user.currency_balance = request.currency_balance
        logger.info(
            f"Admin {current_user.username} updated user {user.username} balance: "
            f"{old_balance} → {request.currency_balance} ZNC"
        )

    # Audit log
    if changed_fields:
        AuditService.log_user_update(
            target_user_id=user.id,
            admin_user_id=current_user.id,
            changed_fields=changed_fields,
            db=db,
        )

    db.commit()
    db.refresh(user)

    return AdminUserResponse.model_validate(user)


# ========== Token Management ==========

@router.get("/tokens", response_model=PaginatedTokensResponse)
async def list_tokens(
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    active_only: bool = Query(True, description="Show only active tokens"),
    limit: int = Query(50, le=100, description="Number of tokens to return"),
    offset: int = Query(0, ge=0, description="Number of tokens to skip"),
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """
    List all access tokens (superuser only)

    Query parameters:
    - user_id: Optional filter by user ID
    - active_only: Show only active tokens (default: true)
    - limit: Maximum number of tokens to return (default: 50, max: 100)
    - offset: Number of tokens to skip for pagination

    Returns:
        Paginated list of tokens with user information
    """
    query = db.query(AccessToken).join(User)

    # Apply user filter
    if user_id:
        query = query.filter(AccessToken.user_id == user_id)

    # Apply active filter
    if active_only:
        query = query.filter(AccessToken.is_active == True)

    # Get total count
    total = query.count()

    # Apply pagination and ordering
    tokens = query.order_by(AccessToken.created_at.desc()).limit(limit).offset(offset).all()

    # Build response with user info
    items = []
    for token in tokens:
        token_dict = AdminTokenResponse.model_validate(token).model_dump()
        token_dict["user_email"] = token.user.email
        token_dict["user_username"] = token.user.username
        items.append(AdminTokenResponse(**token_dict))

    return PaginatedTokensResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )


@router.delete("/tokens/{token_id}", response_model=AdminTokenRevokeResponse)
async def force_revoke_token(
    token_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """
    Force revoke token without refund (superuser only)

    This is an admin-only operation that revokes a token immediately
    without issuing a refund to the user. Use with caution.

    Args:
        token_id: UUID of token to revoke

    Returns:
        Revocation confirmation

    Raises:
        404: Token not found
    """
    token = db.query(AccessToken).filter(AccessToken.id == token_id).first()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )

    # Revoke token
    token.is_active = False
    token.revoked_at = datetime.now(timezone.utc)

    # Audit log
    AuditService.log_token_revoke(
        token_id=token.id,
        user_id=current_user.id,
        refund_amount=0.0,
        force_revoke=True,
        db=db,
    )

    db.commit()

    # Remove from Redis cache
    TokenService._remove_cached_token(token.token)

    logger.warning(
        f"Admin {current_user.username} force-revoked token {token_id} "
        f"(user: {token.user.username}, no refund)"
    )

    return AdminTokenRevokeResponse(
        revoked=True,
        token_id=token_id,
        message=f"Token {token_id} revoked successfully (no refund issued)"
    )


# ========== Audit Log Management ==========

@router.get("/audit-logs", response_model=PaginatedAuditLogsResponse)
async def list_audit_logs(
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    limit: int = Query(50, le=100, description="Number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """
    List audit logs (superuser only)

    Query parameters:
    - user_id: Optional filter by user ID
    - action: Optional filter by action type (e.g., "token_purchase", "admin_user_update")
    - resource_type: Optional filter by resource type (e.g., "AccessToken", "User")
    - limit: Maximum number of logs to return (default: 50, max: 100)
    - offset: Number of logs to skip for pagination

    Returns:
        Paginated list of audit logs with user information
    """
    query = db.query(AuditLog).outerjoin(User)

    # Apply user filter
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    # Apply action filter
    if action:
        query = query.filter(AuditLog.action == action)

    # Apply resource_type filter
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    # Get total count
    total = query.count()

    # Apply pagination and ordering (newest first)
    audit_logs = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset).all()

    # Build response with user info
    items = []
    for log in audit_logs:
        log_dict = AuditLogResponse.model_validate(log).model_dump()
        if log.user:
            log_dict["user_email"] = log.user.email
            log_dict["user_username"] = log.user.username
        items.append(AuditLogResponse(**log_dict))

    return PaginatedAuditLogsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )
