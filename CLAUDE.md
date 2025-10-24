# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Zenzefi Backend - Authentication and proxy server for controlling access to Zenzefi (Windows 11) via time-based access tokens. The server acts as an intermediary between desktop clients and the target server, enabling monetization through token-based access control.

**Current Status:** MVP Phase (Этап 1) - All core authentication, token generation, and proxy functionality implemented and tested (74/74 tests passing, 84% code coverage).

## Tech Stack

- **FastAPI 0.119+** - Async web framework
- **PostgreSQL 15+** - Primary database (SQLAlchemy 2.0 ORM)
- **Redis 7+** - Token caching, sessions
- **Alembic** - Database migrations
- **Pydantic v2** - Data validation
- **PyJWT** - JWT tokens for API authentication
- **pytest** - Testing framework with real PostgreSQL and Redis

## Common Commands

### Development Server

```bash
# Start dev server with hot reload
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start database and Redis (required for development)
docker-compose -f docker-compose.dev.yml up -d

# Stop services
docker-compose -f docker-compose.dev.yml down
```

### Database Migrations

```bash
# Create new migration (autogenerate from models)
poetry run alembic revision --autogenerate -m "Description"

# Apply all migrations
poetry run alembic upgrade head

# Rollback one migration
poetry run alembic downgrade -1

# View migration history
poetry run alembic history

# View current database version
poetry run alembic current
```

### Testing

```bash
# Run all tests (requires docker-compose.dev.yml services running)
poetry run pytest tests/ -v

# Run specific test file
poetry run pytest tests/test_api_tokens.py -v

# Run single test
poetry run pytest tests/test_api_tokens.py::TestTokenPurchaseEndpoint::test_purchase_token_success -v

# Run with coverage
poetry run pytest tests/ --cov=app --cov-report=term

# Run with HTML coverage report
poetry run pytest tests/ --cov=app --cov-report=html
```

**Important:** Tests require PostgreSQL and Redis running via `docker-compose.dev.yml`. Tests use real services, not mocks, for integration testing.

### Code Quality

```bash
# Format code
poetry run black app/

# Sort imports
poetry run isort app/

# Lint
poetry run flake8 app/

# Type checking
poetry run mypy app/
```

## Architecture

### Request Flow

```
[Desktop Client] → [FastAPI Backend] → [Zenzefi Server]
   JWT Auth         Token Validation     X-Access-Token
                           ↓
                    [PostgreSQL] + [Redis Cache]
```

**Two Token Types:**
1. **JWT Tokens** - For API authentication (register, login, purchase tokens)
2. **Access Tokens** - For proxy access to Zenzefi server (used by desktop client)

### Layer Architecture

```
app/
├── api/v1/           # HTTP endpoints (auth, tokens, users, proxy)
├── services/         # Business logic layer
│   ├── auth_service.py       # User registration, authentication
│   ├── token_service.py      # Token generation, validation, caching
│   ├── proxy_service.py      # HTTP/WebSocket proxying
│   └── content_rewriter.py   # URL rewriting for proxied content
├── models/           # SQLAlchemy ORM models (User, AccessToken)
├── schemas/          # Pydantic validation schemas
├── core/             # Core utilities (security, database, redis, logging)
└── main.py           # FastAPI application entry point
```

### Key Services

**TokenService** (`app/services/token_service.py`):
- Generates URL-safe random access tokens (48 bytes = 64 chars)
- Two validation methods:
  - `validate_token()` - validates AND activates token on first use
  - `check_token_status()` - read-only check without activation
- Validates tokens with Redis cache (fast path) + PostgreSQL (slow path)
- Activates token on first use (sets `activated_at`)
- Caches only activated tokens in Redis (TTL = expires_at)
- Filters: `is_active=True`, `revoked_at=None`, not expired

**AuthService** (`app/services/auth_service.py`):
- User registration with bcrypt password hashing
- Login with JWT token generation
- JWT payload: `{"sub": user_id, "username": username}` (NOT email)
- JWT expires in 60 minutes (configurable via ACCESS_TOKEN_EXPIRE_MINUTES)

**ProxyService** (`app/services/proxy_service.py`):
- HTTP and WebSocket proxying to Zenzefi server
- HTTP: Uses httpx with SSL verification disabled (internal VPN)
- WebSocket: Uses websockets library for bidirectional communication
- Validates X-Access-Token for each request (HTTP header or WS query param)
- Forwards requests with custom headers (X-User-Id, X-Token-Id)
- Content rewriting: Injects JavaScript to intercept fetch/XHR/WebSocket
- Supports HTTP Basic Auth for upstream server (optional)

**ContentRewriter** (`app/services/content_rewriter.py`):
- URL rewriting in proxied content (HTML, CSS, JS, JSON)
- Rewrites relative URLs to use proxy prefix (/api/v1/proxy)
- Handles Location headers and other URL-based response headers
- Singleton pattern with lazy initialization in ProxyService

### Database Models

**User** (`app/models/user.py`):
- Fields: id (UUID), email, username, hashed_password, full_name, is_active, is_superuser, created_at, updated_at
- Indexed: email, username (unique indexes)
- Relationships: tokens (one-to-many with AccessToken, cascade delete)

**AccessToken** (`app/models/token.py`):
- Fields: id (UUID), user_id (FK), token (random string), duration_hours, activated_at, is_active, revoked_at, created_at
- `expires_at` - calculated property (activated_at + duration_hours), not stored in DB
- `revoked_at` - timestamp of manual token revocation (NULL = not revoked)
- Validation checks: `is_active=True`, `revoked_at=None`, and token not expired
- Valid durations: 1, 12, 24, 168 (week), 720 (month) hours
- Token format: 64-char URL-safe string (`secrets.token_urlsafe(48)`)

### Redis Cache Structure

```python
# Active tokens (fast validation)
Key: "active_token:{sha256(token)}"
Value: JSON {
    "user_id": "uuid",
    "token_id": "uuid",
    "expires_at": "ISO timestamp",
    "duration_hours": int
}
TTL: Until token expiration
```

### API Authentication

**JWT Authentication** (for API endpoints):
- Header: `Authorization: Bearer {jwt_token}`
- Dependencies: `get_current_user()` or `get_current_active_user()` from `app/api/deps.py`
- Token generated on login, expires in 60 minutes (configurable)

**Access Token Authentication** (for proxy):
- Header: `X-Access-Token: {access_token_string}`
- Validated by TokenService on each proxy request
- No user dependency - validated directly in proxy endpoint

## Testing Architecture

### Test Setup (`tests/conftest.py`)

Tests use **real services** (not mocks):
- PostgreSQL: Connects to `zenzefi_test` database (NOT zenzefi_dev!) (localhost:5432)
- Redis: Connects to real Redis (localhost:6379, db=0)
- Database: Fresh tables created/dropped for each test (function scope)
- Redis: Flushed before/after each test
- All tests are isolated and can run in parallel

### Key Fixtures

```python
test_db          # Fresh PostgreSQL session (creates/drops tables)
fake_redis       # Real Redis client (flushes before/after test)
client           # FastAPI TestClient with DB + Redis overrides
authenticated_client  # Client with registered user + JWT token
test_user_data   # Sample user credentials
```

### Test Organization

- `test_security.py` - Password hashing, JWT operations (14 tests)
- `test_auth_service.py` - Registration, authentication logic (10 tests)
- `test_token_service.py` - Token generation, validation, caching (14 tests)
- `test_api_auth.py` - Auth API endpoints (13 tests)
- `test_api_tokens.py` - Token purchase/validation endpoints (16 tests)
- `test_main.py` - Health checks, CORS, routing (8 tests)

### Common Test Patterns

**Testing token activation:**
```python
# Clear Redis cache to force DB lookup
fake_redis.flushall()
TokenService.validate_token(token.token, test_db)
# Token should now be activated
assert token.activated_at is not None
```

**Testing API with authentication:**
```python
def test_something(authenticated_client: TestClient):
    # JWT token already in headers
    response = authenticated_client.post("/api/v1/tokens/purchase",
                                         json={"duration_hours": 24})
    assert response.status_code == 201
```

## Configuration

### Environment Variables (.env)

Required variables:
- `SECRET_KEY` - JWT signing key (HS256 algorithm)
- `POSTGRES_SERVER`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` - Database connection
- `REDIS_HOST`, `REDIS_PORT` - Redis connection (default: redis:6379)
- `ZENZEFI_TARGET_URL` - Target Zenzefi server URL for proxying
- `BACKEND_URL` - Backend URL for content rewriter (e.g., http://localhost:8000)

Optional:
- `DEBUG` - Debug mode (default: False)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - JWT expiration (default: 60)
- `REDIS_PASSWORD` - Redis password (default: None)
- `REDIS_DB` - Redis database number (default: 0)
- `ZENZEFI_BASIC_AUTH_USER`, `ZENZEFI_BASIC_AUTH_PASSWORD` - HTTP Basic Auth for upstream
- `TOKEN_PRICE_*` - Token pricing (currently 0.0 for MVP)

### Database Connection

SQLAlchemy URL assembled from environment:
```
postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}/{POSTGRES_DB}
```

Connection pooling configured in `app/core/database.py`.

## API Endpoints

### Authentication (`/api/v1/auth`)
- `POST /register` - Register new user
- `POST /login` - Login, returns JWT token

### Users (`/api/v1/users`)
- `GET /me` - Get current user profile (JWT auth required)

### Tokens (`/api/v1/tokens`)
- `POST /purchase` - Create access token (JWT auth required, MVP: free)
  - Body: `{"duration_hours": 1|12|24|168|720}`
  - Returns: TokenResponse with token string
- `GET /my-tokens?active_only=true` - List user's tokens (JWT auth required)
  - Query param: `active_only` (default: true)
  - Returns: List of TokenResponse

### Proxy (`/api/v1/proxy`)
- `ALL /{path:path}` - Proxy HTTP request to Zenzefi (X-Access-Token required)
- `WS /{path:path}` - Proxy WebSocket connection (token via query param)
  - WebSocket URL format: `/api/v1/proxy/path?token=<access_token>`
  - Token validated before establishing connection

### Schema Field Mapping

**Important:** `TokenResponse` schema uses field aliasing:
```python
token_id: UUID = Field(..., alias="id")  # Maps model.id → response.token_id
populate_by_name = True  # Allows both 'id' and 'token_id'
```

This prevents serialization errors when returning AccessToken models from endpoints.

## Critical Implementation Details

### Token Validation Flow

1. Check Redis cache (fast path, ~1ms)
2. If cache miss, query PostgreSQL (slow path, ~10ms) with filters:
   - `is_active = True` (general active status)
   - `revoked_at = None` (not manually revoked)
   - Token not expired (activated_at + duration_hours > now)
3. Activate token on first use (set `activated_at`)
4. Update Redis cache with validated data
5. Return validation result

**Token Revocation:** To revoke a token manually, set `is_active=False` and `revoked_at=datetime.utcnow()`. This immediately invalidates the token and records the revocation timestamp for audit purposes.

### Token Expiration Calculation

**Important:** `expires_at` is a **computed property**, not a database column:
- Removed from database schema (migration: "Remove expires_at column")
- Calculated as: `activated_at + timedelta(hours=duration_hours)`
- Returns `None` if token not yet activated
- Eliminates data duplication and potential sync issues between stored expiration and activation time

### Timezone Handling

**In production code:** Use `datetime.utcnow()` (will be migrated to `datetime.now(datetime.UTC)` in future)

**In tests:** When comparing timestamps from JWT tokens:
```python
# Use utcfromtimestamp, not fromtimestamp (timezone mismatch)
exp_time = datetime.utcfromtimestamp(decoded["exp"])
iat_time = datetime.utcfromtimestamp(decoded["iat"])
```

### Pydantic Version

Project uses **Pydantic v2**. Some deprecation warnings exist:
- `class Config` should migrate to `ConfigDict`
- `from_attributes = True` (was `orm_mode = True` in v1)

### FastAPI Status Codes

- **422 Unprocessable Entity** - Pydantic validation failure (e.g., duration_hours < 1)
- **400 Bad Request** - Business logic error (e.g., invalid duration not in allowed list)
- **403 Forbidden** - Missing authentication credentials
- **401 Unauthorized** - Invalid/expired credentials

## Development Workflow

### Adding New Endpoint

1. Create/update schema in `app/schemas/`
2. Add endpoint to router in `app/api/v1/`
3. Implement business logic in `app/services/`
4. Write tests in `tests/test_api_*.py`
5. Run tests: `poetry run pytest tests/ -v`

### Adding Database Model

1. Create model in `app/models/`
2. Import in `app/models/__init__.py`
3. Create migration: `poetry run alembic revision --autogenerate -m "Add table"`
4. Review generated migration in `alembic/versions/`
5. Apply migration: `poetry run alembic upgrade head`
6. Update tests to use new model

### Modifying Existing Tests

When changing API behavior:
1. Run tests to see failures: `poetry run pytest tests/ -v`
2. Update test assertions to match new behavior
3. Check test documentation for expected status codes
4. Verify all related tests still pass

## Next Development Phases

### Этап 2: Currency System (Planned)
- Add `currency_balance` to User model
- Create Transaction model for tracking purchases
- Implement token pricing (deduct from balance)
- Add refund system for unused tokens

### Этап 3: Monitoring (Planned)
- ProxySession model (track active connections)
- Admin endpoints for user/token management
- Prometheus metrics integration

### Этап 4: Production (Planned)
- Nginx with SSL/TLS
- Rate limiting middleware
- CORS configuration for specific origins
- CI/CD pipeline setup

## Helpful Resources

- **API Docs (when running):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

## Notes for Claude Code

- All tests must pass before considering work complete
- Use real Redis and PostgreSQL for integration testing (configured in conftest.py)
- Token validation uses two-tier caching: Redis (fast) → PostgreSQL (fallback)
- Access tokens are random strings (not JWTs) - distinct from API JWT tokens
- Test fixtures automatically clean up: tables dropped, Redis flushed
- Timezone consistency: use `datetime.utcfromtimestamp()` in tests, `datetime.utcnow()` in code
