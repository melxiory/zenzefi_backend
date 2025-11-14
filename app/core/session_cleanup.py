"""
Background task for cleaning up inactive proxy sessions

Automatically closes sessions that have been inactive for more than 1 hour.
This task should be scheduled to run every 15 minutes.
"""
from loguru import logger
from app.core.database import get_db
from app.services.session_service import SessionService


def cleanup_inactive_sessions():
    """
    Close sessions inactive for more than 1 hour

    This function is called by APScheduler every 15 minutes.
    Sessions with last_activity > 1 hour ago are marked as inactive.
    """
    db = next(get_db())

    try:
        count = SessionService.cleanup_inactive_sessions(db, inactive_hours=1)

        if count > 0:
            logger.info(f"Session cleanup: closed {count} inactive sessions")
        else:
            logger.debug("Session cleanup: no inactive sessions to close")

    except Exception as e:
        logger.error(f"Error during session cleanup: {e}")
        db.rollback()
    finally:
        db.close()
