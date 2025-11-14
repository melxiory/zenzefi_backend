"""
Audit Log Cleanup Background Task

Implements retention policy for audit logs (30 days).
Runs daily at 3 AM to delete old audit logs.
"""
from datetime import datetime, timezone, timedelta
from loguru import logger

from app.core.database import get_db
from app.models.audit_log import AuditLog


def cleanup_old_audit_logs(retention_days: int = 30):
    """
    Delete audit logs older than retention_days

    This function is scheduled to run daily at 3 AM to maintain
    a 30-day audit trail while preventing unbounded database growth.

    Args:
        retention_days: Number of days to retain audit logs (default: 30)

    Returns:
        Number of deleted audit logs
    """
    db = next(get_db())

    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Count before deletion
        count_before = db.query(AuditLog).filter(
            AuditLog.created_at < cutoff_date
        ).count()

        if count_before == 0:
            logger.info(f"No audit logs older than {retention_days} days to clean up")
            return 0

        # Delete old logs
        deleted = db.query(AuditLog).filter(
            AuditLog.created_at < cutoff_date
        ).delete(synchronize_session=False)

        db.commit()

        logger.info(
            f"Audit cleanup: deleted {deleted} audit logs older than {retention_days} days "
            f"(cutoff: {cutoff_date.isoformat()})"
        )

        return deleted

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to clean up old audit logs: {e}")
        raise

    finally:
        db.close()
