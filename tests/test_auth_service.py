"""
Tests for app/services/auth_service.py
"""
import pytest
from sqlalchemy.orm import Session

from app.services.auth_service import AuthService
from app.schemas.user import UserCreate
from app.models.user import User
from app.core.security import verify_password


class TestAuthServiceRegister:
    """Tests for user registration"""

    def test_register_user_success(self, test_db: Session, test_user_data: dict):
        """Test successful user registration"""
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        # Check user was created
        assert user is not None
        assert isinstance(user, User)

        # Check user data
        assert user.email == test_user_data["email"]
        assert user.username == test_user_data["username"]
        assert user.full_name == test_user_data["full_name"]

        # Check password was hashed
        assert user.hashed_password != test_user_data["password"]
        assert verify_password(test_user_data["password"], user.hashed_password)

        # Check defaults
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.id is not None
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_register_user_duplicate_email(
        self, test_db: Session, test_user_data: dict
    ):
        """Test registration with duplicate email fails"""
        # Register first user
        user_create = UserCreate(**test_user_data)
        AuthService.register_user(user_create, test_db)

        # Try to register with same email but different username
        duplicate_data = test_user_data.copy()
        duplicate_data["username"] = "differentusername"
        user_create_duplicate = UserCreate(**duplicate_data)

        # Should raise ValueError
        with pytest.raises(ValueError, match="Email already registered"):
            AuthService.register_user(user_create_duplicate, test_db)

    def test_register_user_duplicate_username(
        self, test_db: Session, test_user_data: dict
    ):
        """Test registration with duplicate username fails"""
        # Register first user
        user_create = UserCreate(**test_user_data)
        AuthService.register_user(user_create, test_db)

        # Try to register with same username but different email
        duplicate_data = test_user_data.copy()
        duplicate_data["email"] = "different@example.com"
        user_create_duplicate = UserCreate(**duplicate_data)

        # Should raise ValueError
        with pytest.raises(ValueError, match="Username already taken"):
            AuthService.register_user(user_create_duplicate, test_db)

    def test_register_user_without_full_name(self, test_db: Session):
        """Test registration without full_name (optional field)"""
        user_data = {
            "email": "noname@example.com",
            "username": "noname",
            "password": "TestPass123!",
        }
        user_create = UserCreate(**user_data)
        user = AuthService.register_user(user_create, test_db)

        # Should succeed with None full_name
        assert user is not None
        assert user.full_name is None


class TestAuthServiceAuthenticate:
    """Tests for user authentication"""

    def test_authenticate_user_success(self, test_db: Session, test_user_data: dict):
        """Test successful user authentication"""
        # Register user first
        user_create = UserCreate(**test_user_data)
        registered_user = AuthService.register_user(user_create, test_db)

        # Authenticate
        authenticated_user = AuthService.authenticate_user(
            test_user_data["email"], test_user_data["password"], test_db
        )

        # Should return user
        assert authenticated_user is not None
        assert authenticated_user.id == registered_user.id
        assert authenticated_user.email == registered_user.email

    def test_authenticate_user_wrong_password(
        self, test_db: Session, test_user_data: dict
    ):
        """Test authentication with wrong password fails"""
        # Register user
        user_create = UserCreate(**test_user_data)
        AuthService.register_user(user_create, test_db)

        # Try to authenticate with wrong password
        authenticated_user = AuthService.authenticate_user(
            test_user_data["email"], "WrongPassword123!", test_db
        )

        # Should return None
        assert authenticated_user is None

    def test_authenticate_user_nonexistent_email(
        self, test_db: Session, test_user_data: dict
    ):
        """Test authentication with non-existent email fails"""
        # Don't register any user

        # Try to authenticate
        authenticated_user = AuthService.authenticate_user(
            "nonexistent@example.com", "AnyPassword123!", test_db
        )

        # Should return None
        assert authenticated_user is None

    def test_authenticate_inactive_user(self, test_db: Session, test_user_data: dict):
        """Test authentication with inactive user fails"""
        # Register user
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        # Deactivate user
        user.is_active = False
        test_db.commit()

        # Try to authenticate
        authenticated_user = AuthService.authenticate_user(
            test_user_data["email"], test_user_data["password"], test_db
        )

        # Should return None
        assert authenticated_user is None


class TestAuthServiceCreateToken:
    """Tests for JWT token creation"""

    def test_create_user_token(self, test_db: Session, test_user_data: dict):
        """Test creating JWT token for user"""
        # Register user
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        # Create token
        token_response = AuthService.create_user_token(user)

        # Check token response
        assert token_response is not None
        assert token_response.access_token is not None
        assert isinstance(token_response.access_token, str)
        assert len(token_response.access_token) > 0

        # Check token type
        assert token_response.token_type == "bearer"

        # Check expires_in
        assert token_response.expires_in > 0
        assert token_response.expires_in == 60 * 60  # 60 minutes in seconds

    def test_token_contains_user_info(self, test_db: Session, test_user_data: dict):
        """Test that token contains user information"""
        from app.core.security import decode_access_token

        # Register user
        user_create = UserCreate(**test_user_data)
        user = AuthService.register_user(user_create, test_db)

        # Create token
        token_response = AuthService.create_user_token(user)

        # Decode token
        decoded = decode_access_token(token_response.access_token)

        # Should contain user info
        assert decoded is not None
        assert decoded["sub"] == str(user.id)
        assert decoded["username"] == user.username
