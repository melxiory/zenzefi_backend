"""
Tests for app/services/token_service.py
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.services.token_service import TokenService
from app.services.auth_service import AuthService
from app.schemas.user import UserCreate
from app.models.token import AccessToken


@pytest.fixture(autouse=True)
def mock_redis(fake_redis):
    """
    Automatically mock Redis for all tests in this file

    This fixture uses autouse=True so it's applied to every test automatically
    """
    with patch('app.services.token_service.get_redis_client', return_value=fake_redis):
        yield fake_redis


class TestTokenServiceGenerate:
    """Tests for access token generation"""

    def test_generate_access_token_success(
        self, test_db: Session, test_user_data: dict
    ):
        """Test successful access token generation"""
        # Create user first
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        # Generate token (Redis is mocked automatically)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, db=test_db
        )

        # Check token
        assert token is not None
        assert isinstance(token, AccessToken)
        assert token.user_id == user.id
        assert token.duration_hours == 24
        assert token.is_active is True
        assert token.activated_at is None  # Not activated yet
        assert token.revoked_at is None

        # Check token string
        assert token.token is not None
        assert isinstance(token.token, str)
        assert len(token.token) > 0

        # Check expiration - should be NULL until activated
        assert token.expires_at is None  # Not activated yet, so no expiry set

    def test_generate_token_valid_durations(
        self, test_db: Session, test_user_data: dict
    ):
        """Test token generation with all valid durations"""
        # Create user
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        valid_durations = [1, 12, 24, 168, 720]

        for duration in valid_durations:
            token = TokenService.generate_access_token(
                user_id=str(user.id), duration_hours=duration, db=test_db
            )

            assert token.duration_hours == duration

    def test_generate_token_invalid_duration(
        self, test_db: Session, test_user_data: dict
    ):
        """Test token generation with invalid duration fails"""
        # Create user
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        # Try invalid durations
        invalid_durations = [0, 2, 5, 100, 1000]

        for duration in invalid_durations:
            with pytest.raises(ValueError, match="Invalid duration"):
                TokenService.generate_access_token(
                    user_id=str(user.id), duration_hours=duration, db=test_db
                )

    def test_generate_token_nonexistent_user(self, test_db: Session):
        """Test token generation for non-existent user fails"""
        fake_user_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(ValueError, match="User not found"):
            TokenService.generate_access_token(
                user_id=fake_user_id, duration_hours=24, db=test_db
            )

    def test_generate_multiple_tokens_for_user(
        self, test_db: Session, test_user_data: dict
    ):
        """Test generating multiple tokens for same user"""
        # Create user
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        # Generate multiple tokens
        token1 = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, db=test_db
        )
        token2 = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=12, db=test_db
        )

        # Tokens should be different
        assert token1.id != token2.id
        assert token1.token != token2.token


class TestTokenServiceValidate:
    """Tests for access token validation"""

    def test_validate_token_success(self, test_db: Session, test_user_data: dict):
        """Test successful token validation"""
        # Create user and token
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, db=test_db
        )

        # Validate token
        is_valid, token_data = TokenService.validate_token(token.token, test_db)

        # Should be valid
        assert is_valid is True
        assert token_data is not None

        # Check token data
        assert token_data["user_id"] == str(user.id)
        assert token_data["token_id"] == str(token.id)
        assert token_data["duration_hours"] == 24
        assert "expires_at" in token_data

    def test_validate_token_activates_on_first_use(
        self, test_db: Session, test_user_data: dict, fake_redis
    ):
        """Test that token is activated on first validation and expires_at is set"""
        # Create user and token
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, db=test_db
        )

        # Token should not be activated yet
        assert token.activated_at is None
        assert token.expires_at is None  # expires_at is NULL until first use

        # Clear Redis cache to force DB lookup
        fake_redis.flushall()

        # Validate token - will hit database and activate
        is_valid, token_data = TokenService.validate_token(token.token, test_db)
        assert is_valid is True

        # Check token was activated
        test_db.refresh(token)
        assert token.activated_at is not None
        assert token.expires_at is not None  # Now expires_at is set

        # Activated time should be close to now
        now = datetime.utcnow()
        assert abs((now - token.activated_at).total_seconds()) < 10

        # Expiry should be 24 hours from activation
        expected_expiry = token.activated_at + timedelta(hours=24)
        assert abs((token.expires_at - expected_expiry).total_seconds()) < 10

    def test_validate_invalid_token(self, test_db: Session):
        """Test validation of invalid token string"""
        fake_token = "invalid-token-string-that-does-not-exist"

        is_valid, token_data = TokenService.validate_token(fake_token, test_db)

        # Should be invalid
        assert is_valid is False
        assert token_data is None

    def test_validate_expired_token(self, test_db: Session, test_user_data: dict, fake_redis):
        """Test validation of expired token"""
        # Create user and token
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=1, db=test_db
        )

        # Manually activate and expire the token in database
        # expires_at is now calculated, so we set activated_at far enough in the past
        # For 1-hour token: activated 2 hours ago = expired 1 hour ago
        token.activated_at = datetime.utcnow() - timedelta(hours=2)
        test_db.commit()

        # Clear Redis cache so validation will check database
        fake_redis.flushall()

        # Validate token - should check database and find it expired
        is_valid, token_data = TokenService.validate_token(token.token, test_db)

        # Should be invalid
        assert is_valid is False
        assert token_data is None

    def test_validate_revoked_token(self, test_db: Session, test_user_data: dict, fake_redis):
        """Test validation of revoked token"""
        # Create user and token
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)
        token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, db=test_db
        )

        # Revoke token in database
        token.is_active = False
        token.revoked_at = datetime.utcnow()
        test_db.commit()

        # Clear Redis cache so validation will check database
        fake_redis.flushall()

        # Validate token - should check database and find it revoked
        is_valid, token_data = TokenService.validate_token(token.token, test_db)

        # Should be invalid
        assert is_valid is False
        assert token_data is None


class TestTokenServiceGetUserTokens:
    """Tests for getting user tokens"""

    def test_get_user_tokens_empty(self, test_db: Session, test_user_data: dict):
        """Test getting tokens for user with no tokens"""
        # Create user without tokens
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        # Get tokens
        tokens = TokenService.get_user_tokens(
            user_id=str(user.id), active_only=False, db=test_db
        )

        # Should be empty list
        assert tokens == []

    def test_get_user_tokens_all(self, test_db: Session, test_user_data: dict):
        """Test getting all tokens for user"""
        # Create user and tokens
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        token1 = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, db=test_db
        )
        token2 = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=12, db=test_db
        )

        # Get all tokens
        tokens = TokenService.get_user_tokens(
            user_id=str(user.id), active_only=False, db=test_db
        )

        # Should return both tokens
        assert len(tokens) == 2
        token_ids = [t.id for t in tokens]
        assert token1.id in token_ids
        assert token2.id in token_ids

    def test_get_user_tokens_active_only(self, test_db: Session, test_user_data: dict):
        """Test getting only active tokens"""
        # Create user and tokens
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        active_token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, db=test_db
        )
        revoked_token = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=12, db=test_db
        )

        # Revoke one token
        revoked_token.is_active = False
        revoked_token.revoked_at = datetime.utcnow()
        test_db.commit()

        # Get active tokens only
        tokens = TokenService.get_user_tokens(
            user_id=str(user.id), active_only=True, db=test_db
        )

        # Should return only active token
        assert len(tokens) == 1
        assert tokens[0].id == active_token.id

    def test_get_user_tokens_ordered_by_created_at(
        self, test_db: Session, test_user_data: dict
    ):
        """Test that tokens are ordered by created_at descending"""
        # Create user and tokens
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        # Create tokens with slight delay
        token1 = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=24, db=test_db
        )
        token2 = TokenService.generate_access_token(
            user_id=str(user.id), duration_hours=12, db=test_db
        )

        # Get tokens
        tokens = TokenService.get_user_tokens(
            user_id=str(user.id), active_only=False, db=test_db
        )

        # Should be ordered by created_at descending (newest first)
        assert len(tokens) == 2
        assert tokens[0].id == token2.id  # Created later
        assert tokens[1].id == token1.id  # Created earlier
