from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
)
from app.models.user import User
from app.schemas.user import UserCreate
from app.schemas.auth import JWTTokenResponse
from app.config import settings


class AuthService:
    """Service for authentication operations"""

    @staticmethod
    def register_user(user_data: UserCreate, db: Session) -> User:
        """
        Register a new user

        Args:
            user_data: User creation data
            db: Database session

        Returns:
            Created User object

        Raises:
            ValueError: If email or username already exists
        """
        # Check if email already exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise ValueError("Email already registered")

        # Check if username already exists
        existing_username = (
            db.query(User).filter(User.username == user_data.username).first()
        )
        if existing_username:
            raise ValueError("Username already taken")

        # Create new user
        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
            full_name=user_data.full_name,
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        return db_user

    @staticmethod
    def authenticate_user(email: str, password: str, db: Session) -> Optional[User]:
        """
        Authenticate user by email and password

        Args:
            email: User email
            password: Plain text password
            db: Database session

        Returns:
            User object if authentication successful, None otherwise
        """
        user = db.query(User).filter(User.email == email).first()

        if not user:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        if not user.is_active:
            return None

        return user

    @staticmethod
    def create_user_token(user: User) -> JWTTokenResponse:
        """
        Create JWT token for user

        Args:
            user: User object

        Returns:
            JWT token response with access token
        """
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username},
            expires_delta=access_token_expires,
        )

        return JWTTokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
        )
