# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 📚 Documentation Navigation

**Quick Links:**
- 🚀 [Development Commands & Workflows](./docs/claude/DEVELOPMENT.md) - All commands, docker, utilities
- 🧪 [Testing Guide](./docs/claude/TESTING.md) - Testing patterns, fixtures, best practices
- 🔧 [Troubleshooting](./docs/claude/TROUBLESHOOTING.md) - Common issues and solutions
- 🏥 [Health Checks](./docs/HEALTH_CHECKS.md) - Health monitoring system
- 🚢 [Deployment](./docs/DEPLOYMENT_TAILSCALE.md) - Docker deployment with Tailscale VPN

## Project Overview

**Zenzefi Backend** - Authentication and proxy server for controlling access to Zenzefi (Windows 11) via time-based access tokens. The server acts as an intermediary between desktop clients and the target server, enabling monetization through token-based access control.

**Current Status:** v0.2.0-beta - Token scope system implemented for DTS Monaco access control. All core authentication, token generation, proxy functionality, cookie-based authentication, and scope-based access control implemented and tested (115/115 tests passing, 85%+ code coverage).

## Tech Stack

- **Python 3.13+** - Runtime environment
- **FastAPI 0.119+** - Async web framework
- **PostgreSQL 15+** - Primary database (SQLAlchemy 2.0 ORM)
- **Redis 7+** - Token caching, sessions, health check results
- **Alembic** - Database migrations
- **Pydantic v2** - Data validation
- **PyJWT** - JWT tokens for API authentication
- **APScheduler** - Background tasks for health checks (50s interval)
- **pytest** - Testing framework with real PostgreSQL and Redis
- **Poetry** - Dependency management

## Quick Start

```bash
# Start development environment
docker-compose -f docker-compose.dev.yml up -d
poetry run alembic upgrade head
python run_dev.py

# Run tests
poetry run pytest tests/ -v

# Create migration
poetry run alembic revision --autogenerate -m "Description"
```

**See [DEVELOPMENT.md](./docs/claude/DEVELOPMENT.md) for all commands.**

## Architecture

### Request Flow

**Full Architecture (Desktop Client + Browser):**
```
[Browser] → [Local Proxy (HTTPS)] → [FastAPI Backend] → [Zenzefi Server]
   Cookie         SSL Termination      Cookie Validation     X-Access-Token
                                       Token Validation
                                             ↓
                                      [PostgreSQL] + [Redis Cache]
```

**Two Token Types:**
1. **JWT Tokens** - For API authentication (register, login, purchase tokens)
2. **Access Tokens** - For proxy access to Zenzefi server (64-char random strings)

**Two Authentication Methods:**
1. **JWT Authentication** - For API endpoints (`Authorization: Bearer token`)
2. **Cookie Authentication** - For desktop client browser access (`zenzefi_access_token` cookie)

### Layer Architecture

```
app/
├── api/v1/          # HTTP endpoints (auth, tokens, users, proxy)
├── services/        # Business logic (auth, token, proxy, content rewriting, health)
├── models/          # SQLAlchemy ORM (User, AccessToken)
├── schemas/         # Pydantic validation
├── core/            # Core utilities (security, database, redis, logging, health scheduler)
├── config.py        # Application settings
└── main.py          # FastAPI application entry point
```

### Key Services

**TokenService** (`app/services/token_service.py`):
- Generates 64-char URL-safe random tokens (`secrets.token_urlsafe(48)`)
- Two-tier validation: Redis cache (~1ms) → PostgreSQL (~10ms)
- Activates token on first use (sets `activated_at`)
- Filters: `is_active=True`, `revoked_at=None`, not expired

**AuthService** (`app/services/auth_service.py`):
- User registration with bcrypt password hashing
- JWT payload: `{"sub": user_id, "username": username}` (NOT email)
- JWT expires in 60 minutes (configurable)

**ProxyService** (`app/services/proxy_service.py`):
- HTTP and WebSocket proxying to Zenzefi server
- Content rewriting via JavaScript injection
- Note: Desktop Client does NOT have ContentRewriter - this is ONLY in Backend

**HealthCheckService** (`app/services/health_service.py`):
- Checks PostgreSQL, Redis, and Zenzefi server
- Overall status: healthy (all up), degraded (Zenzefi down), unhealthy (DB/Redis down)
- Results cached in Redis (TTL: 120 seconds)
- Background scheduler runs every 50 seconds

### Database Models

**User** (`app/models/user.py`):
- Fields: id (UUID), email, username, hashed_password, full_name, is_active, is_superuser
- Relationships: tokens (one-to-many with AccessToken, cascade delete)

**AccessToken** (`app/models/token.py`):
- Fields: id (UUID), user_id (FK), token (random string), duration_hours, scope, activated_at, is_active, revoked_at
- `scope` - Access scope: "full" (default) or "certificates_only" (added in v0.2.0)
- `expires_at` - **computed property** (activated_at + duration_hours), NOT stored in DB
- Valid durations: 1, 12, 24, 168 (week), 720 (month) hours

### Redis Cache Structure

```python
# Active tokens (fast validation)
Key: "active_token:{sha256(token)}"
Value: {
    "user_id": "uuid",
    "token_id": "uuid",
    "expires_at": "ISO",
    "duration_hours": int,
    "scope": "full|certificates_only"  # Added in v0.2.0
}
TTL: Until token expiration

# Health check results
Key: "health:status"
Value: {"status": "healthy|degraded|unhealthy", "timestamp": "ISO", "checks": {...}}
TTL: 120 seconds
```

## Configuration

### Required Environment Variables (.env)

```bash
SECRET_KEY=your-secret-key-here
POSTGRES_SERVER=localhost
POSTGRES_USER=zenzefi
POSTGRES_PASSWORD=your-password
POSTGRES_DB=zenzefi_dev
REDIS_HOST=localhost
REDIS_PORT=6379
ZENZEFI_TARGET_URL=https://zenzefi.melxiory.ru
BACKEND_URL=http://localhost:8000
```

### Optional Variables

```bash
DEBUG=False
ACCESS_TOKEN_EXPIRE_MINUTES=60
COOKIE_SECURE=False  # True in production
COOKIE_SAMESITE=lax  # "none" in production with HTTPS
HEALTH_CHECK_INTERVAL=50
HEALTH_CHECK_TIMEOUT=10.0
```

## API Endpoints

### Authentication (`/api/v1/auth`)
- `POST /register` - Register new user
- `POST /login` - Login, returns JWT token

### Tokens (`/api/v1/tokens`)
- `POST /purchase` - Create access token (JWT auth required, MVP: free)
- `GET /my-tokens?active_only=true` - List user's tokens

## Token Scopes (Access Control)

**Version:** 0.2.0-beta (Added 2025-11-10)

Access tokens support **scope-based access control** to limit which endpoints can be accessed:

### Scope Types

| Scope | Access | Use Case |
|-------|--------|----------|
| `full` | All Zenzefi endpoints | Desktop Client, administrators |
| `certificates_only` | Only `/certificates/*` paths | DTS Monaco, restricted applications |

### Purchasing Scoped Tokens

```bash
# Full access token (default)
POST /api/v1/tokens/purchase
Authorization: Bearer {jwt_token}
{
  "duration_hours": 24,
  "scope": "full"
}

# Certificates-only token
POST /api/v1/tokens/purchase
Authorization: Bearer {jwt_token}
{
  "duration_hours": 24,
  "scope": "certificates_only"
}
```

### Using Scoped Tokens

```bash
# ✅ Allowed with certificates_only scope
GET /api/v1/proxy/certificates/filter
X-Access-Token: {certificates_only_token}

# ❌ Blocked with certificates_only scope (403 Forbidden)
GET /api/v1/proxy/users/currentUser
X-Access-Token: {certificates_only_token}
```

### Allowed Paths for `certificates_only`

**Certificate Operations:**
- `/certificates/filter` - List/search certificates
- `/certificates/details/{id}` - Get certificate details
- `/certificates/export/{id}` - Export certificate
- `/certificates/import/*` - Import certificates
- `/certificates/remove` - Remove certificates
- `/certificates/restore` - Restore certificates

**Certificate Testing:**
- `/certificates/activeForTesting` - Active certificates for testing
- `/certificates/activeForTesting/activate/{id}` - Activate certificate
- `/certificates/activeForTesting/deactivate/{id}` - Deactivate certificate
- `/certificates/activeForTesting/enhanced` - Enhanced testing info
- `/certificates/activeForTesting/options/{id}` - Testing options
- `/certificates/activeForTesting/usecases/{id}` - Use cases

**Certificate Updates & Integrity:**
- `/certificates/update/{id}` - Update certificate
- `/certificates/update/cancel` - Cancel update
- `/certificates/update/metrics` - Update metrics
- `/certificates/checkSystemIntegrityReport` - System integrity report
- `/certificates/checkSystemIntegrityLog` - System integrity log
- `/certificates/checkSystemIntegrityLogExistance` - Check log existence

**UI Configuration:**
- `/configurations/certificatesColumnOrder` - Column order settings
- `/configurations/certificatesColumnVisibility` - Column visibility settings

### Implementation Details

**Validation Location:** `app/core/permissions.py`
- `validate_path_access(path, scope)` - Check if path allowed for scope
- `SCOPE_PERMISSIONS` - Dictionary mapping scopes to allowed regex patterns

**Enforcement Points:**
- HTTP Proxy: `app/api/v1/proxy.py` - Validates before forwarding to Zenzefi
- WebSocket: Blocked entirely for `certificates_only` scope
- Validation happens **before** backend forwards request to Zenzefi

**Redis Cache Structure (Updated):**
```python
Key: "active_token:{sha256(token)}"
Value: {
    "user_id": "uuid",
    "token_id": "uuid",
    "expires_at": "ISO",
    "duration_hours": int,
    "scope": "full|certificates_only"  # Added in v0.2.0
}
```

**Adding New Allowed Paths:**

Edit `app/core/permissions.py` → `SCOPE_PERMISSIONS["certificates_only"]`:
```python
SCOPE_PERMISSIONS = {
    "certificates_only": [
        r"^certificates/newEndpoint",  # Add new allowed path
        # ... existing paths
    ]
}
```

### Desktop Client Compatibility

**No changes required** - Desktop Client is scope-agnostic:
- Desktop Client simply forwards tokens (cookie or header)
- Scope validation happens entirely in Backend
- Tokens with any scope work transparently through Desktop Client
- Desktop Client does NOT create tokens (tokens created via Backend API)

### Health Check
- `GET /health` - Simple health check (~1ms from Redis cache)
- `GET /health/detailed` - Detailed health with latency measurements

### Proxy (`/api/v1/proxy`)
- `POST /authenticate` - Set authentication cookie
- `GET /status` - Check authentication status
- `DELETE /logout` - Delete authentication cookie
- `ALL /{path:path}` - Proxy HTTP request to Zenzefi
- `WS /{path:path}` - Proxy WebSocket connection

**Full API docs:** http://localhost:8000/docs (when running)

## Critical Implementation Details

### Cookie Authentication

**Cookie Path (CRITICAL):**
- Cookie `path` **MUST** be `"/"` (not `"/api/v1/proxy"`)
- Browser only sends cookies if request path matches cookie path
- Setting `path="/api/v1/proxy"` causes cookie not to be sent for `/` or other paths

**Cookie Settings:**
- Development (HTTP): `COOKIE_SECURE=False`, `COOKIE_SAMESITE="lax"`
- Production (HTTPS): `COOKIE_SECURE=True`, `COOKIE_SAMESITE="none"`
- `httponly=True` - Always enabled (XSS protection)
- Lifetime (`max_age`) - Matches token expiration

**Desktop Client Integration:**
- Desktop Client is a **simplified forwarding proxy** (no content rewriting, caching, or auth validation)
- Local proxy (`https://127.0.0.1:61000`) handles SSL termination only
- ALL business logic is in Backend Server
- Desktop Client forwards cookies and sends `X-Local-Url` header for proper URL rewriting

### Token Lifecycle

1. Check Redis cache (fast path, ~1ms)
2. If cache miss, query PostgreSQL (slow path, ~10ms) with filters:
   - `is_active = True`
   - `revoked_at = None`
   - Token not expired (activated_at + duration_hours > now)
3. Activate token on first use (set `activated_at`)
4. Update Redis cache with validated data

**Token Revocation:** Set `is_active=False` and `revoked_at=datetime.utcnow()`

### Token Expiration

**Important:** `expires_at` is a **computed property**, NOT a database column:
- Calculated as: `activated_at + timedelta(hours=duration_hours)`
- Returns `None` if token not yet activated
- Eliminates data duplication

### Timezone Handling

**In production code:** Use `datetime.utcnow()`

**In tests:** When comparing JWT token timestamps:
```python
# Use utcfromtimestamp, not fromtimestamp (timezone mismatch)
exp_time = datetime.utcfromtimestamp(decoded["exp"])
```

### Pydantic Version

Project uses **Pydantic v2**:
- `class Config` should migrate to `ConfigDict`
- `from_attributes = True` (was `orm_mode = True` in v1)

### FastAPI Status Codes

- **422** - Pydantic validation failure
- **400** - Business logic error
- **403** - Missing authentication credentials
- **401** - Invalid/expired credentials

## Testing

**Philosophy:** Integration testing with **real services** (PostgreSQL, Redis) - no mocks.

**Test Database:** `zenzefi_test` (separate from `zenzefi_dev`)

**Test organization:** 115 tests, 85%+ coverage
- `test_security.py` - Password hashing, JWT (14 tests)
- `test_auth_service.py` - Registration, login (10 tests)
- `test_token_service.py` - Token generation, caching (14 tests)
- `test_api_auth.py` - Auth API endpoints (13 tests)
- `test_api_tokens.py` - Token purchase API (16 tests)
- `test_cookie_auth.py` - Cookie authentication (11 tests)
- `test_permissions.py` - Token scope validation (8 tests)
- `test_token_scopes.py` - Scope integration tests (7 tests)
- `test_proxy_status.py` - Proxy status endpoint (4 tests)
- `test_health_service.py` - Health check service (15 tests)
- `test_main.py` - Health checks, CORS, routing (9 tests)

**See [TESTING.md](./docs/claude/TESTING.md) for detailed testing guide.**

## MCP Servers

MCP servers configured in `.mcp.json`:
- **postgres** - Direct SQL queries to zenzefi_dev database
- **docker** - Container status, logs, and operations
- **redis-tools** - Redis operations (`scripts/redis_mcp.py`)
- **zenzefi-api** - Programmatic access to backend API

## Notes for Claude Code

**Critical Information:**
- All tests must pass before considering work complete
- Use real Redis and PostgreSQL for integration testing (configured in `conftest.py`)
- Token validation uses two-tier caching: Redis (fast) → PostgreSQL (fallback)
- Access tokens are random strings (not JWTs) - distinct from API JWT tokens
- `expires_at` is a computed property, NOT a database column
- JWT payload structure: `{"sub": user_id, "username": username}` (NOT email)
- Cookie `path` MUST be `"/"` (not `/api/v1/proxy`) for browser compatibility
- `COOKIE_SECURE=False` in development (HTTP), `True` in production (HTTPS)
- Desktop Client is a **simplified forwarding proxy** - does NOT do content rewriting, caching, or auth validation
- Desktop Client forwards ALL requests to Backend Server (127.0.0.1:8000)
- Desktop Client sends `X-Local-Url` header so Backend knows to rewrite URLs for local proxy domain
- ALL business logic (auth, caching, rewriting, WebSocket) is in Backend Server
- Development primarily on Windows; commands may need adjustment for Linux/Mac
- **Timezone consistency (CRITICAL):**
  - Always use `datetime.now(timezone.utc)` for timezone-aware datetimes (NOT `datetime.utcnow()`)
  - When deserializing from Redis/ISO format: `datetime.fromisoformat()` may return timezone-naive datetime
  - **ALWAYS check timezone before comparison:** `if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)`
  - Tests JWT: use `datetime.utcfromtimestamp()` (not `fromtimestamp`)

**When writing code:**
- Follow existing patterns in codebase
- Add tests for new features (real services, no mocks)
- Update migrations for database changes
- Check DEVELOPMENT.md for command examples
- Check TROUBLESHOOTING.md if issues arise
