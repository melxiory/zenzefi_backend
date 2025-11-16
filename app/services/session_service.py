"""
Session tracking service for ProxySession management
"""
from datetime import datetime, timezone, timedelta
from uuid import UUID
from loguru import logger
from sqlalchemy.orm import Session

from app.models.proxy_session import ProxySession
from app.exceptions import DeviceConflictError


class SessionService:
    """Service for managing proxy sessions"""

    @staticmethod
    def track_request(
        user_id: UUID,
        token_id: UUID,
        device_id: str,
        ip_address: str,
        user_agent: str | None,
        bytes_transferred: int = 0,
        db: Session = None
    ) -> ProxySession:
        """
        Track a proxy request by creating or updating session with device conflict detection

        Args:
            user_id: User ID from validated token
            token_id: Access token ID
            device_id: Device identifier (hardware fingerprint)
            ip_address: Client IP address
            user_agent: User-Agent header value
            bytes_transferred: Bytes transferred in this request
            db: Database session

        Returns:
            ProxySession: Created or updated session

        Raises:
            DeviceConflictError: If token is already in use on a different device
            Exception: If database operation fails
        """
        try:
            # Find active session for this token (любой device)
            active_session = db.query(ProxySession).filter(
                ProxySession.token_id == token_id,
                ProxySession.is_active == True
            ).first()

            # DEVICE CONFLICT DETECTION
            if active_session:
                if active_session.device_id != device_id:
                    # Токен используется на ДРУГОМ устройстве - блокировка
                    raise DeviceConflictError(
                        f"Token already in use on device '{active_session.device_id[:8]}...'. "
                        f"Session started at {active_session.started_at.isoformat()}. "
                        f"Wait for session timeout (5 minutes) or stop the other device."
                    )

                # То же устройство - обновить сессию
                active_session.last_activity = datetime.now(timezone.utc)
                active_session.request_count += 1
                active_session.bytes_transferred += bytes_transferred
                # IP может меняться (VPN, Wi-Fi switch)
                active_session.ip_address = ip_address
                active_session.user_agent = user_agent

                db.commit()
                db.refresh(active_session)

                logger.debug(
                    f"Session updated: device={device_id[:16]}..., "
                    f"requests={active_session.request_count}, "
                    f"bytes={active_session.bytes_transferred}"
                )

                return active_session

            # Нет активной сессии - создать новую
            new_session = ProxySession(
                user_id=user_id,
                token_id=token_id,
                device_id=device_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_count=1,
                bytes_transferred=bytes_transferred
            )
            db.add(new_session)
            db.commit()
            db.refresh(new_session)

            logger.info(
                f"New session created: user={user_id}, token={token_id}, "
                f"device={device_id[:16]}..., ip={ip_address}"
            )

            return new_session

        except DeviceConflictError:
            # Propagate device conflict error
            raise
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
    def cleanup_inactive_sessions(db: Session, inactive_minutes: int = 5) -> int:
        """
        Close sessions inactive for more than specified minutes

        Args:
            db: Database session
            inactive_minutes: Minutes of inactivity before closing (default: 5)

        Returns:
            int: Number of sessions closed
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=inactive_minutes)

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
            logger.info(
                f"Cleaned up {count} inactive proxy sessions "
                f"(inactive >{inactive_minutes} minutes)"
            )

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
