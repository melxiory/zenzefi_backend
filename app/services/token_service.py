import secrets
import hashlib
import json
from datetime import datetime, timedelta
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
        user_id: str, duration_hours: int, db: Session
    ) -> AccessToken:
        """
        Generate new access token for user (MVP: бесплатно)

        Args:
            user_id: User UUID
            duration_hours: Token duration in hours (1, 12, 24, 168, 720)
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

        now = datetime.utcnow()
        # expires_at будет установлен при первой активации токена
        # Это позволяет пользователю получить полное время использования
        # с момента первого обращения к proxy, а не с момента покупки

        # Create token record
        db_token = AccessToken(
            user_id=user_id,
            token=token_string,
            duration_hours=duration_hours,
            created_at=now,
            expires_at=None,  # Будет установлен при активации
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
            if expires_at > datetime.utcnow():
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
            if db_token.expires_at and db_token.expires_at <= datetime.utcnow():
                return False, None

            # Return token data WITHOUT activation
            token_data = {
                "user_id": str(db_token.user_id),
                "token_id": str(db_token.id),
                "expires_at": db_token.expires_at.isoformat() if db_token.expires_at else None,
                "duration_hours": db_token.duration_hours,
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
            if expires_at > datetime.utcnow():
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
            if db_token.expires_at and db_token.expires_at <= datetime.utcnow():
                return False, None

            # Активируем токен при первом использовании
            if not db_token.activated_at:
                now = datetime.utcnow()
                db_token.activated_at = now
                db_token.expires_at = now + timedelta(hours=db_token.duration_hours)
                db.commit()
                db.refresh(db_token)

            # Update Redis cache
            TokenService._cache_token(db_token)

            token_data = {
                "user_id": str(db_token.user_id),
                "token_id": str(db_token.id),
                "expires_at": db_token.expires_at.isoformat(),
                "duration_hours": db_token.duration_hours,
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
            from sqlalchemy import or_
            query = query.filter(
                AccessToken.is_active == True,
                AccessToken.revoked_at == None,
                or_(
                    AccessToken.expires_at == None,  # Не активирован еще
                    AccessToken.expires_at > datetime.utcnow(),  # Активирован но не истек
                ),
            )

        return query.order_by(AccessToken.created_at.desc()).all()

    @staticmethod
    def _cache_token(token: AccessToken):
        """Cache token in Redis"""
        try:
            # Кэшируем только активированные токены (с expires_at)
            if not token.expires_at:
                return

            redis = get_redis_client()
            token_hash = hashlib.sha256(token.token.encode()).hexdigest()
            key = f"active_token:{token_hash}"

            data = {
                "user_id": str(token.user_id),
                "token_id": str(token.id),
                "expires_at": token.expires_at.isoformat(),
                "duration_hours": token.duration_hours,
            }

            ttl = int((token.expires_at - datetime.utcnow()).total_seconds())
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
