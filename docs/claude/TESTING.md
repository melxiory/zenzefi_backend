# Testing Guide

Comprehensive testing guide for zenzefi_backend with pytest, real services integration, and best practices.

## Testing Philosophy

This project uses **integration testing with real services** (PostgreSQL, Redis) instead of mocks. This approach:
- Tests actual database interactions
- Catches real-world issues early
- Validates service integration
- Ensures production-like behavior

## Test Setup

### Prerequisites

```bash
# 1. Ensure PostgreSQL and Redis are running
docker-compose -f docker-compose.dev.yml up -d

# 2. Create test database (one-time setup)
docker exec -it zenzefi-postgres-dev psql -U zenzefi -c "CREATE DATABASE zenzefi_test;"

# Or use the script
poetry run python scripts/create_test_database.py

# 3. Verify test database exists
docker exec -it zenzefi-postgres-dev psql -U zenzefi -c "\l" | grep zenzefi_test
```

### Test Database Configuration

Tests use a **separate database** (`zenzefi_test`) to avoid polluting development data:
- **Development DB:** `zenzefi_dev` (used by `python run_dev.py`)
- **Test DB:** `zenzefi_test` (used by `pytest`)

## Running Tests

### Basic Commands

```bash
# Run all tests with verbose output
poetry run pytest tests/ -v

# Run specific test file
poetry run pytest tests/test_api_tokens.py -v

# Run specific test class
poetry run pytest tests/test_api_tokens.py::TestTokenPurchaseEndpoint -v

# Run single test
poetry run pytest tests/test_api_tokens.py::TestTokenPurchaseEndpoint::test_purchase_token_success -v

# Run tests matching pattern
poetry run pytest tests/ -k "token" -v

# Run tests in parallel (faster, requires pytest-xdist)
poetry run pytest tests/ -n auto
```

### Coverage Reports

```bash
# Run with terminal coverage report
poetry run pytest tests/ --cov=app --cov-report=term

# Run with HTML coverage report (opens in browser)
poetry run pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html

# Run with missing lines report
poetry run pytest tests/ --cov=app --cov-report=term-missing

# Generate coverage badge
poetry run pytest tests/ --cov=app --cov-report=json
```

### Advanced Options

```bash
# Stop on first failure
poetry run pytest tests/ -x

# Show local variables on failure
poetry run pytest tests/ -l

# Show print statements
poetry run pytest tests/ -s

# Warnings as errors
poetry run pytest tests/ -W error

# Rerun failed tests
poetry run pytest tests/ --lf

# Run only failed tests from last run
poetry run pytest tests/ --ff
```

## Test Architecture

### Test Configuration (`tests/conftest.py`)

All tests share common fixtures defined in `conftest.py`:

```python
# Key fixtures available in all tests:
test_db          # Fresh PostgreSQL session (function scope)
fake_redis       # Real Redis client (function scope)
client           # FastAPI TestClient with overrides
test_user_data   # Sample user credentials
test_user_data_2 # Second user for multi-user tests
```

**Important characteristics:**
- PostgreSQL: Connects to `zenzefi_test` database (NOT `zenzefi_dev`)
- Redis: Uses real Redis (localhost:6379, db=0)
- Database: Fresh tables created/dropped for **each test** (function scope)
- Redis: Flushed before/after each test
- All tests are isolated and can run in parallel

### Test Organization

```
tests/
├── conftest.py                # Shared fixtures
├── test_security.py           # Password hashing, JWT (14 tests)
├── test_auth_service.py       # Registration, login (10 tests)
├── test_token_service.py      # Token generation, caching (14 tests)
├── test_api_auth.py           # Auth API endpoints (13 tests)
├── test_api_tokens.py         # Token purchase API (16 tests)
├── test_cookie_auth.py        # Cookie authentication (11 tests)
├── test_proxy_status.py       # Proxy status endpoint
└── test_main.py               # Health, CORS, routing (8 tests)
```

**Total:** 85+ tests with 85%+ code coverage

## Common Test Patterns

### Testing with Authentication

Tests that require authentication should define `authenticated_client` fixture **locally**:

```python
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def authenticated_client(client: TestClient, test_user_data: dict, fake_redis):
    """Create authenticated client with JWT token in headers"""
    # 1. Register user
    client.post("/api/v1/auth/register", json=test_user_data)

    # 2. Login to get JWT token
    login_data = {
        "email": test_user_data["email"],
        "password": test_user_data["password"]
    }
    login_response = client.post("/api/v1/auth/login", json=login_data)
    jwt_token = login_response.json()["access_token"]

    # 3. Add token to headers
    client.headers = {"Authorization": f"Bearer {jwt_token}"}
    return client

def test_purchase_token(authenticated_client: TestClient):
    """Test purchasing a token (JWT already in headers)"""
    response = authenticated_client.post(
        "/api/v1/tokens/purchase",
        json={"duration_hours": 24}
    )
    assert response.status_code == 201
    data = response.json()
    assert "token" in data
```

**Note:** `authenticated_client` is NOT in `conftest.py` - define it locally in each test file that needs it.

### Testing Token Activation

Access tokens activate on first use. To test activation:

```python
def test_token_activation(test_db, fake_redis):
    """Test that token activates on first validation"""
    from app.services.token_service import TokenService
    from app.models.token import AccessToken

    # 1. Create token
    token = TokenService.create_token(
        user_id=user_id,
        duration_hours=24,
        db=test_db
    )
    assert token.activated_at is None  # Not activated yet

    # 2. Clear Redis cache to force DB lookup
    fake_redis.flushall()

    # 3. Validate token (triggers activation)
    result = TokenService.validate_token(token.token, test_db)

    # 4. Verify activation
    test_db.refresh(token)
    assert token.activated_at is not None
    assert result is not None
```

### Testing Redis Cache

To test Redis caching behavior:

```python
def test_redis_caching(test_db, fake_redis):
    """Test that token validation uses Redis cache"""
    from app.services.token_service import TokenService

    # 1. Create and activate token
    token = TokenService.create_token(user_id=user_id, duration_hours=24, db=test_db)
    TokenService.validate_token(token.token, test_db)  # Activates and caches

    # 2. Verify token is in Redis
    token_hash = hashlib.sha256(token.token.encode()).hexdigest()
    cache_key = f"active_token:{token_hash}"
    cached_data = fake_redis.get(cache_key)
    assert cached_data is not None

    # 3. Test cache hit (no DB query)
    result = TokenService.validate_token(token.token, test_db)
    assert result is not None
```

### Testing API Endpoints

Standard pattern for API endpoint tests:

```python
def test_endpoint_success(client: TestClient):
    """Test successful API call"""
    response = client.post(
        "/api/v1/endpoint",
        json={"key": "value"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "expected_value"

def test_endpoint_validation_error(client: TestClient):
    """Test validation error (422)"""
    response = client.post(
        "/api/v1/endpoint",
        json={"invalid": "data"}
    )
    assert response.status_code == 422

def test_endpoint_unauthorized(client: TestClient):
    """Test unauthorized access (401)"""
    response = client.get("/api/v1/protected")
    assert response.status_code == 401
```

### Testing with Multiple Users

Use `test_user_data` and `test_user_data_2` for multi-user tests:

```python
def test_multiple_users(client: TestClient, test_user_data: dict, test_user_data_2: dict):
    """Test interaction between two users"""
    # Register first user
    client.post("/api/v1/auth/register", json=test_user_data)

    # Register second user
    client.post("/api/v1/auth/register", json=test_user_data_2)

    # Login as first user
    login1 = client.post("/api/v1/auth/login", json={
        "email": test_user_data["email"],
        "password": test_user_data["password"]
    })
    token1 = login1.json()["access_token"]

    # Test with first user's token
    client.headers = {"Authorization": f"Bearer {token1}"}
    response = client.get("/api/v1/users/me")
    assert response.json()["email"] == test_user_data["email"]
```

## Test Data Fixtures

### Built-in Fixtures (conftest.py)

```python
# User data for tests
test_user_data = {
    "email": "test@example.com",
    "username": "testuser",
    "password": "testpass123",
    "full_name": "Test User"
}

test_user_data_2 = {
    "email": "test2@example.com",
    "username": "testuser2",
    "password": "testpass456",
    "full_name": "Test User 2"
}
```

### Creating Custom Fixtures

Define fixtures locally in test files when needed:

```python
@pytest.fixture
def sample_token(test_db, test_user_data):
    """Create a sample access token"""
    from app.services.auth_service import AuthService
    from app.services.token_service import TokenService

    # Register user
    user = AuthService.register_user(test_user_data, test_db)

    # Create token
    token = TokenService.create_token(
        user_id=str(user.id),
        duration_hours=24,
        db=test_db
    )
    return token
```

## Important Testing Notes

### Timezone Handling

**In production code:** Use `datetime.utcnow()`

**In tests:** When comparing JWT token timestamps:
```python
from datetime import datetime

# CORRECT: Use utcfromtimestamp
exp_time = datetime.utcfromtimestamp(decoded["exp"])
iat_time = datetime.utcfromtimestamp(decoded["iat"])

# WRONG: fromtimestamp causes timezone mismatch
exp_time = datetime.fromtimestamp(decoded["exp"])  # Don't do this!
```

### Database State

Each test gets a **fresh database**:
- Tables created before test
- Tables dropped after test
- No state persists between tests
- Tests can run in any order

### Redis State

Redis is **flushed** before/after each test:
- No cache pollution between tests
- Each test starts with empty Redis
- Use `fake_redis.flushall()` to manually clear during test

### FastAPI TestClient

`client` fixture provides TestClient with overrides:
- Uses `zenzefi_test` database
- Uses real Redis
- Doesn't require server to be running
- Synchronous (no async/await needed in tests)

## Writing New Tests

### Step-by-Step Guide

1. **Choose appropriate test file** (or create new one)
2. **Import necessary fixtures** from `conftest.py`
3. **Write test function** with descriptive name
4. **Use fixtures** as function parameters
5. **Follow AAA pattern** (Arrange, Act, Assert)
6. **Test edge cases** and error conditions
7. **Run tests** to verify

Example:

```python
def test_new_feature(test_db, client: TestClient, test_user_data: dict):
    """Test new feature with clear description"""
    # Arrange: Set up test data
    user = create_test_user(test_user_data, test_db)

    # Act: Perform the action
    response = client.post("/api/v1/new-feature", json={"data": "value"})

    # Assert: Verify results
    assert response.status_code == 200
    assert response.json()["result"] == "expected"
```

## Debugging Failed Tests

### View Test Output

```bash
# Show print statements
poetry run pytest tests/test_file.py -s

# Show local variables on failure
poetry run pytest tests/test_file.py -l

# Increase verbosity
poetry run pytest tests/test_file.py -vv
```

### Use Debugger

```python
# Add breakpoint in test
def test_something():
    import pdb; pdb.set_trace()
    # Test code here
```

### Check Database State

```python
def test_with_db_inspection(test_db):
    # Inspect database during test
    from app.models.user import User
    users = test_db.query(User).all()
    print(f"Users in DB: {len(users)}")
```

### Check Redis State

```python
def test_with_redis_inspection(fake_redis):
    # Inspect Redis during test
    keys = fake_redis.keys("*")
    print(f"Redis keys: {keys}")
```

## Best Practices

1. **Use descriptive test names** - `test_purchase_token_with_invalid_duration`
2. **One assertion per test** - Tests should fail for one reason
3. **Test edge cases** - Empty input, max values, invalid data
4. **Clean up resources** - Fixtures handle this automatically
5. **Don't rely on test order** - Tests should be independent
6. **Use fixtures** - Don't duplicate setup code
7. **Test error cases** - Not just happy path
8. **Keep tests fast** - Avoid unnecessary sleeps
9. **Mock external APIs** - Don't call real external services
10. **Run tests before commit** - Ensure nothing breaks

## Coverage Goals

- **Minimum coverage:** 80%
- **Current coverage:** 85%+
- **Target coverage:** 90%+

Files with low coverage are candidates for more tests.

## CI/CD Integration

Tests run automatically on:
- Pull requests
- Main branch commits
- Scheduled nightly runs

CI configuration ensures:
- Fresh PostgreSQL and Redis containers
- Test database creation
- All tests pass before merge

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy testing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#session-frequently-asked-questions)
- Project CLAUDE.md for architecture overview
