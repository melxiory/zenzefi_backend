from datetime import datetime, timezone
from loguru import logger

from fastapi import APIRouter, Request, Response, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.core.permissions import validate_path_access
from app.services.token_service import TokenService
from app.services.proxy_service import ProxyService
from app.services.session_service import SessionService
from app.exceptions import DeviceConflictError

router = APIRouter()


@router.get("/status", status_code=status.HTTP_200_OK)
async def proxy_status(
    db: Session = Depends(get_db),
    x_access_token: str | None = Header(None, alias="X-Access-Token"),
):
    """
    Check proxy connection status and token validity (read-only, does NOT activate token)

    Authentication:
        Header: X-Access-Token (required)

    Returns:
        Connection status and token information
        - For non-activated tokens: expires_at is null, is_activated is false
        - For activated tokens: expires_at is set, time_remaining_seconds calculated

    Raises:
        HTTPException: If token is invalid or expired
    """
    if not x_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: provide X-Access-Token header"
        )

    # Check token status WITHOUT activating it
    valid, token_data = TokenService.check_token_status(x_access_token, db)

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    # Build response based on whether token is activated
    response = {
        "connected": True,
        "user_id": token_data["user_id"],
        "token_id": token_data["token_id"],
        "is_activated": token_data["is_activated"],
        "expires_at": token_data["expires_at"],
        "duration_hours": token_data["duration_hours"],
    }

    # Calculate time remaining only for activated tokens
    if token_data["is_activated"] and token_data["expires_at"]:
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        # Ensure timezone-aware comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        time_remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        response["time_remaining_seconds"] = max(0, time_remaining)
        response["status"] = "active"
    else:
        # Token not yet activated
        response["time_remaining_seconds"] = None
        response["status"] = "ready"  # Ready to be activated

    return response


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy_to_zenzefi(
    request: Request,
    response: Response,
    path: str,
    db: Session = Depends(get_db),
    x_access_token: str | None = Header(None, alias="X-Access-Token"),
):
    """
    Proxy to Zenzefi with X-Access-Token header authentication

    Authentication:
        Header: X-Access-Token (required)

    **IMPORTANT:** This is a catch-all route that must be defined LAST!
    It forwards requests to the target Zenzefi server.

    **Usage:**
    - Empty path proxies to root: GET /api/v1/proxy/ → https://zenzefi.melxiory.ru/
    - Specific paths: GET /api/v1/proxy/certificates/filter → https://zenzefi.melxiory.ru/certificates/filter

    **Example:**
        GET /api/v1/proxy/certificates/filter
        Headers: X-Access-Token: your_token
        → Forwards to https://zenzefi.melxiory.ru/certificates/filter

    **curl example:**
        curl -H "X-Access-Token: your_token" \\
             http://localhost:8000/api/v1/proxy/certificates/filter

    Args:
        path: URL path to proxy (e.g., "" for root, "certificates/filter")
        request: FastAPI Request object
        db: Database session
        x_access_token: Token from header (required)

    Returns:
        Proxied response from Zenzefi server (JSON, etc.)

    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    # ============ DEVICE IDENTIFICATION ============
    # Extract X-Device-ID header (обязателен для device conflict detection)
    device_id = request.headers.get("x-device-id")

    if not device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Device identification required: X-Device-ID header missing. "
                "Please update your Desktop Client to the latest version."
            ),
        )

    # Базовая валидация device_id
    if len(device_id) < 8 or len(device_id) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Device-ID header format (must be 8-255 characters)",
        )

    # ============ AUTHENTICATION ============
    # Check if token is provided
    if not x_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: provide X-Access-Token header",
        )

    # Validate token
    valid, token_data = TokenService.validate_token(x_access_token, db)

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    # Extract user and token IDs
    user_id = token_data["user_id"]
    token_id = token_data["token_id"]

    # ============ SCOPE-BASED PATH VALIDATION ============
    token_scope = token_data.get("scope", "full")

    # Validate path access based on token scope
    if not validate_path_access(path, token_scope):
        logger.warning(
            f"Access denied: scope='{token_scope}' path='/{path}' "
            f"user_id={user_id} token_id={token_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Access denied: your token scope ('{token_scope}') "
                f"does not allow access to '/{path}'"
            )
        )

    logger.info(
        f"Access granted: scope='{token_scope}' path='/{path}' "
        f"method={request.method} user_id={user_id}"
    )
    # ============ END SCOPE VALIDATION ============

    # ============ SESSION TRACKING WITH DEVICE CONFLICT DETECTION ============
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")

    try:
        SessionService.track_request(
            user_id=user_id,
            token_id=token_id,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            db=db
        )
    except DeviceConflictError as e:
        # DEVICE CONFLICT - токен используется на другом устройстве
        logger.warning(
            f"Device conflict detected: token={token_id}, "
            f"attempted_device={device_id[:16]}..., error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        # Don't fail the request if session tracking fails
        logger.warning(f"Failed to track session: {e}")

    # Proxy request to Zenzefi
    response = await ProxyService.proxy_request(
        request=request, path=path, user_id=user_id, token_id=token_id
    )

    return response
