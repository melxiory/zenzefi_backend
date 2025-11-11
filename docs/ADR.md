# Architecture Decision Records (ADR)

> Документация ключевых архитектурных решений проекта Zenzefi Backend

**Версия:** v0.3.0-beta
**Последнее обновление:** 2025-11-11

---

## Содержание

1. [ADR-001: Computed expires_at Property](#adr-001-computed-expires_at-property)
2. [ADR-002: Lazy Token Activation](#adr-002-lazy-token-activation)
3. [ADR-003: Scope-Based Access Control](#adr-003-scope-based-access-control)
4. [ADR-004: Simplified HTTP-Only Proxy](#adr-004-simplified-http-only-proxy)
5. [ADR-005: Two-Tier Token Validation](#adr-005-two-tier-token-validation)
6. [ADR-006: Timezone-Aware Datetimes Everywhere](#adr-006-timezone-aware-datetimes-everywhere)
7. [ADR-007: X-Access-Token Header Authentication](#adr-007-x-access-token-header-authentication)
8. [ADR-008: Real Services in Integration Tests](#adr-008-real-services-in-integration-tests)

---

## ADR-001: Computed expires_at Property

**Дата:** 2025-10-20
**Статус:** ✅ Принято
**Контекст:** v0.2.0

### Проблема

Изначально планировалось хранить `expires_at` как отдельную колонку в таблице `access_tokens`. Это приводило к:
- **Data duplication:** `expires_at` зависит от `activated_at` и `duration_hours`
- **Sync issues:** При изменении `activated_at` нужно обновлять `expires_at`
- **Timezone confusion:** Смешивание timezone-aware и naive datetime

### Решение

Реализовать `expires_at` как `@property` в модели `AccessToken`:

```python
@property
def expires_at(self) -> datetime | None:
    if not self.activated_at:
        return None

    # Ensure timezone-aware
    activated = self.activated_at
    if activated.tzinfo is None:
        activated = activated.replace(tzinfo=timezone.utc)

    return activated + timedelta(hours=self.duration_hours)
```

### Consequences

**Плюсы:**
- ✅ Устраняет data duplication
- ✅ Всегда синхронизировано с `activated_at` и `duration_hours`
- ✅ Timezone-aware по умолчанию
- ✅ Упрощает логику обновления

**Минусы:**
- ⚠️ Немного медленнее (~0.01ms overhead)
- ⚠️ Нельзя использовать в SQL WHERE clause (но можно фильтровать через Python)

**Миграция:**
```bash
# Удалить expires_at column из БД
poetry run alembic revision --autogenerate -m "Remove expires_at column"
```

---

## ADR-002: Lazy Token Activation

**Дата:** 2025-10-20
**Статус:** ✅ Принято
**Контекст:** v0.2.0

### Проблема

Когда начинать отсчет времени токена:
1. **При покупке:** Пользователь теряет время, если не использует токен сразу
2. **При первом использовании:** Гибко, но требует дополнительной логики

### Решение

Отложенная активация (lazy activation):
- `activated_at = NULL` при создании токена
- `activated_at = datetime.now(timezone.utc)` при первом вызове `validate_token()`
- `expires_at` вычисляется от `activated_at`

```python
def validate_token(token: str, db: Session) -> tuple[bool, dict | None]:
    db_token = db.query(AccessToken).filter(...).first()

    if db_token:
        # Activate on first use
        if not db_token.activated_at:
            db_token.activated_at = datetime.now(timezone.utc)
            db.commit()

        return True, token_data

    return False, None
```

### Consequences

**Плюсы:**
- ✅ Гибкость: можно купить токен "про запас"
- ✅ Честная монетизация: платишь за реальное время использования
- ✅ Удобство: токен активируется автоматически при первом использовании

**Минусы:**
- ⚠️ Нужно различать два статуса: "ready" (не активирован) и "active" (активирован)
- ⚠️ Добавлен метод `check_token_status()` для read-only проверки

**Примеры использования:**
```python
# Покупка токена
token = TokenService.generate_access_token(user_id, 24)
# activated_at = None, expires_at = None

# Через 3 дня первое использование
valid, data = TokenService.validate_token(token.token, db)
# activated_at = now, expires_at = now + 24h
```

---

## ADR-003: Scope-Based Access Control

**Дата:** 2025-10-25
**Статус:** ✅ Принято
**Контекст:** v0.2.0

### Проблема

DTS Monaco требует ограниченного доступа только к `/certificates/*` endpoints. Как реализовать детальный контроль доступа на уровне путей?

### Решение

Regex-based path matching с scope permissions:

```python
# app/core/permissions.py
SCOPE_PERMISSIONS = {
    "full": [".*"],  # All paths
    "certificates_only": [
        r"^certificates/filter",
        r"^certificates/details/[^/]+",
        r"^certificates/export/[^/]+",
        r"^certificates/activeForTesting/.*",
        r"^certificates/update/.*",
        r"^certificates/checkSystemIntegrity.*",
        r"^configurations/certificatesColumn.*"
    ]
}

def validate_path_access(path: str, scope: str) -> tuple[bool, str | None]:
    patterns = SCOPE_PERMISSIONS.get(scope, [])
    for pattern in patterns:
        if re.match(pattern, path):
            return True, None
    return False, f"Access denied for path: {path} (scope: {scope})"
```

**Integration:**
- `AccessToken.scope` - DB column (migration)
- `TokenCreate` schema - scope validation
- Proxy endpoint - 403 Forbidden при нарушении
- Redis cache - scope хранится

### Consequences

**Плюсы:**
- ✅ Безопасность: детальный контроль на уровне путей
- ✅ Гибкость: легко добавлять новые scopes
- ✅ Производительность: regex ~0.01ms
- ✅ DTS Monaco: certificates_only scope идеален

**Минусы:**
- ⚠️ Вручную добавлять patterns при новых endpoints
- ⚠️ Regex может быть сложным (требует документации)

**Примеры:**
```python
# Full access token
POST /api/v1/tokens/purchase
{"duration_hours": 24, "scope": "full"}

# Certificates-only token
POST /api/v1/tokens/purchase
{"duration_hours": 24, "scope": "certificates_only"}

# ✅ Allowed
GET /api/v1/proxy/certificates/filter
X-Access-Token: {certificates_only_token}

# ❌ Blocked (403 Forbidden)
GET /api/v1/proxy/users/currentUser
X-Access-Token: {certificates_only_token}
```

---

## ADR-004: Simplified HTTP-Only Proxy

**Дата:** 2025-11-01
**Статус:** ✅ Принято
**Контекст:** v0.3.0

### Проблема

Исходный план предполагал:
- WebSocket support
- Cookie authentication + X-Access-Token hybrid
- ContentRewriter для HTML/JS
- CacheManager
- Session management в Redis

**Реальность:** DTS Monaco - простой HTTP API, WebSocket не нужен. ContentRewriter избыточен.

### Решение

Упрощённый HTTP proxy:
- ✅ Только HTTP methods (GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD)
- ✅ Только X-Access-Token header authentication
- ✅ Direct pass-through без content modification
- ✅ Desktop Client автоматически добавляет X-Access-Token

```python
# app/services/proxy_service.py (упрощённый)
async def proxy_request(request: Request, path: str, user_id: str, token_id: str):
    target_url = f"{settings.ZENZEFI_TARGET_URL}/{path}"

    # Forward headers (exclude Host, X-Access-Token)
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ['host', 'x-access-token']}

    # Add forwarding headers
    headers['X-Forwarded-For'] = request.client.host
    headers['X-User-Id'] = user_id

    # Proxy request
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=await request.body()
        )

    return Response(content=response.content, status_code=response.status_code)
```

### Consequences

**Плюсы:**
- ✅ Простота: меньше кода, легче поддерживать
- ✅ Безопасность: меньше поверхности для атак
- ✅ Производительность: нет overhead на content rewriting
- ✅ Разделение ответственности: Desktop Client = token forwarder, Backend = validator

**Минусы:**
- ⚠️ Если понадобится WebSocket - придется добавлять отдельно
- ⚠️ Если понадобится content rewriting - переделка архитектуры

**Удалено из кодовой базы:**
- `ContentRewriter` class
- Cookie handling logic
- WebSocket support
- Cache Manager

---

## ADR-005: Two-Tier Token Validation

**Дата:** 2025-10-22
**Статус:** ✅ Принято
**Контекст:** v0.2.0

### Проблема

Валидация токена в PostgreSQL каждый раз (~10ms) может стать узким местом при высокой нагрузке (1000 req/sec).

### Решение

Двухуровневое кеширование:

```python
def validate_token(token: str, db: Session) -> tuple[bool, dict | None]:
    # 1. Fast path: Redis cache (~1ms)
    redis_data = TokenService._get_cached_token(token)
    if redis_data:
        expires_at = datetime.fromisoformat(redis_data['expires_at'])
        if expires_at > datetime.now(timezone.utc):
            return True, redis_data
        else:
            TokenService._remove_cached_token(token)

    # 2. Slow path: PostgreSQL (~10ms)
    db_token = db.query(AccessToken).filter(...).first()
    if db_token:
        TokenService._cache_token(db_token)
        return True, token_data

    return False, None
```

**Redis structure:**
```python
Key: "active_token:{sha256(token)}"
Value: {
    "user_id": "uuid",
    "token_id": "uuid",
    "expires_at": "ISO",
    "duration_hours": int,
    "scope": "full|certificates_only"
}
TTL: До истечения токена
```

### Consequences

**Плюсы:**
- ✅ Производительность: 90%+ requests из Redis (~1ms)
- ✅ Надёжность: PostgreSQL source of truth при cache miss
- ✅ Актуальность: TTL = срок токена
- ✅ Масштабируемость: Redis легко scale horizontally

**Минусы:**
- ⚠️ Кешируются только **активированные** токены (activated_at не NULL)
- ⚠️ При revoke нужно явно удалять из Redis
- ⚠️ Небольшой delay при первой валидации (~10ms)

**Метрики:**
- Cache hit rate: >90%
- Latency p50: ~1ms (Redis)
- Latency p99: ~10ms (PostgreSQL fallback)

---

## ADR-006: Timezone-Aware Datetimes Everywhere

**Дата:** 2025-10-18
**Статус:** ✅ Принято
**Контекст:** v0.1.0

### Проблема

Timezone-naive datetime приводил к багам:
```python
# Bug
now = datetime.utcnow()  # naive
expires_at = datetime.fromisoformat(redis_data['expires_at'])  # aware
if expires_at > now:  # TypeError: can't compare offset-naive and offset-aware
    ...
```

### Решение

Всегда использовать timezone-aware datetimes:

```python
# ✅ Правильно
from datetime import datetime, timezone
now = datetime.now(timezone.utc)

# ❌ Неправильно
now = datetime.utcnow()  # Returns naive datetime
```

**Правила:**
1. Все `datetime.now()` → `datetime.now(timezone.utc)`
2. Проверять timezone перед сравнением:
   ```python
   if dt.tzinfo is None:
       dt = dt.replace(tzinfo=timezone.utc)
   ```
3. В тестах JWT: использовать `datetime.utcfromtimestamp()` (не `fromtimestamp`)

### Consequences

**Плюсы:**
- ✅ Корректность: устраняет ошибки сравнения naive vs aware
- ✅ Совместимость: PostgreSQL TIMESTAMP WITH TIME ZONE
- ✅ Тесты: все 104 теста проходят без timezone issues

**Минусы:**
- ⚠️ Нужно явно проверять timezone при десериализации из Redis/ISO

**Фикс в кодовой базе:**
```python
# Все файлы
datetime.utcnow() → datetime.now(timezone.utc)

# AccessToken.expires_at property
if activated.tzinfo is None:
    activated = activated.replace(tzinfo=timezone.utc)

# TokenService validation
if expires_at.tzinfo is None:
    expires_at = expires_at.replace(tzinfo=timezone.utc)
```

---

## ADR-007: X-Access-Token Header Authentication

**Дата:** 2025-11-01
**Статус:** ✅ Принято
**Контекст:** v0.3.0

### Проблема

Изначально планировалось использовать Cookie + X-Access-Token hybrid authentication. Однако:
- Cookie требует session management
- Cookie подвержен CSRF attacks
- Desktop Client может легко добавлять headers

### Решение

Использовать **только X-Access-Token header** для proxy authentication:

```python
# app/api/v1/proxy.py
@router.api_route("/{path:path}", methods=["GET", "POST", ...])
async def proxy_to_zenzefi(
    path: str,
    request: Request,
    x_access_token: str = Header(..., alias="X-Access-Token"),
    db: Session = Depends(get_db)
):
    # Validate token
    valid, token_data = TokenService.validate_token(x_access_token, db)

    if not valid:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    # Proxy request
    return await ProxyService.proxy_request(request, path, token_data['user_id'], token_data['token_id'])
```

**Desktop Client:**
```python
# zenzefi_client/core/proxy.py
async def handle_http(self, request):
    # Автоматически добавляет header
    request.headers["X-Access-Token"] = self.access_token

    # Forward to backend
    response = await httpx.request(
        method=request.method,
        url=f"http://localhost:8000/api/v1/proxy/{path}",
        headers=request.headers,
        content=request.body
    )
    return response
```

### Consequences

**Плюсы:**
- ✅ Простота: нет session management
- ✅ Безопасность: нет CSRF, нет Cookie hijacking
- ✅ Stateless: backend полностью stateless
- ✅ Desktop Client: легко добавлять headers

**Минусы:**
- ⚠️ DTS Monaco должен идти через Desktop Client (не напрямую к Backend)
- ⚠️ Token нужно хранить безопасно в Desktop Client (Fernet encryption)

**Удалено:**
- Cookie authentication logic
- Session management в Redis
- CSRF protection middleware

---

## ADR-008: Real Services in Integration Tests

**Дата:** 2025-10-15
**Статус:** ✅ Принято
**Контекст:** v0.1.0

### Проблема

Использовать моки (mocks) для PostgreSQL и Redis в тестах или реальные сервисы?

**Минусы моков:**
- Не тестируют реальное поведение БД
- Не ловят проблемы с SQL queries
- Не тестируют Redis operations
- Ложная уверенность в качестве

### Решение

Использовать **реальные PostgreSQL и Redis** в интеграционных тестах:

```python
# tests/conftest.py
@pytest.fixture(scope="session")
def db_engine():
    """Create test database engine"""
    engine = create_engine(
        "postgresql://zenzefi:password@localhost:5432/zenzefi_test"
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Cleanup
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(db_engine):
    """Create clean database session for each test"""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    # Rollback after test
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="session")
def redis_client():
    """Redis client for tests"""
    client = redis.Redis(host="localhost", port=6379, db=1)

    yield client

    # Cleanup
    client.flushdb()
```

**Setup:**
```bash
# Start test services
docker-compose -f docker-compose.dev.yml up -d postgres redis

# Run tests
poetry run pytest tests/ -v
```

### Consequences

**Плюсы:**
- ✅ Реальное поведение: тестируем actual SQL queries
- ✅ Ловим баги: типы данных, constraints, indexes
- ✅ Уверенность: если тесты проходят, БД работает
- ✅ Redis operations: тестируем caching, TTL

**Минусы:**
- ⚠️ Медленнее: ~2-3 секунды setup
- ⚠️ Требует Docker: PostgreSQL и Redis должны быть запущены
- ⚠️ Cleanup: нужно очищать тестовую БД после тестов

**Метрики:**
- 104 теста
- 85%+ code coverage
- ~15 секунд execution time
- 100% прохождение

---

## Итоговая таблица ADR

| ADR | Название | Статус | Версия | Impact |
|-----|----------|--------|--------|--------|
| ADR-001 | Computed expires_at Property | ✅ Принято | v0.2.0 | High |
| ADR-002 | Lazy Token Activation | ✅ Принято | v0.2.0 | High |
| ADR-003 | Scope-Based Access Control | ✅ Принято | v0.2.0 | High |
| ADR-004 | Simplified HTTP-Only Proxy | ✅ Принято | v0.3.0 | Critical |
| ADR-005 | Two-Tier Token Validation | ✅ Принято | v0.2.0 | High |
| ADR-006 | Timezone-Aware Datetimes | ✅ Принято | v0.1.0 | Critical |
| ADR-007 | X-Access-Token Header Auth | ✅ Принято | v0.3.0 | Critical |
| ADR-008 | Real Services in Tests | ✅ Принято | v0.1.0 | High |

**Impact levels:**
- **Critical:** Fundamental architectural decision
- **High:** Significant impact on design/implementation
- **Medium:** Important but localized change
- **Low:** Minor improvement

---

## Процесс добавления нового ADR

1. **Создать новый раздел:** `## ADR-XXX: Название`
2. **Заполнить поля:**
   - Дата
   - Статус (Предложено / Обсуждается / Принято / Отклонено / Устарело)
   - Контекст (версия)
   - Проблема
   - Решение
   - Consequences (плюсы/минусы)
3. **Обновить таблицу:** Добавить в итоговую таблицу
4. **Code review:** Обсудить с командой перед принятием
5. **Implementation:** Реализовать после принятия

---

**Дополнительные ресурсы:**
- [ADR GitHub Template](https://github.com/joelparkerhenderson/architecture-decision-record)
- [Thoughtworks Technology Radar](https://www.thoughtworks.com/radar)
- [Martin Fowler on ADR](https://martinfowler.com/articles/architectural-decisions.html)
