import secrets
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.token import AccessToken
from app.models.user import User
from app.core.redis import get_redis_client
from app.config import settings


class TokenService:
    """Service for access token operations"""

    @staticmethod
    def generate_access_token(
        user_id: str, duration_hours: int, scope: str, db: Session
    ) -> AccessToken:
        """
        Generate new access token for user (MVP: бесплатно)

        Args:
            user_id: User UUID
            duration_hours: Token duration in hours (1, 12, 24, 168, 720)
            scope: Access scope ("full" or "certificates_only")
            db: Database session

        Returns:
            Created AccessToken object

        Raises:
            ValueError: If user not found or invalid duration
        """
        # Validate duration
        valid_durations = [1, 12, 24, 168, 720]
        if duration_hours not in valid_durations:
            raise ValueError(
                f"Invalid duration. Must be one of: {valid_durations}"
            )

        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        # Generate random token (URL-safe, 48 bytes = 64 chars)
        token_string = secrets.token_urlsafe(48)

        now = datetime.now(timezone.utc)
        # activated_at будет установлен при первом использовании токена
        # expires_at вычисляется динамически как activated_at + duration_hours

        # Create token record
        db_token = AccessToken(
            user_id=user_id,
            token=token_string,
            duration_hours=duration_hours,
            scope=scope,
            created_at=now,
            activated_at=None,  # Будет установлен при первом использовании
            is_active=True,
        )

        db.add(db_token)
        db.commit()
        db.refresh(db_token)

        # Cache token in Redis
        TokenService._cache_token(db_token)

        return db_token

    @staticmethod
    def check_token_status(token: str, db: Session) -> Tuple[bool, Optional[dict]]:
        """
        Check token status WITHOUT activating it (read-only check)

        This is useful for status endpoints where you want to check if a token
        is valid without starting the expiration countdown.

        Args:
            token: Access token string
            db: Database session

        Returns:
            Tuple of (is_valid, token_data)
            token_data contains: user_id, token_id, expires_at, duration_hours, is_activated

            For non-activated tokens:
                - expires_at will be None
                - is_activated will be False
        """
        # Check Redis cache first (fast path)
        redis_data = TokenService._get_cached_token(token)
        if redis_data:
            expires_at = datetime.fromisoformat(redis_data["expires_at"])
            # Ensure timezone-aware comparison
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > datetime.now(timezone.utc):
                redis_data["is_activated"] = True
                return True, redis_data
            else:
                # Expired token in cache
                return False, None

        # Check database (slow path) - READ ONLY, no activation
        db_token = (
            db.query(AccessToken)
            .filter(
                AccessToken.token == token,
                AccessToken.is_active == True,
                AccessToken.revoked_at == None,
            )
            .first()
        )

        if db_token:
            # Check if already activated and expired
            # expires_at is now calculated from activated_at + duration_hours
            if db_token.activated_at:
                # Ensure activated_at is timezone-aware for comparison
                activated_at = db_token.activated_at
                if activated_at.tzinfo is None:
                    activated_at = activated_at.replace(tzinfo=timezone.utc)
                expires_at = activated_at + timedelta(hours=db_token.duration_hours)
                if expires_at <= datetime.now(timezone.utc):
                    return False, None

            # Return token data WITHOUT activation
            token_data = {
                "user_id": str(db_token.user_id),
                "token_id": str(db_token.id),
                "expires_at": db_token.expires_at.isoformat() if db_token.expires_at else None,
                "duration_hours": db_token.duration_hours,
                "scope": db_token.scope,
                "is_activated": db_token.activated_at is not None,
                "activated_at": db_token.activated_at.isoformat() if db_token.activated_at else None,
            }

            return True, token_data

        return False, None

    @staticmethod
    def validate_token(token: str, db: Session) -> Tuple[bool, Optional[dict]]:
        """
        Validate access token and ACTIVATE it on first use

        ⚠️  WARNING: This method activates the token on first validation!
        Use check_token_status() if you need read-only validation.

        Args:
            token: Access token string
            db: Database session

        Returns:
            Tuple of (is_valid, token_data)
            token_data contains: user_id, token_id, expires_at, duration_hours
        """
        # Check Redis cache first (fast path)
        redis_data = TokenService._get_cached_token(token)
        if redis_data:
            expires_at = datetime.fromisoformat(redis_data["expires_at"])
            # Ensure timezone-aware comparison
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > datetime.now(timezone.utc):
                return True, redis_data
            else:
                # Expired token in cache, remove it
                TokenService._remove_cached_token(token)

        # Check database (slow path)
        # Находим токен: активный, не отозванный, и либо не активирован (expires_at=NULL),
        # либо активирован но еще не истек
        db_token = (
            db.query(AccessToken)
            .filter(
                AccessToken.token == token,
                AccessToken.is_active == True,
                AccessToken.revoked_at == None,
            )
            .first()
        )

        if db_token:
            # Проверяем, не истек ли уже активированный токен
            # expires_at теперь вычисляется динамически
            if db_token.activated_at:
                # Ensure activated_at is timezone-aware for comparison
                activated_at = db_token.activated_at
                if activated_at.tzinfo is None:
                    activated_at = activated_at.replace(tzinfo=timezone.utc)
                expires_at = activated_at + timedelta(hours=db_token.duration_hours)
                if expires_at <= datetime.now(timezone.utc):
                    return False, None

            # Активируем токен при первом использовании
            if not db_token.activated_at:
                db_token.activated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(db_token)

            # Update Redis cache
            TokenService._cache_token(db_token)

            token_data = {
                "user_id": str(db_token.user_id),
                "token_id": str(db_token.id),
                "expires_at": db_token.expires_at.isoformat(),  # Uses @property
                "duration_hours": db_token.duration_hours,
                "scope": db_token.scope,
            }

            return True, token_data

        return False, None

    @staticmethod
    def get_user_tokens(user_id: str, active_only: bool, db: Session) -> list[AccessToken]:
        """
        Get all tokens for a user

        Args:
            user_id: User UUID
            active_only: If True, return only active tokens
            db: Database session

        Returns:
            List of AccessToken objects
        """
        query = db.query(AccessToken).filter(AccessToken.user_id == user_id)

        if active_only:
            # Активный токен = is_active=True, не отозван, и (не активирован ИЛИ не истек)
            # Поскольку expires_at теперь вычисляется, фильтруем по activated_at
            query = query.filter(
                AccessToken.is_active == True,
                AccessToken.revoked_at == None,
            )

            # Получаем все токены и фильтруем в Python (expires_at теперь property)
            all_tokens = query.order_by(AccessToken.created_at.desc()).all()
            now = datetime.now(timezone.utc)
            return [
                token for token in all_tokens
                if token.activated_at is None or token.expires_at > now
            ]

        return query.order_by(AccessToken.created_at.desc()).all()

    @staticmethod
    def _cache_token(token: AccessToken):
        """Cache token in Redis"""
        try:
            # Кэшируем только активированные токены
            if not token.activated_at:
                return

            redis = get_redis_client()
            token_hash = hashlib.sha256(token.token.encode()).hexdigest()
            key = f"active_token:{token_hash}"

            # expires_at вычисляется через @property
            expires_at = token.expires_at
            data = {
                "user_id": str(token.user_id),
                "token_id": str(token.id),
                "expires_at": expires_at.isoformat(),
                "duration_hours": token.duration_hours,
                "scope": token.scope,
            }

            ttl = int((expires_at - datetime.now(timezone.utc)).total_seconds())
            if ttl > 0:
                redis.setex(key, ttl, json.dumps(data))
        except Exception as e:
            # Log error but don't fail - Redis is cache, not critical
            from loguru import logger
            logger.warning(f"Failed to cache token in Redis: {e}")

    @staticmethod
    def _get_cached_token(token: str) -> Optional[dict]:
        """Get token from Redis cache"""
        try:
            redis = get_redis_client()
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            key = f"active_token:{token_hash}"

            data = redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            # Log error but don't fail
            from loguru import logger
            logger.warning(f"Failed to get token from Redis: {e}")
            return None

    @staticmethod
    def _remove_cached_token(token: str):
        """Remove token from Redis cache"""
        try:
            redis = get_redis_client()
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            key = f"active_token:{token_hash}"
            redis.delete(key)
        except Exception as e:
            # Log error but don't fail
            from loguru import logger
            logger.warning(f"Failed to remove token from Redis: {e}")
