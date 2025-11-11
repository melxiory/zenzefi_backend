# Этап 1: MVP (Minimum Viable Product)

**Статус:** ✅ **ЗАВЕРШЁН**
**Версия:** v0.3.0-beta
**Время реализации:** 2-3 недели
**Тесты:** 104/104 (100% прохождение, 85%+ покрытие)

---

## Цель

Создать минимальную работающую систему для тестирования концепции: аутентификация, генерация токенов доступа и HTTP проксирование к Zenzefi серверу.

---

## Базовые задачи (завершены)

### ✅ Инициализация проекта

**Что реализовано:**
- Создана структура папок (app/, tests/, scripts/, alembic/)
- Настроен Poetry (pyproject.toml v0.3.0-beta, Python 3.13)
- Docker Compose для dev (PostgreSQL 15 + Redis 7)
- 4 MCP servers (.mcp.json): backend API, Redis, Docker, Postgres

**Файлы:**
- `pyproject.toml` - dependencies и project metadata
- `docker-compose.dev.yml` - development environment
- `.mcp.json` - MCP server configurations

---

### ✅ База данных

**Модели:**

#### User Model (`app/models/user.py`)
```python
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.now(timezone.utc))

    # Relationships
    tokens = relationship("AccessToken", back_populates="user", cascade="all, delete-orphan")
```

#### AccessToken Model (`app/models/token.py`)
```python
class AccessToken(Base):
    __tablename__ = "access_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)  # 64-char random string
    duration_hours = Column(Integer, nullable=False)  # 1, 12, 24, 168, 720
    scope = Column(String, default="full", nullable=False)  # "full" | "certificates_only"
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    activated_at = Column(DateTime(timezone=True), nullable=True)  # Lazy activation
    is_active = Column(Boolean, default=True, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="tokens")

    @property
    def expires_at(self) -> datetime | None:
        """Computed property: activated_at + duration_hours"""
        if not self.activated_at:
            return None

        activated = self.activated_at
        if activated.tzinfo is None:
            activated = activated.replace(tzinfo=timezone.utc)

        return activated + timedelta(hours=self.duration_hours)
```

**Миграции Alembic:**
```bash
# 4 миграции созданы
0cbf73fcb14e - Initial schema (User + AccessToken)
f909ad8c76ed - Make expires_at nullable (lazy activation)
b3f64e56a42f - Remove expires_at column (computed property)
f09519d56544 - Add scope field (v0.2.0)
```

---

### ✅ Аутентификация

**JWT Tokens:**
- Algorithm: HS256
- Expires: 60 минут
- Payload: `{"sub": user_id, "username": username}` (НЕ email!)

**API Endpoints:**

#### POST /api/v1/auth/register
```python
# Request
{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "SecurePass123!",
  "full_name": "John Doe"  # optional
}

# Response 201
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "is_active": true,
  "created_at": "2025-10-15T10:00:00Z"
}
```

#### POST /api/v1/auth/login
```python
# Request
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}

# Response 200
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### GET /api/v1/users/me
```python
# Headers
Authorization: Bearer {jwt_token}

# Response 200
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "is_active": true,
  "created_at": "2025-10-15T10:00:00Z"
}
```

**Реализация:**
- `app/services/auth_service.py` - Registration, login logic
- `app/core/security.py` - JWT creation, bcrypt hashing
- `app/api/deps.py` - get_current_user, get_current_active_user dependencies

---

### ✅ Система токенов

**TokenService (`app/services/token_service.py`):**

```python
def generate_access_token(user_id: UUID, duration_hours: int, scope: str, db: Session) -> AccessToken:
    """Generate random access token (64-char URL-safe string)"""
    token_string = secrets.token_urlsafe(48)  # 48 bytes = 64 chars

    db_token = AccessToken(
        user_id=user_id,
        token=token_string,
        duration_hours=duration_hours,
        scope=scope,
        created_at=datetime.now(timezone.utc),
        is_active=True
        # activated_at = None (lazy activation)
    )

    db.add(db_token)
    db.commit()

    return db_token

def validate_token(token: str, db: Session) -> tuple[bool, dict | None]:
    """Two-tier validation: Redis cache (~1ms) → PostgreSQL (~10ms)"""
    # 1. Fast path: Redis cache
    redis_data = TokenService._get_cached_token(token)
    if redis_data:
        expires_at = datetime.fromisoformat(redis_data['expires_at'])
        if expires_at > datetime.now(timezone.utc):
            return True, redis_data

    # 2. Slow path: PostgreSQL
    db_token = db.query(AccessToken).filter(
        AccessToken.token == token,
        AccessToken.is_active == True,
        AccessToken.revoked_at == None
    ).first()

    if db_token and db_token.expires_at and db_token.expires_at > datetime.now(timezone.utc):
        # Activate on first use
        if not db_token.activated_at:
            db_token.activated_at = datetime.now(timezone.utc)
            db.commit()

        # Cache for future requests
        TokenService._cache_token(db_token)

        token_data = {
            "user_id": str(db_token.user_id),
            "token_id": str(db_token.id),
            "expires_at": db_token.expires_at.isoformat(),
            "duration_hours": db_token.duration_hours,
            "scope": db_token.scope
        }

        return True, token_data

    return False, None
```

**API Endpoints:**

#### POST /api/v1/tokens/purchase
```python
# Headers
Authorization: Bearer {jwt_token}

# Request
{
  "duration_hours": 24,  # 1, 12, 24, 168, 720
  "scope": "full"         # "full" | "certificates_only"
}

# Response 201 (MVP: бесплатно)
{
  "token_id": "uuid",
  "token": "abc123def456...",
  "duration_hours": 24,
  "scope": "full",
  "created_at": "2025-10-15T11:00:00Z",
  "is_active": true,
  "activated_at": null,
  "expires_at": null  # Активируется при первом использовании
}
```

#### GET /api/v1/tokens/my-tokens
```python
# Headers
Authorization: Bearer {jwt_token}

# Query params
?active_only=true

# Response 200
{
  "items": [
    {
      "token_id": "uuid",
      "token": "abc123def456...",
      "duration_hours": 24,
      "scope": "full",
      "created_at": "2025-10-15T11:00:00Z",
      "activated_at": "2025-10-15T11:05:00Z",
      "expires_at": "2025-10-16T11:05:00Z",
      "is_active": true
    }
  ]
}
```

**Redis Cache Structure:**
```python
Key: "active_token:{sha256(token)}"
Value: {
    "user_id": "uuid",
    "token_id": "uuid",
    "expires_at": "ISO timestamp",
    "duration_hours": int,
    "scope": "full|certificates_only"
}
TTL: До истечения токена
```

---

### ✅ Проксирование

**ProxyService (`app/services/proxy_service.py`):**

```python
async def proxy_request(request: Request, path: str, user_id: str, token_id: str) -> Response:
    """Simple HTTP proxy to Zenzefi server"""
    target_url = f"{settings.ZENZEFI_TARGET_URL}/{path}"

    # Copy headers (exclude Host, X-Access-Token)
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ['host', 'x-access-token', 'content-length']}

    # Add forwarding headers
    headers.update({
        'X-Forwarded-For': request.client.host,
        'X-Forwarded-Proto': 'https',
        'X-User-Id': user_id,
        'X-Token-Id': token_id
    })

    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=await request.body(),
            params=request.query_params
        )

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers)
    )
```

**API Endpoints:**

#### GET /api/v1/proxy/status
```python
# Headers
X-Access-Token: abc123def456...

# Response 200
{
  "connected": true,
  "user_id": "uuid",
  "token_id": "uuid",
  "is_activated": true,
  "expires_at": "2025-10-16T11:00:00Z",
  "time_remaining_seconds": 82800,
  "status": "active"  # "ready" | "active"
}
```

#### ALL /api/v1/proxy/{path:path}
```python
# Headers
X-Access-Token: abc123def456...

# Supported methods
GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD

# Scope validation
# "full" scope: все paths разрешены
# "certificates_only" scope: только /certificates/* paths

# Response
# Proxied response from Zenzefi server
```

---

## 🆕 Реализовано СВЕРХ плана

### 1. Scope-Based Access Control (v0.2.0)

**Реализация:**
- `app/core/permissions.py` - Regex-based path matching
- `AccessToken.scope` - Database column (migration f09519d56544)
- Token validation с scope проверкой

**Scopes:**
- `"full"` - доступ ко всем endpoints
- `"certificates_only"` - только `/certificates/*` и `/configurations/certificatesColumn*`

**Allowed paths для certificates_only:**
```python
SCOPE_PERMISSIONS = {
    "certificates_only": [
        r"^certificates/filter",
        r"^certificates/details/[^/]+",
        r"^certificates/export/[^/]+",
        r"^certificates/import.*",
        r"^certificates/remove",
        r"^certificates/restore",
        r"^certificates/activeForTesting.*",
        r"^certificates/update.*",
        r"^certificates/checkSystemIntegrity.*",
        r"^configurations/certificatesColumn.*"
    ]
}
```

**Тесты:** 15/15 (test_permissions.py + test_token_scopes.py)

---

### 2. Health Check System

**HealthCheckService (`app/services/health_service.py`):**

```python
async def check_database() -> tuple[bool, float]:
    """Check PostgreSQL connection"""
    # Execute simple query, measure latency

async def check_redis() -> tuple[bool, float]:
    """Check Redis connection"""
    # Ping Redis, measure latency

async def check_zenzefi() -> tuple[bool, float]:
    """Check Zenzefi server availability"""
    # HTTP GET to target server

def determine_overall_status(checks: dict) -> str:
    """Determine system status"""
    if not checks['database'] or not checks['redis']:
        return "unhealthy"
    elif not checks['zenzefi']:
        return "degraded"
    return "healthy"

async def perform_health_check() -> dict:
    """Run all checks, save to Redis cache (TTL: 120s)"""
    # Returns: status, timestamp, checks, latencies
```

**Background Scheduler (`app/core/health_scheduler.py`):**
```python
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    scheduler.add_job(
        perform_health_check_task,
        "interval",
        seconds=50  # Run every 50 seconds
    )
    scheduler.start()
```

**API Endpoints:**

#### GET /health
```python
# Fast check from Redis cache (~1ms)
{
  "status": "healthy",
  "timestamp": "2025-10-15T12:00:00Z"
}
```

#### GET /health/detailed
```python
# Detailed health with latency measurements
{
  "status": "healthy",
  "timestamp": "2025-10-15T12:00:00Z",
  "checks": {
    "database": true,
    "redis": true,
    "zenzefi": true
  },
  "latencies": {
    "database_ms": 5.2,
    "redis_ms": 0.8,
    "zenzefi_ms": 150.3
  }
}
```

**Тесты:** 15/15 (test_health_service.py)

---

### 3. Timezone-Aware Datetimes

**Правила:**
```python
# ✅ Правильно
from datetime import datetime, timezone
now = datetime.now(timezone.utc)

# ❌ Неправильно
now = datetime.utcnow()  # Returns naive datetime
```

**Проверки timezone:**
```python
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
```

**Применение:**
- Все операции с datetime используют `datetime.now(timezone.utc)`
- `AccessToken.expires_at` @property гарантирует timezone-aware
- Redis serialization в ISO format с timezone
- Тесты JWT используют `datetime.utcfromtimestamp()`

---

### 4. Comprehensive Testing

**Статистика:**
```
104 теста (100% прохождение)
85%+ покрытие кода
Тестовая БД: zenzefi_test (PostgreSQL)
Redis: database 1 (отдельно от dev)
```

**Test файлы:**
- `test_security.py` - 14 тестов (JWT, bcrypt)
- `test_auth_service.py` - 10 тестов (registration, login)
- `test_token_service.py` - 14 тестов (generation, validation, caching)
- `test_api_auth.py` - 13 тестов (auth endpoints)
- `test_api_tokens.py` - 16 тестов (token endpoints)
- `test_permissions.py` - 8 тестов (scope validation)
- `test_token_scopes.py` - 7 тестов (scope integration)
- `test_proxy_status.py` - 4 теста (proxy status endpoint)
- `test_health_service.py` - 15 тестов (health checks)
- `test_main.py` - 9 тестов (routing, CORS, health, docs)

**Философия:**
- Реальные PostgreSQL и Redis (БЕЗ моков!)
- Integration tests, не unit tests
- Каждый тест использует clean database session (rollback после теста)

**Запуск:**
```bash
# All tests
poetry run pytest tests/ -v

# Specific file
poetry run pytest tests/test_api_auth.py -v

# With coverage
poetry run pytest tests/ -v --cov=app --cov-report=html
```

---

### 5. Utility Scripts & Infrastructure

**Scripts (12+ файлов):**
```bash
scripts/
├── init_db.py              # Initialize database
├── check_database.py       # Check DB status
├── reset_database.py       # Drop and recreate DB
├── clear_database.py       # Clear all data
├── create_test_database.py # Setup test DB
├── create_superuser.py     # Create admin user
├── test_create_token.py    # Test token generation
├── deploy_docker.sh        # Docker Compose deploy
├── deploy.sh               # Production deploy
├── cleanup_and_redeploy.sh # Full redeploy
└── fix_ssl.sh              # SSL certificates fix
```

**MCP Servers (4 configured):**
```json
{
  "zenzefi-backend": "FastMCP server for backend API",
  "redis-tools": "Redis operations (get, set, keys, flushdb)",
  "docker": "Docker container management",
  "postgres": "PostgreSQL query execution"
}
```

**Документация:**
- `CLAUDE.md` - Backend-specific guide
- `docs/claude/DEVELOPMENT.md` - All commands
- `docs/claude/TESTING.md` - Testing patterns
- `docs/claude/TROUBLESHOOTING.md` - Common issues

---

### 6. Архитектурные упрощения (v0.3.0)

**Удалено из плана:**
- ❌ WebSocket support (не нужен для DTS Monaco)
- ❌ Cookie authentication (только X-Access-Token header)
- ❌ ContentRewriter (прямое проксирование HTTP)
- ❌ CacheManager (упрощённый подход)
- ❌ Session management в Redis (stateless backend)

**Результат:**
- ✅ Простота: меньше кода, легче поддерживать
- ✅ Безопасность: меньше поверхности для атак
- ✅ Производительность: нет overhead на content rewriting
- ✅ Разделение: Desktop Client = token forwarder, Backend = validator

**См. также:** `docs/ADR.md` - ADR-004 (Simplified HTTP-Only Proxy)

---

## Итоговая статистика

**Время разработки:** 2-3 недели
**Строк кода:** ~5250 (app/ + tests/ + scripts/)
**Тесты:** 104 (85%+ покрытие)
**Миграции:** 4
**API Endpoints:** 9
**Модели:** 2 (User, AccessToken)
**Сервисы:** 4 (Auth, Token, Proxy, Health)

**Следующий этап:** [Этап 2 (Система валюты)](./PHASE_2_CURRENCY.md) - добавление монетизации

---

## Запуск development environment

```bash
# Start services
docker-compose -f docker-compose.dev.yml up -d

# Run migrations
poetry run alembic upgrade head

# Start development server
python run_dev.py
```

Backend running: http://localhost:8000
API Docs: http://localhost:8000/docs
Health Check: http://localhost:8000/health

---

**См. также:**
- [ADR.md](../ADR.md) - Architecture Decision Records
- [PHASE_2_CURRENCY.md](./PHASE_2_CURRENCY.md) - Следующий этап
- [DEVELOPMENT.md](../claude/DEVELOPMENT.md) - Development commands
