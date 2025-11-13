"""
Pytest fixtures and configuration for Zenzefi Backend tests
"""
import os
import pytest
from typing import Generator
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

from app.core.database import Base, get_db
from app.main import app
from app.config import Settings


# Test database setup - use SEPARATE PostgreSQL test database
# IMPORTANT: Tests use zenzefi_test (NOT zenzefi_dev!) to avoid dropping production tables
# This requires docker-compose.dev.yml to be running with postgres service
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg2://zenzefi:devpassword@localhost:5432/zenzefi_test"
)


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """
    Create a test database session for each test

    Uses PostgreSQL test database. Requires docker-compose.dev.yml to be running.
    Creates and drops all tables for each test to ensure test isolation.
    """
    # Create engine
    engine = create_engine(TEST_DATABASE_URL, echo=False)

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session factory
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create session
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        # Clean up - drop all tables after test
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(scope="function")
def fake_redis():
    """
    Create a real Redis client for testing

    Connects to real Redis running in Docker and clears data before/after each test.
    Requires: docker-compose.dev.yml with redis service running
    """
    import redis

    # Connect to real Redis
    redis_client = redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    # Clear Redis before test
    redis_client.flushdb()

    yield redis_client

    # Clear Redis after test
    redis_client.flushdb()
    redis_client.close()


@pytest.fixture(scope="function")
def client(test_db: Session, fake_redis, monkeypatch) -> Generator[TestClient, None, None]:
    """
    Create a test client with database and Redis dependency overrides

    This fixture provides a FastAPI TestClient that uses:
    - Test database instead of real database
    - Fake Redis instead of real Redis
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Mock Redis client to use fake Redis - using monkeypatch for duration of test
    monkeypatch.setattr('app.core.redis.get_redis_client', lambda: fake_redis)
    monkeypatch.setattr('app.services.token_service.get_redis_client', lambda: fake_redis)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_settings() -> Settings:
    """
    Create test settings with safe defaults

    Overrides production settings with test-safe values
    """
    return Settings(
        PROJECT_NAME="Zenzefi Backend Test",
        VERSION="1.0.0-test",
        DEBUG=True,
        SECRET_KEY="test-secret-key-for-testing-only-do-not-use-in-production",
        ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=60,
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        POSTGRES_DB="test_db",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD=None,
        ZENZEFI_TARGET_URL="https://test-zenzefi-server",
    )


@pytest.fixture
def test_user_data() -> dict:
    """
    Sample user data for testing
    """
    return {
        "email": "testuser@example.com",
        "username": "testuser",
        "password": "TestPass123!",
        "full_name": "Test User",
    }


@pytest.fixture
def test_user_data_2() -> dict:
    """
    Second sample user data for testing multiple users
    """
    return {
        "email": "testuser2@example.com",
        "username": "testuser2",
        "password": "TestPass456!",
        "full_name": "Test User 2",
    }


@pytest.fixture
def test_user(test_db: Session, test_user_data: dict):
    """
    Create a real user in the test database with 0 balance (default)
    """
    from decimal import Decimal
    from app.models import User
    from app.core.security import get_password_hash

    user = User(
        email=test_user_data["email"],
        username=test_user_data["username"],
        hashed_password=get_password_hash(test_user_data["password"]),
        full_name=test_user_data.get("full_name"),
        is_active=True,
        is_superuser=False,
        currency_balance=Decimal("0.00"),  # Default: no balance
    )

    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    return user


@pytest.fixture
def test_user_with_balance(test_db: Session, test_user_data: dict):
    """
    Create a real user in the test database with 1000 ZNC balance
    (for tests that need to purchase tokens without explicit balance top-up)
    """
    from decimal import Decimal
    from app.models import User
    from app.core.security import get_password_hash

    user = User(
        email=test_user_data["email"],
        username=test_user_data["username"],
        hashed_password=get_password_hash(test_user_data["password"]),
        full_name=test_user_data.get("full_name"),
        is_active=True,
        is_superuser=False,
        currency_balance=Decimal("1000.00"),  # Pre-funded for token purchases
    )

    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    return user


@pytest.fixture(scope="function", autouse=True)
def override_token_prices(monkeypatch):
    """
    Override token prices for testing (ensure non-zero prices)
    """
    from decimal import Decimal
    from app.config import settings

    # Set test prices
    monkeypatch.setattr(settings, "TOKEN_PRICE_1H", Decimal("1.00"))
    monkeypatch.setattr(settings, "TOKEN_PRICE_12H", Decimal("10.00"))
    monkeypatch.setattr(settings, "TOKEN_PRICE_24H", Decimal("18.00"))
    monkeypatch.setattr(settings, "TOKEN_PRICE_7D", Decimal("100.00"))
    monkeypatch.setattr(settings, "TOKEN_PRICE_30D", Decimal("300.00"))
