"""
Create superuser script.
Creates an admin user with superuser privileges.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import User
from loguru import logger


def create_superuser(email: str, username: str, password: str, full_name: str = None):
    """Create a superuser"""
    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            logger.error(f"User with email {email} already exists!")
            return False

        existing_username = db.query(User).filter(User.username == username).first()
        if existing_username:
            logger.error(f"User with username {username} already exists!")
            return False

        # Create superuser
        hashed_password = get_password_hash(password)
        superuser = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            full_name=full_name,
            is_active=True,
            is_superuser=True,
        )

        db.add(superuser)
        db.commit()
        db.refresh(superuser)

        logger.info(f"Superuser created successfully!")
        logger.info(f"  Email: {email}")
        logger.info(f"  Username: {username}")
        logger.info(f"  ID: {superuser.id}")

        return True

    except Exception as e:
        logger.error(f"Error creating superuser: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    import getpass

    print("=== Create Superuser ===")
    email = input("Email: ")
    username = input("Username: ")
    password = getpass.getpass("Password: ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        logger.error("Passwords do not match!")
        sys.exit(1)

    full_name = input("Full name (optional): ") or None

    success = create_superuser(email, username, password, full_name)
    sys.exit(0 if success else 1)
