"""
Audit Service for logging all important system actions

This service provides centralized audit logging for tracking:
- Token purchases and revocations
- User updates (admin operations)
- Currency transactions
- Authentication events
"""
from uuid import UUID
from typing import Optional, Dict, Any
from loguru import logger

from sqlalchemy.orm import Session
from fastapi import Request

from app.models.audit_log import AuditLog


class AuditService:
    """
    Service for creating audit log entries

    All audit logs are committed by the caller to ensure atomicity
    with the operation being audited.
    """

    @staticmethod
    def log(
        action: str,
        resource_type: str,
        resource_id: Optional[UUID],
        user_id: Optional[UUID],
        details: Optional[Dict[str, Any]],
        db: Session,
        request: Optional[Request] = None,
    ) -> AuditLog:
        """
        Create an audit log entry

        Args:
            action: Action performed (e.g., "token_purchase", "user_update")
            resource_type: Type of resource affected (e.g., "AccessToken", "User")
            resource_id: UUID of the resource affected (if applicable)
            user_id: UUID of the user performing the action (None for system actions)
            details: Additional context as JSON (e.g., {"duration_hours": 24, "cost": 18.00})
            db: Database session
            request: FastAPI Request object for extracting IP and user agent (optional)

        Returns:
            Created AuditLog instance (not yet committed)

        Example:
            ```python
            AuditService.log(
                action="token_purchase",
                resource_type="AccessToken",
                resource_id=token.id,
                user_id=user.id,
                details={"duration_hours": 24, "cost_znc": 18.00, "scope": "full"},
                db=db,
                request=request
            )
            db.commit()  # Commit with the main operation
            ```
        """
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )

        db.add(audit_log)

        logger.info(
            f"Audit: {action} on {resource_type} "
            f"(resource_id={resource_id}, user_id={user_id})"
        )

        return audit_log

    @staticmethod
    def log_token_purchase(
        token_id: UUID,
        user_id: UUID,
        duration_hours: int,
        cost_znc: float,
        scope: str,
        db: Session,
        request: Optional[Request] = None,
    ) -> AuditLog:
        """
        Log token purchase action

        Convenience method for logging token purchases with standard format.
        """
        return AuditService.log(
            action="token_purchase",
            resource_type="AccessToken",
            resource_id=token_id,
            user_id=user_id,
            details={
                "duration_hours": duration_hours,
                "cost_znc": cost_znc,
                "scope": scope,
            },
            db=db,
            request=request,
        )

    @staticmethod
    def log_token_revoke(
        token_id: UUID,
        user_id: UUID,
        refund_amount: float,
        force_revoke: bool,
        db: Session,
        request: Optional[Request] = None,
    ) -> AuditLog:
        """
        Log token revocation action

        Convenience method for logging token revocations with standard format.
        """
        return AuditService.log(
            action="token_revoke" if not force_revoke else "admin_force_revoke",
            resource_type="AccessToken",
            resource_id=token_id,
            user_id=user_id,
            details={
                "refund_amount": refund_amount,
                "force_revoke": force_revoke,
            },
            db=db,
            request=request,
        )

    @staticmethod
    def log_user_update(
        target_user_id: UUID,
        admin_user_id: UUID,
        changed_fields: Dict[str, Any],
        db: Session,
        request: Optional[Request] = None,
    ) -> AuditLog:
        """
        Log user update action (admin operation)

        Convenience method for logging admin user updates with standard format.
        """
        return AuditService.log(
            action="admin_user_update",
            resource_type="User",
            resource_id=target_user_id,
            user_id=admin_user_id,
            details={"changed_fields": changed_fields},
            db=db,
            request=request,
        )

    @staticmethod
    def log_currency_transaction(
        transaction_id: UUID,
        user_id: UUID,
        transaction_type: str,
        amount: float,
        payment_id: Optional[str],
        db: Session,
        request: Optional[Request] = None,
    ) -> AuditLog:
        """
        Log currency transaction action

        Convenience method for logging currency transactions with standard format.
        """
        return AuditService.log(
            action=f"currency_{transaction_type.lower()}",
            resource_type="Transaction",
            resource_id=transaction_id,
            user_id=user_id,
            details={
                "transaction_type": transaction_type,
                "amount": amount,
                "payment_id": payment_id,
            },
            db=db,
            request=request,
        )

    @staticmethod
    def log_auth_event(
        action: str,
        user_id: Optional[UUID],
        success: bool,
        details: Optional[Dict[str, Any]],
        db: Session,
        request: Optional[Request] = None,
    ) -> AuditLog:
        """
        Log authentication event

        Convenience method for logging authentication events with standard format.
        """
        return AuditService.log(
            action=f"auth_{action}",
            resource_type="User",
            resource_id=user_id,
            user_id=user_id,
            details={"success": success, **(details or {})},
            db=db,
            request=request,
        )
