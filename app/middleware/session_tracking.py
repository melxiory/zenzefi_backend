"""
ProxySession tracking middleware

Automatically tracks proxy sessions by creating/updating session records
on each proxy request. Sessions are created on first request and updated
on subsequent requests with request count and last activity timestamp.
"""
from datetime import datetime, timezone
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response

from app.core.database import get_db
from app.models.proxy_session import ProxySession


class ProxySessionMiddleware(BaseHTTPMiddleware):
    """
    Middleware for tracking proxy sessions

    Automatically creates or updates ProxySession records for all requests
    to /api/v1/proxy endpoints. Tracks request count and last activity.

    Requirements:
    - Request must have state.user_id and state.token_id set by auth
    - Only tracks requests to /api/v1/proxy/* paths
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and track session if it's a proxy request

        Args:
            request: FastAPI Request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response from next handler
        """
        # Skip non-proxy requests
        if not request.url.path.startswith("/api/v1/proxy"):
            return await call_next(request)

        # Skip if auth data not available (will be handled by auth error)
        if not hasattr(request.state, "user_id") or not hasattr(request.state, "token_id"):
            return await call_next(request)

        # Extract session info
        user_id = request.state.user_id
        token_id = request.state.token_id
        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")

        # Get database session
        db = next(get_db())

        try:
            # Find or create session
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
                    user_agent=user_agent
                )
                db.add(session)
                logger.info(f"Created new proxy session: user_id={user_id}, token_id={token_id}, ip={ip_address}")

            # Process request
            response = await call_next(request)

            # Update session stats
            session.last_activity = datetime.now(timezone.utc)
            session.request_count += 1

            # Track bytes transferred (if available)
            if hasattr(response, "body"):
                # For streamed responses, body might not be available
                try:
                    body_length = len(response.body) if response.body else 0
                    session.bytes_transferred += body_length
                except:
                    pass

            db.commit()

            return response

        except Exception as e:
            logger.error(f"Error tracking proxy session: {e}")
            db.rollback()
            # Don't fail the request if session tracking fails
            return await call_next(request)
        finally:
            db.close()
