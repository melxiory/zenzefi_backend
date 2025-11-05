from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response, Depends, Header, Cookie, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.services.token_service import TokenService
from app.services.proxy_service import ProxyService

router = APIRouter()


@router.post("/authenticate", status_code=status.HTTP_200_OK)
async def authenticate_with_cookie(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Validate token and set secure HTTP-only cookie

    Body:
        {"token": "your_access_token_here"}

    Returns:
        Authentication status with cookie information

    Raises:
        HTTPException: If token is invalid or expired
    """
    # Read token from request body
    body = await request.json()
    token = body.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is required in request body"
        )

    # Validate token (read-only check, does NOT activate)
    valid, token_data = TokenService.check_token_status(token, db)

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token"
        )

    # Calculate cookie max_age based on token expiration
    # For non-activated tokens, use duration_hours
    if token_data["is_activated"] and token_data["expires_at"]:
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    else:
        # Token not yet activated - use full duration
        max_age = token_data["duration_hours"] * 3600

    # Set secure HTTP-only cookie
    response.set_cookie(
        key="zenzefi_access_token",
        value=token,
        max_age=max_age,  # Lifetime in seconds
        httponly=True,    # JavaScript cannot read (XSS protection)
        secure=settings.COOKIE_SECURE,      # HTTPS only in production
        samesite=settings.COOKIE_SAMESITE,  # Cross-site policy
        path="/",  # Cookie for entire domain (required for proxy to work)
        domain=None  # Cookie for current domain
    )

    return {
        "authenticated": True,
        "user_id": token_data["user_id"],
        "token_id": token_data["token_id"],
        "is_activated": token_data["is_activated"],
        "expires_at": token_data["expires_at"],
        "cookie_set": True,
        "cookie_max_age": max_age,
        "time_remaining_seconds": max_age
    }


@router.delete("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    """
    Delete authentication cookie (logout)

    Returns:
        Logout status
    """
    response.delete_cookie(
        key="zenzefi_access_token",
        path="/"
    )

    return {
        "logged_out": True,
        "message": "Cookie deleted successfully"
    }


@router.get("/status", status_code=status.HTTP_200_OK)
async def proxy_status(
    db: Session = Depends(get_db),
    zenzefi_access_token: str | None = Cookie(None, alias="zenzefi_access_token"),
    x_access_token: str | None = Header(None, alias="X-Access-Token"),
):
    """
    Check proxy connection status and token validity (read-only, does NOT activate token)

    Authentication (priority order):
        1. Cookie: zenzefi_access_token
        2. Header: X-Access-Token

    Returns:
        Connection status and token information
        - For non-activated tokens: expires_at is null, is_activated is false
        - For activated tokens: expires_at is set, time_remaining_seconds calculated

    Raises:
        HTTPException: If token is invalid or expired
    """
    # Priority: Cookie > Header
    access_token = zenzefi_access_token or x_access_token

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: provide cookie or X-Access-Token header"
        )

    # Check token status WITHOUT activating it
    valid, token_data = TokenService.check_token_status(access_token, db)

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    # Build response based on whether token is activated
    response = {
        "connected": True,
        "authenticated_via": "cookie" if zenzefi_access_token else "header",
        "user_id": token_data["user_id"],
        "token_id": token_data["token_id"],
        "is_activated": token_data["is_activated"],
        "expires_at": token_data["expires_at"],
        "duration_hours": token_data["duration_hours"],
    }

    # Calculate time remaining only for activated tokens
    if token_data["is_activated"] and token_data["expires_at"]:
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        time_remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
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

    Authentication (priority order):
        1. Query param: ?token=<access_token>
        2. Cookie: zenzefi_access_token

    Args:
        websocket: WebSocket connection
        path: URL path to proxy
        db: Database session

    Note:
        X-Access-Token is extracted from query parameters or cookies since
        WebSocket connections from browsers don't support custom headers
    """
    # Extract token from query parameters or cookies (priority: query > cookie)
    x_access_token = websocket.query_params.get("token") or websocket.cookies.get("zenzefi_access_token")

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
    response: Response,
    path: str,
    db: Session = Depends(get_db),
    # Read token from Cookie OR header (backward compatibility)
    zenzefi_access_token: str | None = Cookie(None, alias="zenzefi_access_token"),
    x_access_token: str | None = Header(None, alias="X-Access-Token"),
):
    """
    Proxy to Zenzefi with Cookie and Header authentication support

    Authentication (priority order):
        1. Cookie: zenzefi_access_token
        2. Header: X-Access-Token

    **IMPORTANT:** This is a catch-all route that must be defined LAST!
    It forwards requests to the target Zenzefi server, including HTML content.

    **Usage:**
    - Empty path proxies to root: GET /api/v1/proxy/ → https://zenzefi.melxiory.ru/
    - Specific paths: GET /api/v1/proxy/api/users → https://zenzefi.melxiory.ru/api/users

    **Examples:**
        Browser/Desktop Client (with cookie):
        GET http://localhost:8000/api/v1/proxy/
        Cookie: zenzefi_access_token=your_token
        → Returns Zenzefi web interface HTML

        API Request (with header):
        GET /api/v1/proxy/api/users/profile
        Headers: X-Access-Token: your_token
        → Forwards to https://zenzefi.melxiory.ru/api/users/profile

    **curl examples:**
        # With cookie
        curl -b cookies.txt http://localhost:8000/api/v1/proxy/api/users/me

        # With header
        curl -H "X-Access-Token: your_token" \\
             http://localhost:8000/api/v1/proxy/api/users/me

    Args:
        path: URL path to proxy (e.g., "" for root, "api/users/me", "sessions/create")
        request: FastAPI Request object
        db: Database session
        zenzefi_access_token: Token from cookie (optional)
        x_access_token: Token from header (optional)

    Returns:
        Proxied response from Zenzefi server (HTML, JSON, etc.)

    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    # Skip source maps - browser doesn't send custom headers for them
    if path.endswith('.map'):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source maps not available through proxy"
        )

    # Check for token in query parameters (for initial authentication from desktop client)
    query_token = request.query_params.get("token")

    if query_token:
        # Validate token (read-only check)
        valid, token_data = TokenService.check_token_status(query_token, db)

        if not valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token in query parameter"
            )

        # Calculate cookie max_age based on token expiration
        if token_data["is_activated"] and token_data["expires_at"]:
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        else:
            # Token not yet activated - use full duration
            max_age = token_data["duration_hours"] * 3600

        # Redirect to same path without token parameter
        # ВАЖНО: Если запрос пришел через локальный прокси (X-Local-Url),
        # редиректим на URL прокси, а не на backend URL
        local_url = request.headers.get("X-Local-Url")
        if local_url:
            # Desktop client - redirect to local proxy URL
            # path переменная содержит путь БЕЗ префикса /api/v1/proxy (это {path:path} из роута)
            # Формируем правильный URL для редиректа на локальный прокси
            redirect_url = f"{local_url.rstrip('/')}/{path}"
        else:
            # Direct access - redirect to same backend URL without query params
            redirect_url = str(request.url).split("?")[0]

        # ВАЖНО: Создаем RedirectResponse и устанавливаем cookie на НЕМ
        redirect_response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

        # Устанавливаем cookie на redirect response
        redirect_response.set_cookie(
            key="zenzefi_access_token",
            value=query_token,
            max_age=max_age,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            path="/",
            domain=None
        )

        return redirect_response

    # Priority: Cookie > Header
    access_token = zenzefi_access_token or x_access_token

    # Check if token is provided
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: provide cookie or X-Access-Token header",
        )

    # Validate token
    valid, token_data = TokenService.validate_token(access_token, db)

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
