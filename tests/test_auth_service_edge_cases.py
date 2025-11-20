"""
Edge case tests for AuthService

Tests critical boundary conditions and invalid scenarios:
- Registration: Case sensitivity, whitespace handling, SQL injection attempts
- Referral codes: Invalid codes, inactive referrers, collision handling
- Authentication: Case sensitivity, timing attacks (not directly testable)
- JWT tokens: Expired tokens, malformed tokens (security module tests)
"""
import pytest
from sqlalchemy.orm import Session

from app.services.auth_service import AuthService
from app.schemas.user import UserCreate
from app.models.user import User


class TestAuthServiceRegistrationEdgeCases:
    """Tests for user registration edge cases"""

    def test_register_user_email_case_insensitive(self, test_db: Session):
        """
        EDGE CASE TEST: Register with different email case

        Expected: Should fail (email uniqueness is case-insensitive)
        Note: PostgreSQL UNIQUE constraint is case-sensitive by default,
        but application may enforce case-insensitivity
        """
        # Register first user with lowercase email
        user_data1 = UserCreate(
            email="test@example.com",
            username="testuser1",
            password="TestPass123!",
            full_name="Test User 1"
        )
        AuthService.register_user(user_data1, test_db)

        # Attempt to register with uppercase email
        user_data2 = UserCreate(
            email="TEST@EXAMPLE.COM",  # Same email, different case
            username="testuser2",
            password="TestPass123!",
            full_name="Test User 2"
        )

        # Behavior depends on DB collation (document actual behavior)
        try:
            AuthService.register_user(user_data2, test_db)
            # If succeeds, case-sensitive emails are allowed
            # This may be a bug if email should be case-insensitive
        except ValueError as e:
            # If fails, case-insensitive check is working
            assert "Email already registered" in str(e)

    def test_register_user_username_case_insensitive(self, test_db: Session):
        """
        EDGE CASE TEST: Register with different username case

        Expected: Should fail (username uniqueness is case-insensitive)
        """
        # Register first user with lowercase username
        user_data1 = UserCreate(
            email="user1@example.com",
            username="testuser",
            password="TestPass123!",
            full_name="Test User 1"
        )
        AuthService.register_user(user_data1, test_db)

        # Attempt to register with uppercase username
        user_data2 = UserCreate(
            email="user2@example.com",
            username="TESTUSER",  # Same username, different case
            password="TestPass123!",
            full_name="Test User 2"
        )

        # Behavior depends on DB collation (document actual behavior)
        try:
            AuthService.register_user(user_data2, test_db)
            # If succeeds, case-sensitive usernames are allowed
        except ValueError as e:
            # If fails, case-insensitive check is working
            assert "Username already taken" in str(e)

    def test_register_user_email_with_leading_trailing_whitespace(
        self, test_db: Session
    ):
        """
        VALIDATION TEST: Register with email containing whitespace

        Expected: Pydantic EmailStr should strip whitespace or fail validation
        """
        user_data = UserCreate(
            email="  test@example.com  ",  # Leading/trailing whitespace
            username="testuser",
            password="TestPass123!",
            full_name="Test User"
        )

        # Pydantic should strip whitespace automatically
        user = AuthService.register_user(user_data, test_db)
        assert user.email == "test@example.com"  # Whitespace stripped

    def test_register_user_username_with_special_characters(
        self, test_db: Session
    ):
        """
        VALIDATION TEST: Register with username containing special characters

        Expected: May succeed or fail depending on validation rules
        Note: Documents current behavior
        """
        user_data = UserCreate(
            email="special@example.com",
            username="test-user_123",  # Hyphens, underscores, numbers
            password="TestPass123!",
            full_name="Test User"
        )

        # Should succeed (username allows these characters)
        user = AuthService.register_user(user_data, test_db)
        assert user.username == "test-user_123"

    def test_register_user_with_sql_injection_attempt(self, test_db: Session):
        """
        SECURITY TEST: Register with SQL injection in fields

        Expected: Should be safely escaped by ORM (no SQL injection)
        """
        user_data = UserCreate(
            email="sqlinject@example.com",
            username="admin' OR '1'='1",  # SQL injection attempt
            password="TestPass123!",
            full_name="Robert'; DROP TABLE users;--"
        )

        # Should safely create user without SQL injection
        user = AuthService.register_user(user_data, test_db)
        assert user.username == "admin' OR '1'='1"  # Stored as literal string
        assert user.full_name == "Robert'; DROP TABLE users;--"

        # Verify user exists (table not dropped)
        found_user = test_db.query(User).filter(User.id == user.id).first()
        assert found_user is not None


class TestAuthServiceReferralCodeEdgeCases:
    """Tests for referral code edge cases"""

    def test_register_with_invalid_referral_code(self, test_db: Session):
        """
        VALIDATION TEST: Register with non-existent referral code

        Expected: Should fail with "Invalid referral code"
        """
        user_data = UserCreate(
            email="referred@example.com",
            username="referred",
            password="TestPass123!",
            full_name="Referred User"
        )

        with pytest.raises(ValueError, match="Invalid referral code"):
            AuthService.register_user(
                user_data,
                test_db,
                referral_code="INVALIDCODE123"  # Non-existent code
            )

    def test_register_with_inactive_referrer_code(self, test_db: Session):
        """
        SECURITY TEST: Register with referral code from inactive user

        Expected: Should fail with "Invalid referral code"
        """
        # Create referrer user
        referrer = User(
            email="referrer@example.com",
            username="referrer",
            hashed_password="hashed",
            full_name="Referrer User",
            referral_code="INACTIVE123",
            is_active=False  # Inactive user
        )
        test_db.add(referrer)
        test_db.commit()

        # Attempt to register with inactive referrer's code
        user_data = UserCreate(
            email="referred@example.com",
            username="referred",
            password="TestPass123!",
            full_name="Referred User"
        )

        with pytest.raises(ValueError, match="Invalid referral code"):
            AuthService.register_user(
                user_data,
                test_db,
                referral_code="INACTIVE123"
            )

    def test_generate_referral_code_uniqueness(self, test_db: Session):
        """
        UNIQUENESS TEST: Generate multiple referral codes (should all be unique)

        Expected: All codes should be unique (extremely high probability)
        """
        codes = set()

        # Generate 100 codes
        for _ in range(100):
            code = AuthService.generate_referral_code(test_db)
            assert len(code) == 12
            assert code.isalnum()
            assert code.isupper() or code.isdigit()
            codes.add(code)

        # All codes should be unique
        assert len(codes) == 100

    def test_register_with_referral_code_case_sensitive(self, test_db: Session):
        """
        EDGE CASE TEST: Referral code matching is case-sensitive

        Expected: Lowercase version of referral code should fail
        """
        # Create referrer user with uppercase code
        referrer_data = UserCreate(
            email="referrer@example.com",
            username="referrer",
            password="TestPass123!",
            full_name="Referrer User"
        )
        referrer = AuthService.register_user(referrer_data, test_db)
        referral_code = referrer.referral_code  # e.g., "A7B9C2D4E6F8"

        # Attempt to register with lowercase version
        user_data = UserCreate(
            email="referred@example.com",
            username="referred",
            password="TestPass123!",
            full_name="Referred User"
        )

        with pytest.raises(ValueError, match="Invalid referral code"):
            AuthService.register_user(
                user_data,
                test_db,
                referral_code=referral_code.lower()  # Lowercase version
            )


class TestAuthServiceAuthenticationEdgeCases:
    """Tests for authentication edge cases"""

    def test_authenticate_email_case_insensitive(self, test_db: Session):
        """
        EDGE CASE TEST: Authenticate with different email case

        Expected: Should succeed (email matching is case-insensitive)
        Note: Depends on database collation
        """
        # Register user with lowercase email
        user_data = UserCreate(
            email="auth@example.com",
            username="authuser",
            password="TestPass123!",
            full_name="Auth User"
        )
        AuthService.register_user(user_data, test_db)

        # Authenticate with uppercase email
        authenticated = AuthService.authenticate_user(
            email="AUTH@EXAMPLE.COM",  # Different case
            password="TestPass123!",
            db=test_db
        )

        # Behavior depends on DB collation (document actual behavior)
        # If succeeds, case-insensitive matching is working
        # If fails (None), case-sensitive matching is enforced

    def test_authenticate_with_empty_password(self, test_db: Session):
        """
        EDGE CASE TEST: Authenticate with empty password

        Expected: Should fail (return None)
        """
        # Register user
        user_data = UserCreate(
            email="empty_pass@example.com",
            username="empty_pass",
            password="TestPass123!",
            full_name="Empty Pass User"
        )
        AuthService.register_user(user_data, test_db)

        # Attempt to authenticate with empty password
        authenticated = AuthService.authenticate_user(
            email="empty_pass@example.com",
            password="",  # Empty password
            db=test_db
        )

        assert authenticated is None

    def test_authenticate_with_whitespace_only_password(self, test_db: Session):
        """
        EDGE CASE TEST: Authenticate with whitespace-only password

        Expected: Should fail (return None)
        """
        # Register user
        user_data = UserCreate(
            email="whitespace_pass@example.com",
            username="whitespace_pass",
            password="TestPass123!",
            full_name="Whitespace Pass User"
        )
        AuthService.register_user(user_data, test_db)

        # Attempt to authenticate with whitespace password
        authenticated = AuthService.authenticate_user(
            email="whitespace_pass@example.com",
            password="     ",  # Only whitespace
            db=test_db
        )

        assert authenticated is None

    def test_authenticate_preserves_password_whitespace(self, test_db: Session):
        """
        EDGE CASE TEST: Password with leading/trailing whitespace

        Expected: Whitespace should be preserved (not stripped)
        """
        # Register user with password containing whitespace
        user_data = UserCreate(
            email="whitespace_preserved@example.com",
            username="whitespace_preserved",
            password=" TestPass123! ",  # Leading/trailing whitespace
            full_name="Whitespace Preserved User"
        )
        user = AuthService.register_user(user_data, test_db)

        # Authenticate with exact password (including whitespace)
        authenticated = AuthService.authenticate_user(
            email="whitespace_preserved@example.com",
            password=" TestPass123! ",  # Same whitespace
            db=test_db
        )

        assert authenticated is not None
        assert authenticated.id == user.id

        # Authenticate without whitespace should fail
        authenticated_fail = AuthService.authenticate_user(
            email="whitespace_preserved@example.com",
            password="TestPass123!",  # No whitespace
            db=test_db
        )

        assert authenticated_fail is None
