"""
Database initialization script.
Creates all tables and optionally creates a superuser.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import engine, Base
from app.models import User, AccessToken
from loguru import logger


def init_db():
    """Initialize database - create all tables"""
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully!")


if __name__ == "__main__":
    init_db()
