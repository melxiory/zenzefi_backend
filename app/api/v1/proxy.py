from datetime import datetime

from fastapi import APIRouter, Request, Response, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.token_service import TokenService
from app.services.proxy_service import ProxyService

router = APIRouter()


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy_to_zenzefi(
    path: str,
    request: Request,
    x_access_token: str = Header(..., alias="X-Access-Token"),
    db: Session = Depends(get_db),
):
    """
    Proxy all requests to Zenzefi server with token validation

    Args:
        path: URL path to proxy
        request: FastAPI Request object
        x_access_token: Access token from header
        db: Database session

    Returns:
        Proxied response from Zenzefi server

    Raises:
        HTTPException: If token is invalid or expired
    """
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


@router.get("/status", status_code=status.HTTP_200_OK)
async def proxy_status(
    x_access_token: str = Header(..., alias="X-Access-Token"),
    db: Session = Depends(get_db),
):
    """
    Check proxy connection status and token validity

    Args:
        x_access_token: Access token from header
        db: Database session

    Returns:
        Connection status and token information

    Raises:
        HTTPException: If token is invalid or expired
    """
    # Validate token
    valid, token_data = TokenService.validate_token(x_access_token, db)

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    expires_at = datetime.fromisoformat(token_data["expires_at"])
    time_remaining = int((expires_at - datetime.utcnow()).total_seconds())

    return {
        "connected": True,
        "user_id": token_data["user_id"],
        "token_id": token_data["token_id"],
        "time_remaining_seconds": max(0, time_remaining),
        "expires_at": token_data["expires_at"],
        "status": "active",
    }
