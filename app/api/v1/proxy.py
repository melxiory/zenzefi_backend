from datetime import datetime

from fastapi import APIRouter, Request, Response, Depends, Header, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.token_service import TokenService
from app.services.proxy_service import ProxyService

router = APIRouter()


@router.get("/status", status_code=status.HTTP_200_OK)
async def proxy_status(
    x_access_token: str = Header(..., alias="X-Access-Token"),
    db: Session = Depends(get_db),
):
    """
    Check proxy connection status and token validity (read-only, does NOT activate token)

    This endpoint checks if a token is valid WITHOUT activating it. This allows
    clients to check token status before deciding to connect through the proxy.

    Args:
        x_access_token: Access token from header
        db: Database session

    Returns:
        Connection status and token information
        - For non-activated tokens: expires_at is null, is_activated is false
        - For activated tokens: expires_at is set, time_remaining_seconds calculated

    Raises:
        HTTPException: If token is invalid or expired
    """
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
        time_remaining = int((expires_at - datetime.utcnow()).total_seconds())
        response["time_remaining_seconds"] = max(0, time_remaining)
        response["status"] = "active"
    else:
        # Token not yet activated
        response["time_remaining_seconds"] = None
        response["status"] = "ready"  # Ready to be activated

    return response


@router.websocket("/{path:path}")
async def websocket_proxy(
    websocket: WebSocket,
    path: str,
    db: Session = Depends(get_db),
):
    """
    WebSocket proxy to Zenzefi server

    **IMPORTANT:** This handles WebSocket connections (e.g., /ws/info)

    Args:
        websocket: WebSocket connection
        path: URL path to proxy
        db: Database session

    Note:
        X-Access-Token is extracted from query parameters since
        WebSocket connections from browsers don't support custom headers
    """
    # Extract token from query parameters or cookies
    x_access_token = websocket.query_params.get("token") or websocket.cookies.get("X-Access-Token")

    if not x_access_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing access token")
        return

    # Validate token
    valid, token_data = TokenService.validate_token(x_access_token, db)

    if not valid:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
        return

    # Extract user and token IDs
    user_id = token_data["user_id"]
    token_id = token_data["token_id"]

    # Proxy WebSocket to Zenzefi
    await ProxyService.proxy_websocket(
        websocket=websocket, path=path, user_id=user_id, token_id=token_id
    )


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy_to_zenzefi(
    request: Request,
    path: str,
    x_access_token: str = Header(None, alias="X-Access-Token"),
    db: Session = Depends(get_db),
):
    """
    Proxy all requests to Zenzefi server with token validation

    **IMPORTANT:** This is a catch-all route that must be defined LAST!
    It forwards requests to the target Zenzefi server, including HTML content.

    **Usage:**
    - Empty path proxies to root: GET /api/v1/proxy/ → https://zenzefi.melxiory.ru/
    - Specific paths: GET /api/v1/proxy/api/users → https://zenzefi.melxiory.ru/api/users

    **Examples:**
        Browser/Desktop Client:
        GET http://localhost:8000/api/v1/proxy/
        Headers: X-Access-Token: your_token
        → Returns Zenzefi web interface HTML

        API Request:
        GET /api/v1/proxy/api/users/profile
        Headers: X-Access-Token: your_token
        → Forwards to https://zenzefi.melxiory.ru/api/users/profile

    **curl example:**
        curl -H "X-Access-Token: your_token" \\
             http://localhost:8000/api/v1/proxy/api/users/me

    Args:
        path: URL path to proxy (e.g., "" for root, "api/users/me", "sessions/create")
        request: FastAPI Request object
        x_access_token: Access token from header (optional for .map files)
        db: Database session

    Returns:
        Proxied response from Zenzefi server (HTML, JSON, etc.)

    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    # Allow empty path for root URL proxying
    # Empty path will proxy to the root of Zenzefi server

    # Skip source maps - browser doesn't send custom headers for them
    if path.endswith('.map'):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source maps not available through proxy"
        )

    # Check if token is provided
    if not x_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Access-Token header is required",
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

    # Proxy request to Zenzefi
    response = await ProxyService.proxy_request(
        request=request, path=path, user_id=user_id, token_id=token_id
    )

    return response
