"""
Rate Limiting middleware

Implements Redis-based rate limiting with sliding window algorithm.
Protects endpoints from abuse with different limits for auth, API, and proxy endpoints.

Limits:
- Auth endpoints (/api/v1/auth/*): 5 requests/hour per IP (brute force protection)
- API endpoints (/api/v1/*): 100 requests/minute per user
- Proxy endpoints (/api/v1/proxy/*): 1000 requests/minute per token
"""
import time
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from app.core.redis import get_redis_client


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-based rate limiting with sliding window algorithm

    Uses Redis sorted sets (zset) for efficient sliding window tracking.
    Each request is added to a zset with timestamp as both score and member.
    Old entries outside the window are automatically removed.

    Limits are configurable per endpoint type:
    - auth: IP-based (brute force protection)
    - api: User-based (normal API usage)
    - proxy: Token-based (proxy traffic)
    """

    # Rate limit configurations
    LIMITS = {
        "auth": {"requests": 5, "window": 3600},     # 5 attempts/hour (IP-based)
        "api": {"requests": 100, "window": 60},       # 100 req/min (user-based)
        "proxy": {"requests": 1000, "window": 60},    # 1000 req/min (token-based)
    }

    async def dispatch(self, request: Request, call_next):
        """
        Process request and check rate limits

        Args:
            request: FastAPI Request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response from next handler or 429 error if rate limit exceeded

        Raises:
            HTTPException: 429 Too Many Requests if limit exceeded
        """
        redis = get_redis_client()
        path = request.url.path

        # Determine rate limit type and identifier
        limit_type, identifier = self._get_limit_config(request, path)

        if not identifier:
            # No identifier available (e.g., unauthenticated request to non-auth endpoint)
            # Let the request proceed (auth will handle it)
            return await call_next(request)

        # Check for superuser bypass (optional)
        if self._is_superuser(request):
            logger.debug(f"Rate limit bypassed for superuser: {identifier}")
            return await call_next(request)

        # Check rate limit
        limit_config = self.LIMITS[limit_type]
        key = f"rate_limit:{limit_type}:{identifier}"

        try:
            # Sliding window counter
            current_time = int(time.time())
            window_start = current_time - limit_config["window"]

            # Remove old entries outside the window
            redis.zremrangebyscore(key, 0, window_start)

            # Count current requests in window
            current_count = redis.zcard(key)

            if current_count >= limit_config["requests"]:
                # Rate limit exceeded
                logger.warning(
                    f"Rate limit exceeded: {limit_type} - {identifier} "
                    f"({current_count}/{limit_config['requests']} in {limit_config['window']}s)"
                )
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": (
                            f"Rate limit exceeded. Maximum {limit_config['requests']} requests "
                            f"per {limit_config['window']} seconds allowed."
                        ),
                        "limit": limit_config["requests"],
                        "window": limit_config["window"],
                        "retry_after": self._get_retry_after(redis, key, limit_config),
                    }
                )

            # Add current request to sliding window
            # Use unique member (timestamp + small random component) to avoid collisions
            # when multiple requests arrive in the same second
            import secrets
            unique_member = f"{current_time}:{secrets.token_hex(4)}"
            redis.zadd(key, {unique_member: current_time})
            # Set expiration to window duration (auto-cleanup)
            redis.expire(key, limit_config["window"])

            # Process request
            response = await call_next(request)
            return response

        except HTTPException:
            # Re-raise HTTP exceptions (rate limit exceeded)
            raise
        except Exception as e:
            # Log error but don't fail request if Redis is unavailable
            logger.error(f"Rate limiting error: {e}")
            # Fail open (allow request) if rate limiting system fails
            return await call_next(request)

    def _get_limit_config(self, request: Request, path: str) -> tuple[str, str | None]:
        """
        Determine rate limit type and identifier based on request path

        Args:
            request: FastAPI Request object
            path: Request URL path

        Returns:
            Tuple of (limit_type, identifier)
            - limit_type: "auth", "api", or "proxy"
            - identifier: IP address, user_id, or token_id (None if not available)
        """
        if path.startswith("/api/v1/auth"):
            # Auth endpoints: IP-based rate limiting
            limit_type = "auth"
            identifier = request.client.host if request.client else None

        elif path.startswith("/api/v1/proxy"):
            # Proxy endpoints: Token-based rate limiting
            limit_type = "proxy"
            identifier = str(request.state.token_id) if hasattr(request.state, "token_id") else None

        else:
            # Other API endpoints: User-based rate limiting
            limit_type = "api"
            identifier = str(request.state.user_id) if hasattr(request.state, "user_id") else None

        return limit_type, identifier

    def _is_superuser(self, request: Request) -> bool:
        """
        Check if request is from a superuser (bypass rate limiting)

        Args:
            request: FastAPI Request object

        Returns:
            True if user is superuser, False otherwise
        """
        # Check if user object is available and is_superuser is True
        if hasattr(request.state, "user") and hasattr(request.state.user, "is_superuser"):
            return request.state.user.is_superuser
        return False

    def _get_retry_after(self, redis, key: str, limit_config: dict) -> int:
        """
        Calculate retry_after seconds (when oldest request will expire)

        Args:
            redis: Redis client
            key: Rate limit key
            limit_config: Limit configuration dict

        Returns:
            Seconds until oldest request expires from window
        """
        try:
            # Get oldest request timestamp from zset
            oldest = redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_timestamp = int(oldest[0][1])  # score is the timestamp
                current_time = int(time.time())
                window_end = oldest_timestamp + limit_config["window"]
                retry_after = max(0, window_end - current_time)
                return retry_after
        except Exception as e:
            logger.error(f"Error calculating retry_after: {e}")

        # Default: return full window duration
        return limit_config["window"]
