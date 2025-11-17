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

**Zenzefi Backend** - Authentication and proxy server for controlling access to Zenzefi (Windows 11) via time-based access tokens. The server acts as an intermediary between applications (like DTS Monaco) and the target server, enabling monetization through token-based access control.

**Current Status:** v0.5.0-beta - Device conflict detection implemented ("1 token = 1 device" policy). All core authentication, token generation, proxy functionality, scope-based access control, device conflict detection, and monetization features tested (156/156 tests passing, 85%+ code coverage).

**Phase Status:**
- ✅ Phase 1 (MVP): Core authentication, tokens, HTTP proxy, health checks - COMPLETED
- ✅ Phase 2 (Currency System): ZNC balance, transactions, payment gateway, refunds - COMPLETED
- ✅ Phase 3 (Monitoring): ProxySession tracking with device conflict detection, session timeout - COMPLETED
- ⏳ Phase 4 (Production): Rate limiting, CI/CD, backups - PARTIALLY (Docker deployment done)

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

**Simplified Architecture (DTS Monaco Integration):**
```
[Application] → [FastAPI Backend] → [Zenzefi Server]
(DTS Monaco)    X-Access-Token      Token Validation
                + X-Device-ID       + Device Conflict Check
                Header Auth                ↓
                                    [PostgreSQL] + [Redis Cache]
                                    ProxySession tracking
```

**Two Token Types:**
1. **JWT Tokens** - For API authentication (register, login, purchase tokens)
2. **Access Tokens** - For proxy access to Zenzefi server (64-char random strings)

**Authentication Method:**
- **X-Access-Token Header** - For all proxy requests to Zenzefi server
- **X-Device-ID Header** - Device identifier for "1 token = 1 device" enforcement
- **JWT Authentication** - For API endpoints (`Authorization: Bearer token`)

**Device Conflict Detection (v0.5.0+):**
- Each access token can only be used from one device at a time
- Desktop Client sends hardware-based device_id (20-char hash)
- Backend tracks active sessions per token with device_id
- Attempting to use token from different device → 409 Conflict
- Session timeout: 5 minutes of inactivity (auto-cleanup every 2 minutes)

### Layer Architecture

```
app/
├── api/v1/          # HTTP endpoints (auth, tokens, users, currency, webhooks, proxy)
├── services/        # Business logic (auth, token, currency, payment, proxy, content rewriting, health)
├── models/          # SQLAlchemy ORM (User, AccessToken, Transaction)
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
- HTTP proxying to Zenzefi server (simplified, no WebSocket support)
- Direct pass-through of requests and responses
- CORS headers for API compatibility

**HealthCheckService** (`app/services/health_service.py`):
- Checks PostgreSQL, Redis, and Zenzefi server
- Overall status: healthy (all up), degraded (Zenzefi down), unhealthy (DB/Redis down)
- Results cached in Redis (TTL: 120 seconds)
- Background scheduler runs every 50 seconds

**CurrencyService** (`app/services/currency_service.py`):
- Manages ZNC (Zenzefi Credits) currency balance
- Operations: get_balance, credit_balance, get_transactions
- Atomic balance updates with row-level locking
- Transaction history with pagination and filtering

**PaymentService** (`app/services/payment_service.py`):
- MockPaymentProvider for development/testing
- Simulates payment gateway (YooKassa/Stripe in production)
- Operations: create_payment, simulate_payment_success, handle_webhook
- Conversion rate: 1 ZNC = 10 RUB (configurable)

### Database Models

**User** (`app/models/user.py`):
- Fields: id (UUID), email, username, hashed_password, full_name, is_active, is_superuser, currency_balance (Decimal)
- Relationships: tokens (one-to-many with AccessToken, cascade delete), transactions (one-to-many with Transaction, cascade delete)
- currency_balance: Decimal(10, 2), default 0.00, indexed (added in Phase 2)

**AccessToken** (`app/models/token.py`):
- Fields: id (UUID), user_id (FK), token (random string), duration_hours, scope, activated_at, is_active, revoked_at
- `scope` - Access scope: "full" (default) or "certificates_only" (added in v0.2.0)
- `expires_at` - **computed property** (activated_at + duration_hours), NOT stored in DB
- Valid durations: 1, 12, 24, 168 (week), 720 (month) hours
- Pricing: 1h=1 ZNC, 12h=10 ZNC, 24h=18 ZNC, 7d=100 ZNC, 30d=300 ZNC

**Transaction** (`app/models/transaction.py`) - *Added in Phase 2*:
- Fields: id (UUID), user_id (FK), amount (Decimal), transaction_type (enum), description, payment_id, created_at
- TransactionType enum: DEPOSIT (balance top-up), PURCHASE (token purchase), REFUND (token revoke refund)
- amount: positive for deposit/refund, negative for purchase
- payment_id: External payment gateway transaction ID (optional, for tracking)
- Relationship: user (many-to-one with User)

**ProxySession** (`app/models/proxy_session.py`) - *Added in Phase 3*:
- Fields: id (UUID), user_id (FK), token_id (FK), device_id (String 255), ip_address (INET), user_agent, started_at, last_activity, ended_at, bytes_transferred, request_count, is_active
- `device_id` - Hardware-based device identifier (20-char hash from Desktop Client)
- `is_active` - Boolean flag for active sessions (indexed)
- `last_activity` - Timestamp of last request (indexed for cleanup)
- Relationships: user (many-to-one), token (many-to-one), both with cascade delete
- **Session timeout:** 5 minutes of inactivity (auto-cleanup every 2 minutes)
- **Device conflict detection:** Only one device_id can use a token at a time

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
HEALTH_CHECK_INTERVAL=50
HEALTH_CHECK_TIMEOUT=10.0
```

## API Endpoints

### Authentication (`/api/v1/auth`)
- `POST /register` - Register new user
- `POST /login` - Login, returns JWT token

### Tokens (`/api/v1/tokens`)
- `POST /purchase` - Create access token (JWT auth required, costs ZNC)
- `GET /my-tokens?active_only=true` - List user's tokens
- `DELETE /{token_id}` - Revoke token with proportional refund (Phase 2)

### Currency (`/api/v1/currency`) - *Phase 2*
- `GET /balance` - Get current ZNC balance
- `GET /transactions` - Get transaction history (pagination, filtering by type)
- `POST /mock-purchase` - Mock balance purchase (testing only, bypasses payment gateway)
- `POST /purchase` - Create payment for ZNC purchase (mock payment gateway)
- `POST /admin/simulate-payment/{payment_id}` - Simulate successful payment (admin, testing)

### Webhooks (`/api/v1/webhooks`) - *Phase 2*
- `POST /payment` - Payment webhook handler (for payment gateway callbacks, HMAC verification in production)
- `GET /mock-payment` - Mock payment completion page (testing only)

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

### Health Check
- `GET /health` - Simple health check (~1ms from Redis cache)

### Proxy (`/api/v1/proxy`)
- `GET /status` - Check authentication status (requires `X-Access-Token` header)
- `ALL /{path:path}` - Proxy HTTP request to Zenzefi (requires `X-Access-Token` and `X-Device-ID` headers)

**Required Headers:**
- `X-Access-Token` - Access token for authentication
- `X-Device-ID` - Hardware-based device identifier (20-char hash from Desktop Client)

**Response Codes:**
- `200 OK` - Request proxied successfully
- `403 Forbidden` - Missing X-Device-ID header (upgrade Desktop Client)
- `401 Unauthorized` - Invalid/expired access token
- `409 Conflict` - Token already in use on different device (wait 5 minutes or stop other device)

**Example Usage:**
```bash
# Proxy request with device ID
curl -X GET "http://localhost:8000/api/v1/proxy/users/currentUser" \
  -H "X-Access-Token: your-access-token" \
  -H "X-Device-ID: a1b2c3d4e5f6g7h8i9j0"

# ❌ Missing device ID (403 Forbidden)
curl -X GET "http://localhost:8000/api/v1/proxy/users/currentUser" \
  -H "X-Access-Token: your-access-token"
# Error: Device identification required

# ❌ Token in use on another device (409 Conflict)
curl -X GET "http://localhost:8000/api/v1/proxy/users/currentUser" \
  -H "X-Access-Token: your-access-token" \
  -H "X-Device-ID: different-device-id"
# Error: Token already in use on device 'a1b2c3d4...'
```

**Full API docs:** http://localhost:8000/docs (when running)

## Critical Implementation Details

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

**Test organization:** 161 tests, 85%+ coverage
- `test_security.py` - Password hashing, JWT (14 tests)
- `test_auth_service.py` - Registration, login (10 tests)
- `test_token_service.py` - Token generation, caching, revoke (21 tests)
- `test_api_auth.py` - Auth API endpoints (13 tests)
- `test_api_tokens.py` - Token purchase API (16 tests)
- `test_currency_service.py` - Currency balance, transactions (10 tests) *Phase 2*
- `test_api_currency.py` - Currency API endpoints (13 tests) *Phase 2*
- `test_payment_service.py` - Mock payment gateway (5 tests) *Phase 2*
- `test_api_payment.py` - Payment API endpoints (8 tests) *Phase 2*
- `test_token_purchase.py` - Token purchase with balance (8 tests) *Phase 2*
- `test_permissions.py` - Token scope validation (8 tests)
- `test_token_scopes.py` - Scope integration tests (7 tests)
- `test_proxy_status.py` - Proxy status endpoint (4 tests)
- `test_health_service.py` - Health check service (15 tests)
- `test_proxy_session.py` - ProxySession tracking, device conflicts (13 tests) *Phase 3*
- `test_main.py` - Health checks, CORS, routing (9 tests)

**Phase 2 Tests Added:** 44 new tests (currency, payment, token purchase integration)
**Phase 3 Tests Added:** 13 new tests (ProxySession tracking, device conflict detection)

**See [TESTING.md](./docs/claude/TESTING.md) for detailed testing guide.**

## MCP Servers

MCP servers configured in `.mcp.json`:
- **postgres** - Direct SQL queries to zenzefi_dev database
- **docker** - Container status, logs, and operations
- **redis-tools** - Redis operations (`scripts/redis_mcp.py`)
- **zenzefi-api** - Programmatic access to backend API

## Notes for Claude Code

**Critical Information:**
- All tests must pass before considering work complete (148 tests as of Phase 2)
- Use real Redis and PostgreSQL for integration testing (configured in `conftest.py`)
- Token validation uses two-tier caching: Redis (fast) → PostgreSQL (fallback)
- Access tokens are random strings (not JWTs) - distinct from API JWT tokens
- `expires_at` is a computed property, NOT a database column
- JWT payload structure: `{"sub": user_id, "username": username}` (NOT email)
- **X-Access-Token header** - ONLY authentication method for proxy endpoints
- ProxyService is simplified: no WebSocket support, no HTML rewriting, no cookie handling
- Development primarily on Windows; commands may need adjustment for Linux/Mac
- **Timezone consistency (CRITICAL):**
  - Always use `datetime.now(timezone.utc)` for timezone-aware datetimes (NOT `datetime.utcnow()`)
  - When deserializing from Redis/ISO format: `datetime.fromisoformat()` may return timezone-naive datetime
  - **ALWAYS check timezone before comparison:** `if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)`
  - Tests JWT: use `datetime.utcfromtimestamp()` (not `fromtimestamp`)

**Phase 2 (Currency System) - Completed:**
- Currency balance stored as Decimal(10, 2) to avoid floating-point errors
- Token purchase charges balance atomically with `with_for_update()` row locking
- Token revoke calculates proportional refund: `refund = cost * (time_unused / total_duration)`
- MockPaymentProvider simulates payment gateway for development (replace with YooKassa/Stripe in production)
- Transaction history tracks all balance changes (DEPOSIT, PURCHASE, REFUND)
- Pricing: 1h=1 ZNC, 12h=10 ZNC, 24h=18 ZNC, 7d=100 ZNC, 30d=300 ZNC

**Phase 3 (Device Conflict Detection) - Completed:**
- **X-Device-ID header required** for all proxy requests (Desktop Client sends hardware fingerprint)
- ProxySession tracks active sessions with device_id (composite index on token_id, device_id, is_active)
- **1 token = 1 device policy:** Using token from different device → 409 Conflict error
- **Session timeout:** 5 minutes of inactivity (auto-cleanup every 2 minutes via APScheduler)
- **Device ID format:** 20-char SHA256 hash of hardware characteristics (stable across restarts)
- **Security:** Proxy requests without X-Device-ID → 403 Forbidden (Desktop Client upgrade required)
- **Session reuse:** Same device can reconnect after timeout (device_id matches)
- **IP changes allowed:** Same device can switch IPs (VPN, Wi-Fi) without conflict

**When writing code:**
- Follow existing patterns in codebase
- Add tests for new features (real services, no mocks)
- Update migrations for database changes
- Check DEVELOPMENT.md for command examples
- Check TROUBLESHOOTING.md if issues arise
