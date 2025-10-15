import httpx
from fastapi import Request, Response
from loguru import logger

from app.config import settings


class ProxyService:
    """Service for proxying requests to Zenzefi server"""

    @staticmethod
    async def proxy_request(
        request: Request, path: str, user_id: str, token_id: str
    ) -> Response:
        """
        Proxy HTTP request to Zenzefi server

        Args:
            request: FastAPI Request object
            path: URL path to proxy
            user_id: Authenticated user ID
            token_id: Access token ID (for logging)

        Returns:
            Response: Proxied response from Zenzefi server
        """
        # Build target URL
        target_url = f"{settings.ZENZEFI_TARGET_URL}/{path}"

        # Copy headers (exclude certain headers)
        headers = {}
        for key, value in request.headers.items():
            key_lower = key.lower()
            if key_lower not in [
                "host",
                "x-access-token",
                "content-length",
                "transfer-encoding",
            ]:
                headers[key] = value

        # Add forwarding headers
        headers.update(
            {
                "X-Forwarded-For": request.client.host if request.client else "unknown",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": request.headers.get("host", "unknown"),
                "X-User-Id": user_id,  # For Zenzefi server logging
                "X-Token-Id": token_id,
            }
        )

        try:
            async with httpx.AsyncClient(
                verify=False,  # Skip SSL verification for internal VPN
                timeout=30.0,
                follow_redirects=False,
            ) as client:
                # Read request body
                body = await request.body()

                # Log request
                logger.info(
                    f"Proxy: {request.method} {target_url} | "
                    f"User: {user_id} | Token: {token_id}"
                )

                # Execute proxied request
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    params=request.query_params,
                )

                # Prepare response headers
                response_headers = {}
                for key, value in response.headers.items():
                    key_lower = key.lower()
                    # Skip hop-by-hop headers
                    if key_lower not in [
                        "connection",
                        "keep-alive",
                        "transfer-encoding",
                        "content-length",
                    ]:
                        response_headers[key] = value

                # Log response
                logger.info(
                    f"Proxy response: {response.status_code} | "
                    f"Size: {len(response.content)} bytes"
                )

                # Return proxied response
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=response_headers,
                    media_type=response.headers.get("content-type"),
                )

        except httpx.TimeoutException:
            logger.error(f"Proxy timeout: {target_url}")
            return Response(
                content="Gateway Timeout: Zenzefi server did not respond",
                status_code=504,
            )

        except httpx.RequestError as e:
            logger.error(f"Proxy error: {e}")
            return Response(
                content=f"Bad Gateway: Unable to reach Zenzefi server - {str(e)}",
                status_code=502,
            )

        except Exception as e:
            logger.exception(f"Unexpected proxy error: {e}")
            return Response(content="Internal Server Error", status_code=500)
