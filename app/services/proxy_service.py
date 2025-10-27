import httpx
import re
import base64
import asyncio
from fastapi import Request, Response, WebSocket
from loguru import logger
import websockets

from app.config import settings
from app.services.content_rewriter import get_content_rewriter


class ProxyService:
    """Service for proxying requests to Zenzefi server"""

    # Lazy initialization для ContentRewriter (singleton)
    _content_rewriter = None

    @classmethod
    def get_content_rewriter(cls):
        """Lazy initialization ContentRewriter"""
        if cls._content_rewriter is None:
            cls._content_rewriter = get_content_rewriter(
                upstream_url=settings.ZENZEFI_TARGET_URL,
                backend_url=settings.BACKEND_URL
            )
        return cls._content_rewriter

    @staticmethod
    async def proxy_websocket(
        websocket: WebSocket, path: str, user_id: str, token_id: str
    ) -> None:
        """
        Proxy WebSocket connection to Zenzefi server

        Args:
            websocket: FastAPI WebSocket connection
            path: URL path to proxy
            user_id: Authenticated user ID
            token_id: Access token ID (for logging)
        """
        # Build target WebSocket URL
        ws_url = f"wss://zenzefi.melxiory.ru/{path}" if path else "wss://zenzefi.melxiory.ru"

        # Remove query string from path for logging
        log_path = path.split('?')[0] if path else "/"

        logger.info(
            f"WebSocket: {ws_url} | "
            f"User: {user_id} | Token: {token_id}"
        )

        # Accept the WebSocket connection from client
        await websocket.accept()

        # Prepare headers for upstream WebSocket
        headers = {}

        # Add Basic Auth if configured
        if settings.ZENZEFI_BASIC_AUTH_USER and settings.ZENZEFI_BASIC_AUTH_PASSWORD:
            credentials = f"{settings.ZENZEFI_BASIC_AUTH_USER}:{settings.ZENZEFI_BASIC_AUTH_PASSWORD}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
            logger.debug("Added HTTP Basic Auth for WebSocket")

        # Add custom headers
        headers.update({
            "X-User-Id": user_id,
            "X-Token-Id": token_id,
        })

        try:
            # Connect to upstream WebSocket
            async with websockets.connect(
                ws_url,
                extra_headers=headers,
                ssl=None,  # Skip SSL verification for internal VPN
                max_size=10 * 1024 * 1024,  # 10MB message size limit
            ) as upstream_ws:

                logger.debug(f"WebSocket connected: {log_path}")

                async def forward_to_upstream():
                    """Forward messages from client to upstream server"""
                    try:
                        while True:
                            # Receive from client
                            data = await websocket.receive()

                            if "text" in data:
                                await upstream_ws.send(data["text"])
                            elif "bytes" in data:
                                await upstream_ws.send(data["bytes"])
                            else:
                                # Connection closed
                                break
                    except Exception as e:
                        logger.debug(f"Forward to upstream ended: {e}")

                async def forward_to_client():
                    """Forward messages from upstream server to client"""
                    try:
                        async for message in upstream_ws:
                            if isinstance(message, str):
                                await websocket.send_text(message)
                            elif isinstance(message, bytes):
                                await websocket.send_bytes(message)
                    except Exception as e:
                        logger.debug(f"Forward to client ended: {e}")

                # Run both forwarding tasks concurrently
                await asyncio.gather(
                    forward_to_upstream(),
                    forward_to_client(),
                    return_exceptions=True
                )

        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
        except Exception as e:
            logger.exception(f"Unexpected WebSocket error: {e}")
        finally:
            try:
                await websocket.close()
            except:
                pass
            logger.debug(f"WebSocket closed: {log_path}")

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
        # Read X-Local-Url header from desktop client (if present)
        # Desktop client sends its local proxy URL (e.g., https://127.0.0.1:61000)
        # This URL will be used for content rewriting instead of /api/v1/proxy prefix
        local_url = request.headers.get('X-Local-Url')
        use_desktop_client = local_url is not None

        if use_desktop_client:
            local_url = local_url.rstrip('/')
            logger.debug(f"Desktop client detected: X-Local-Url = {local_url}")

        # Build target URL
        target_url = f"{settings.ZENZEFI_TARGET_URL}/{path}" if path else settings.ZENZEFI_TARGET_URL

        # Copy headers (exclude certain headers)
        headers = {}
        for key, value in request.headers.items():
            key_lower = key.lower()
            if key_lower not in [
                "host",
                "x-access-token",
                "x-local-url",  # Desktop client header, don't forward to upstream
                "content-length",
                "transfer-encoding",
            ]:
                headers[key] = value

        # Set proper Host header for target server
        from urllib.parse import urlparse
        parsed_target = urlparse(settings.ZENZEFI_TARGET_URL)
        headers["Host"] = parsed_target.netloc

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

        # Add HTTP Basic Auth if configured and not already present
        if settings.ZENZEFI_BASIC_AUTH_USER and settings.ZENZEFI_BASIC_AUTH_PASSWORD:
            if "authorization" not in headers:
                credentials = f"{settings.ZENZEFI_BASIC_AUTH_USER}:{settings.ZENZEFI_BASIC_AUTH_PASSWORD}"
                encoded = base64.b64encode(credentials.encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"
                logger.debug("Added HTTP Basic Auth from config")

        try:
            async with httpx.AsyncClient(
                verify=False,  # Skip SSL verification for internal VPN
                timeout=30.0,
                follow_redirects=True,  # Follow redirects to get final content
            ) as client:
                # Read request body
                body = await request.body()

                # Log request
                logger.info(
                    f"Proxy: {request.method} {target_url} | "
                    f"User: {user_id} | Token: {token_id}"
                )
                logger.debug(f"Request headers to Zenzefi: {dict(headers)}")

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
                    # Skip hop-by-hop headers and content-encoding
                    # (httpx auto-decompresses, so we send raw content)
                    if key_lower not in [
                        "connection",
                        "keep-alive",
                        "transfer-encoding",
                        "content-length",
                        "content-encoding",  # Exclude to prevent double-decompression
                    ]:
                        response_headers[key] = value

                # Add CORS headers explicitly
                response_headers.update({
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Credentials": "true",
                })

                # Log response
                logger.info(
                    f"Proxy response: {response.status_code} | "
                    f"Size: {len(response.content)} bytes"
                )

                # Get or create content rewriter instance
                # For desktop client, create dynamic rewriter with local_url
                # For direct API access, use singleton with backend_url
                if use_desktop_client:
                    from app.services.content_rewriter import ContentRewriter
                    content_rewriter = ContentRewriter(
                        upstream_url=settings.ZENZEFI_TARGET_URL,
                        backend_url=local_url
                    )
                    logger.debug(f"Created dynamic ContentRewriter for desktop client: {local_url}")
                else:
                    content_rewriter = ProxyService.get_content_rewriter()

                # Rewrite content to fix relative URLs
                content = response.content
                content_type = response.headers.get("content-type", "")

                # Rewrite JavaScript to fix hardcoded URLs (for SockJS /ws/info)
                # Only needed for direct API access, not desktop client
                if "javascript" in content_type and not use_desktop_client:
                    try:
                        js_content = content.decode('utf-8')
                        # Replace /ws/info with /api/v1/proxy/ws/info in JS
                        if '/ws/info' in js_content:
                            js_content = js_content.replace('"/ws/info', '"/api/v1/proxy/ws/info')
                            js_content = js_content.replace("'/ws/info", "'/api/v1/proxy/ws/info")
                            content = js_content.encode('utf-8')
                            logger.debug(f"Rewrote /ws/info URLs in JavaScript file: {request.path}")
                    except Exception as e:
                        logger.warning(f"Failed to rewrite JS content: {e}")

                # Rewrite HTML only - use <base> tag to set base URL
                if "text/html" in content_type:
                    try:
                        text_content = content.decode('utf-8')

                        # Inject a script to intercept fetch/XMLHttpRequest/WebSocket
                        # This rewrites URLs at runtime without breaking JavaScript syntax

                        # Extract X-Access-Token from request cookies for storage
                        access_token = ""
                        for cookie in request.headers.get('cookie', '').split(';'):
                            if 'X-Access-Token' in cookie:
                                access_token = cookie.split('=')[1].strip()
                                break

                        # If not in cookies, try to get from header passed during initial request
                        # (this won't work in browser, but useful for understanding flow)
                        if not access_token:
                            access_token = request.headers.get('X-Access-Token', '')

                        # For desktop client, don't add prefix (desktop client handles routing)
                        # For direct access, use /api/v1/proxy prefix
                        proxy_prefix = '' if use_desktop_client else '/api/v1/proxy'

                        proxy_script = f"""
<script type="text/javascript">
// IMMEDIATE EXECUTION - Install interceptors BEFORE any other code runs
(function() {{
    console.log('[Zenzefi Proxy] Script loaded - installing interceptors immediately!');
    const proxyPrefix = '{proxy_prefix}';

    // Store access token for WebSocket use
    const ACCESS_TOKEN = '{access_token}';
    console.log('[Zenzefi Proxy] Token available:', !!ACCESS_TOKEN);
    if (ACCESS_TOKEN) {{
        sessionStorage.setItem('X-Access-Token', ACCESS_TOKEN);
        console.log('[Zenzefi Proxy] Token stored in sessionStorage');
    }}

    // Get access token
    function getAccessToken() {{
        return sessionStorage.getItem('X-Access-Token') || localStorage.getItem('X-Access-Token') || ACCESS_TOKEN || '';
    }}

    // Intercept fetch
    const originalFetch = window.fetch;
    window.fetch = function(url, options) {{
        if (typeof url === 'string' && url.startsWith('/') && !url.startsWith(proxyPrefix)) {{
            url = proxyPrefix + url;
        }}
        return originalFetch(url, options);
    }};

    // ULTRA-DEEP intercept: Replace XMLHttpRequest at Object.defineProperty level
    const OriginalXMLHttpRequest = window.XMLHttpRequest;

    const proxyXHR = function() {{
        const xhr = new OriginalXMLHttpRequest();
        const originalOpen = xhr.open;

        xhr.open = function(method, url, ...rest) {{
            const originalUrl = url;
            // Rewrite URL if it's relative and not already proxied
            if (typeof url === 'string' && url.startsWith('/') && !url.startsWith(proxyPrefix)) {{
                url = proxyPrefix + url;
                console.log('[Zenzefi Proxy] XHR rewrite:', originalUrl, '→', url);
            }}
            return originalOpen.call(this, method, url, ...rest);
        }};

        return xhr;
    }};

    // Copy all static properties and constants
    for (let prop in OriginalXMLHttpRequest) {{
        if (OriginalXMLHttpRequest.hasOwnProperty(prop)) {{
            try {{
                proxyXHR[prop] = OriginalXMLHttpRequest[prop];
            }} catch(e) {{}}
        }}
    }}

    Object.setPrototypeOf(proxyXHR.prototype, OriginalXMLHttpRequest.prototype);
    Object.setPrototypeOf(proxyXHR, OriginalXMLHttpRequest);

    // FORCE replace using defineProperty (non-configurable!)
    try {{
        delete window.XMLHttpRequest;
        Object.defineProperty(window, 'XMLHttpRequest', {{
            value: proxyXHR,
            writable: false,
            configurable: false
        }});
    }} catch(e) {{
        // Fallback: just replace
        window.XMLHttpRequest = proxyXHR;
    }}

    console.log('[Zenzefi Proxy] XMLHttpRequest constructor intercepted (LOCKED)!');

    // Intercept WebSocket
    const OriginalWebSocket = window.WebSocket;
    window.WebSocket = function(url, protocols) {{
        console.log('[Zenzefi Proxy] Original WebSocket URL:', url);

        // Convert relative URL to use proxy
        if (typeof url === 'string' && url.startsWith('/') && !url.startsWith(proxyPrefix)) {{
            url = proxyPrefix + url;
        }}

        // Convert ws:// to our proxy endpoint (http → ws mapping)
        if (typeof url === 'string' && (url.startsWith('ws://') || url.startsWith('wss://'))) {{
            // Extract path from WebSocket URL
            const wsUrl = new URL(url);
            url = proxyPrefix + wsUrl.pathname + wsUrl.search;
        }}

        // Add token to WebSocket URL as query parameter
        const token = getAccessToken();
        if (token) {{
            if (url.indexOf('?') === -1) {{
                url += '?token=' + encodeURIComponent(token);
            }} else {{
                url += '&token=' + encodeURIComponent(token);
            }}
        }}

        console.log('[Zenzefi Proxy] Rewritten WebSocket URL:', url);
        return new OriginalWebSocket(url, protocols);
    }};
    window.WebSocket.prototype = OriginalWebSocket.prototype;
    window.WebSocket.CONNECTING = OriginalWebSocket.CONNECTING;
    window.WebSocket.OPEN = OriginalWebSocket.OPEN;
    window.WebSocket.CLOSING = OriginalWebSocket.CLOSING;
    window.WebSocket.CLOSED = OriginalWebSocket.CLOSED;

    console.log('[Zenzefi Proxy] WebSocket interceptor installed!');
}})();
</script>
"""
                        # Inject BEFORE any other scripts to catch WebSocket early
                        if '<head>' in text_content.lower():
                            # Find position right after <head>
                            match = re.search(r'<head[^>]*>', text_content, flags=re.IGNORECASE)
                            if match:
                                pos = match.end()
                                text_content = text_content[:pos] + '\n' + proxy_script + '\n' + text_content[pos:]
                                logger.debug("Injected proxy intercept script at start of <head>")
                            else:
                                logger.warning("Found <head> but couldn't parse it")
                        elif '<html>' in text_content.lower():
                            # If no <head>, inject right after <html>
                            match = re.search(r'<html[^>]*>', text_content, flags=re.IGNORECASE)
                            if match:
                                pos = match.end()
                                text_content = text_content[:pos] + '\n' + proxy_script + '\n' + text_content[pos:]
                                logger.debug("Injected proxy intercept script after <html>")
                        else:
                            # Last resort: inject at the very beginning
                            text_content = proxy_script + '\n' + text_content
                            logger.debug("Injected proxy intercept script at document start")

                        # Also rewrite static asset URLs in HTML (only for direct API access)
                        # Desktop client doesn't need this - it handles routing itself
                        if not use_desktop_client:
                            text_content = re.sub(
                                r'(href|src)="(/[^"]*)"',
                                r'\1="/api/v1/proxy\2"',
                                text_content
                            )
                            text_content = re.sub(
                                r"(href|src)='(/[^']*)'",
                                r"\1='/api/v1/proxy\2'",
                                text_content
                            )
                            logger.debug(f"Rewrote URLs in {content_type} to proxy through /api/v1/proxy/")
                        else:
                            logger.debug(f"Desktop client detected - skipping static asset URL rewriting")

                        content = text_content.encode('utf-8')
                    except Exception as e:
                        logger.warning(f"Failed to rewrite content: {e}")
                        # Fall back to original content if rewriting fails

                # Apply ContentRewriter for URL rewriting (after HTML/JS modifications)
                # This handles URL rewriting in all text content types
                rewritten_content = content_rewriter.rewrite_content(content, content_type)

                # Rewrite URLs in response headers (Location, Referer, CORS, etc.)
                response_headers = content_rewriter.rewrite_headers(response_headers)

                # Update content-length if content was modified
                if len(rewritten_content) != len(content):
                    response_headers["content-length"] = str(len(rewritten_content))
                    logger.debug(
                        f"Content rewritten by ContentRewriter: {len(content)} → {len(rewritten_content)} bytes"
                    )

                # Return proxied response with rewritten content
                return Response(
                    content=rewritten_content,
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
