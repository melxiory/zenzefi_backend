"""
Session tracking service for ProxySession management
"""
from datetime import datetime, timezone
from uuid import UUID
from loguru import logger
from sqlalchemy.orm import Session

from app.models.proxy_session import ProxySession


class SessionService:
    """Service for managing proxy sessions"""

    @staticmethod
    def track_request(
        user_id: UUID,
        token_id: UUID,
        ip_address: str,
        user_agent: str | None,
        bytes_transferred: int = 0,
        db: Session = None
    ) -> ProxySession:
        """
        Track a proxy request by creating or updating session

        Args:
            user_id: User ID from validated token
            token_id: Access token ID
            ip_address: Client IP address
            user_agent: User-Agent header value
            bytes_transferred: Bytes transferred in this request
            db: Database session

        Returns:
            ProxySession: Created or updated session

        Raises:
            Exception: If database operation fails
        """
        try:
            # Find active session for this user/token combination
            session = db.query(ProxySession).filter(
                ProxySession.user_id == user_id,
                ProxySession.token_id == token_id,
                ProxySession.is_active == True
            ).first()

            if not session:
                # Create new session
                session = ProxySession(
                    user_id=user_id,
                    token_id=token_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_count=1,
                    bytes_transferred=bytes_transferred
                )
                db.add(session)
                logger.info(
                    f"Created new proxy session: "
                    f"user_id={user_id}, token_id={token_id}, ip={ip_address}"
                )
            else:
                # Update existing session
                session.last_activity = datetime.now(timezone.utc)
                session.request_count += 1
                session.bytes_transferred += bytes_transferred

            db.commit()
            db.refresh(session)

            return session

        except Exception as e:
            logger.error(f"Error tracking proxy session: {e}")
            db.rollback()
            raise

    @staticmethod
    def close_session(session_id: UUID, db: Session) -> bool:
        """
        Close an active proxy session

        Args:
            session_id: Session ID to close
            db: Database session

        Returns:
            bool: True if session was closed, False if not found
        """
        session = db.query(ProxySession).filter(
            ProxySession.id == session_id,
            ProxySession.is_active == True
        ).first()

        if not session:
            return False

        session.is_active = False
        session.ended_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Closed proxy session: {session_id}")
        return True

    @staticmethod
    def cleanup_inactive_sessions(db: Session, inactive_hours: int = 1) -> int:
        """
        Close sessions inactive for more than specified hours

        Args:
            db: Database session
            inactive_hours: Hours of inactivity before closing (default: 1)

        Returns:
            int: Number of sessions closed
        """
        from datetime import timedelta

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=inactive_hours)

        sessions = db.query(ProxySession).filter(
            ProxySession.is_active == True,
            ProxySession.last_activity < cutoff_time
        ).all()

        count = 0
        for session in sessions:
            session.is_active = False
            session.ended_at = datetime.now(timezone.utc)
            count += 1

        db.commit()

        if count > 0:
            logger.info(f"Cleaned up {count} inactive proxy sessions (>{inactive_hours}h)")

        return count

    @staticmethod
    def get_active_sessions(user_id: UUID | None = None, db: Session = None) -> list[ProxySession]:
        """
        Get active proxy sessions

        Args:
            user_id: Optional user ID to filter by
            db: Database session

        Returns:
            list[ProxySession]: Active sessions
        """
        query = db.query(ProxySession).filter(ProxySession.is_active == True)

        if user_id:
            query = query.filter(ProxySession.user_id == user_id)

        return query.order_by(ProxySession.last_activity.desc()).all()
