"""
Tests for app/core/security.py module
"""
import pytest
from datetime import timedelta, datetime, timezone

from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashing:
    """Tests for password hashing functions"""

    def test_hash_password(self):
        """Test that password hashing works"""
        password = "TestPassword123!"
        hashed = get_password_hash(password)

        # Hashed password should not equal plain password
        assert hashed != password

        # Hashed password should be a string
        assert isinstance(hashed, str)

        # Hashed password should have content
        assert len(hashed) > 0

    def test_verify_password_correct(self):
        """Test password verification with correct password"""
        password = "CorrectPassword123!"
        hashed = get_password_hash(password)

        # Should return True for correct password
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password"""
        password = "CorrectPassword123!"
        wrong_password = "WrongPassword456!"
        hashed = get_password_hash(password)

        # Should return False for incorrect password
        assert verify_password(wrong_password, hashed) is False

    def test_hash_different_passwords_produce_different_hashes(self):
        """Test that different passwords produce different hashes"""
        password1 = "Password123!"
        password2 = "DifferentPassword456!"

        hash1 = get_password_hash(password1)
        hash2 = get_password_hash(password2)

        # Different passwords should produce different hashes
        assert hash1 != hash2

    def test_hash_same_password_produces_different_hashes(self):
        """Test that same password hashed twice produces different hashes (salt)"""
        password = "SamePassword123!"

        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Same password hashed twice should produce different hashes (bcrypt uses salt)
        assert hash1 != hash2

        # But both should verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWTTokens:
    """Tests for JWT token creation and decoding"""

    def test_create_access_token(self, test_settings):
        """Test creating an access token"""
        data = {"sub": "user123", "username": "testuser"}
        token = create_access_token(data)

        # Token should be a string
        assert isinstance(token, str)

        # Token should have content
        assert len(token) > 0

        # Token should have 3 parts (header.payload.signature)
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_access_token_with_custom_expiration(self, test_settings):
        """Test creating token with custom expiration time"""
        data = {"sub": "user123"}
        expires_delta = timedelta(minutes=30)

        token = create_access_token(data, expires_delta)

        # Decode and check expiration
        decoded = decode_access_token(token)
        assert decoded is not None

        # Check that exp claim exists
        assert "exp" in decoded

        # Expiration should be approximately 30 minutes from now
        exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        expected_exp = datetime.now(timezone.utc) + expires_delta

        # Allow 10 seconds tolerance
        assert abs((exp_time - expected_exp).total_seconds()) < 10

    def test_decode_access_token(self, test_settings):
        """Test decoding a valid access token"""
        data = {"sub": "user123", "username": "testuser"}
        token = create_access_token(data)

        # Decode token
        decoded = decode_access_token(token)

        # Should return dict
        assert isinstance(decoded, dict)

        # Should contain original data
        assert decoded["sub"] == "user123"
        assert decoded["username"] == "testuser"

        # Should contain exp and iat claims
        assert "exp" in decoded
        assert "iat" in decoded

    def test_decode_invalid_token(self, test_settings):
        """Test decoding an invalid token"""
        invalid_token = "invalid.token.here"

        # Should return None for invalid token
        decoded = decode_access_token(invalid_token)
        assert decoded is None

    def test_decode_malformed_token(self, test_settings):
        """Test decoding a malformed token"""
        malformed_token = "not-a-jwt-token-at-all"

        # Should return None
        decoded = decode_access_token(malformed_token)
        assert decoded is None

    def test_decode_expired_token(self, test_settings):
        """Test decoding an expired token"""
        data = {"sub": "user123"}
        # Create token that expired 1 hour ago
        expired_delta = timedelta(hours=-1)
        token = create_access_token(data, expired_delta)

        # Should return None for expired token
        decoded = decode_access_token(token)
        assert decoded is None

    def test_token_contains_issued_at(self, test_settings):
        """Test that token contains issued at (iat) claim"""
        data = {"sub": "user123"}
        token = create_access_token(data)

        decoded = decode_access_token(token)
        assert decoded is not None

        # Check iat claim
        assert "iat" in decoded
        iat_time = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)

        # Should be close to current time
        now = datetime.now(timezone.utc)
        assert abs((now - iat_time).total_seconds()) < 10

    def test_token_preserves_custom_claims(self, test_settings):
        """Test that custom claims are preserved in token"""
        data = {
            "sub": "user123",
            "username": "testuser",
            "email": "test@example.com",
            "custom_field": "custom_value",
        }
        token = create_access_token(data)

        decoded = decode_access_token(token)
        assert decoded is not None

        # All custom claims should be preserved
        assert decoded["sub"] == "user123"
        assert decoded["username"] == "testuser"
        assert decoded["email"] == "test@example.com"
        assert decoded["custom_field"] == "custom_value"
