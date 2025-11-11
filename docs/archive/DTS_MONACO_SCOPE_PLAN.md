# План реализации: Ограничение доступа для DTS Monaco

## Обзор

**Цель:** Ограничить доступ токенов DTS Monaco только к certificate endpoints Zenzefi сервера, блокировав доступ к остальным частям системы.

**Метод:** Добавление поля `scope` в модель `AccessToken` с валидацией разрешенных путей на уровне proxy.

**Версия:** 1.0
**Дата:** 2025-01-10
**Статус:** Планирование

## Архитектурное решение

### Система Scopes

Два типа scope для токенов:

| Scope | Описание | Разрешенные пути | Использование |
|-------|----------|------------------|---------------|
| `full` | Полный доступ | Все пути (`*`) | Desktop Client, администраторы |
| `certificates_only` | Только сертификаты | `/certificates/*` | DTS Monaco |

### Принцип работы

```
[DTS Monaco]
    ↓ X-Access-Token: {token with scope=certificates_only}
[Backend Proxy]
    ↓ validate_path_access(path="/certificates/filter", scope="certificates_only")
    ↓ ✅ Allowed
[Zenzefi Server] /certificates/filter
```

```
[DTS Monaco]
    ↓ X-Access-Token: {token with scope=certificates_only}
[Backend Proxy]
    ↓ validate_path_access(path="/users/currentUser", scope="certificates_only")
    ↓ ❌ BLOCKED - 403 Forbidden
[Response] Access denied
```

## Найденные Certificate Endpoints

### Из анализа Zenzefi UI JavaScript

**Основные операции:**

```
GET  /certificates/filter                              # Список/поиск
GET  /certificates/details/{id}                        # Детали
GET  /certificates/export/{id}                         # Экспорт
POST /certificates/import/files                        # Импорт
DELETE /certificates/remove                            # Удаление
POST /certificates/restore                             # Восстановление
```

**Тестирование:**

```
GET  /certificates/activeForTesting                    # Активные для тестирования
POST /certificates/activeForTesting/activate/{id}     # Активировать
POST /certificates/activeForTesting/deactivate/{id}   # Деактивировать
GET  /certificates/activeForTesting/enhanced           # Enhanced info
GET  /certificates/activeForTesting/options/{id}      # Опции
GET  /certificates/activeForTesting/usecases/{id}     # Use cases
```

**Обновление и проверка:**

```
POST /certificates/update/{id}                         # Обновить
GET  /certificates/update/metrics                      # Метрики
POST /certificates/update/cancel                       # Отменить
GET  /certificates/checkSystemIntegrityReport          # Отчет
GET  /certificates/checkSystemIntegrityLog             # Лог
GET  /certificates/checkSystemIntegrityLogExistance    # Проверка существования
```

**Конфигурация (UI-related):**

```
GET  /configurations/certificatesColumnOrder           # Порядок столбцов
POST /configurations/certificatesColumnOrder
GET  /configurations/certificatesColumnVisibility      # Видимость столбцов
POST /configurations/certificatesColumnVisibility
```

### ⚠️ Требуется валидация

**Эти endpoint'ы найдены в JavaScript, но требуется:**

1. ✅ Перехватить реальные API запросы с Fiddler (см. `FIDDLER_SETUP.md`)
2. ✅ Подтвердить какие endpoint'ы реально используются DTS Monaco
3. ✅ Уточнить HTTP методы (GET/POST/DELETE)
4. ✅ Определить обязательные vs опциональные endpoint'ы

## Этапы реализации

### Этап 1: Database Migration

**Файл:** `alembic/versions/XXXXXX_add_token_scope.py`

**Действия:**
- Создать миграцию: `poetry run alembic revision --autogenerate -m "add token scope"`
- Добавить колонку `scope VARCHAR DEFAULT 'full' NOT NULL`
- Backward-compatible: существующие токены автоматически получат `scope='full'`

**SQL (для проверки):**

```sql
ALTER TABLE access_tokens
ADD COLUMN scope VARCHAR NOT NULL DEFAULT 'full';
```

**Тест миграции:**

```bash
# Upgrade
poetry run alembic upgrade head

# Проверка
poetry run python scripts/db_check.py

# Downgrade test
poetry run alembic downgrade -1
poetry run alembic upgrade head
```

---

### Этап 2: Обновление моделей

#### 2.1 Обновить AccessToken Model

**Файл:** `app/models/token.py`

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class AccessToken(Base):
    __tablename__ = "access_tokens"

    # Existing fields...
    id: Mapped[UUID]
    user_id: Mapped[UUID]
    token: Mapped[str]
    duration_hours: Mapped[int]
    # ... other existing fields ...

    # NEW FIELD
    scope: Mapped[str] = mapped_column(
        String,
        default="full",
        nullable=False,
        comment="Access scope: 'full' or 'certificates_only'"
    )
```

#### 2.2 Обновить Pydantic схемы

**Файл:** `app/schemas/token.py`

```python
from pydantic import BaseModel, Field, validator
from typing import Literal

class TokenCreate(BaseModel):
    """Схема для создания токена"""
    duration_hours: int = Field(..., ge=1, description="Duration in hours")
    scope: Literal["full", "certificates_only"] = Field(
        default="full",
        description="Access scope: 'full' for all paths, 'certificates_only' for certificates"
    )

    @validator('scope')
    def validate_scope(cls, v):
        allowed_scopes = ["full", "certificates_only"]
        if v not in allowed_scopes:
            raise ValueError(f"scope must be one of {allowed_scopes}")
        return v

class TokenInDB(BaseModel):
    """Схема токена из БД"""
    id: str
    user_id: str
    token: str
    duration_hours: int
    created_at: datetime
    activated_at: Optional[datetime]
    is_active: bool
    revoked_at: Optional[datetime]
    expires_at: Optional[datetime]
    scope: str  # NEW FIELD

    class Config:
        from_attributes = True
```

---

### Этап 3: Конфигурация разрешенных путей

**Файл:** `app/core/permissions.py` (новый файл)

```python
"""
Path-based access control for token scopes.

Этот модуль определяет разрешенные пути для каждого scope токена.
"""

import re
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

# Разрешенные пути для каждого scope
SCOPE_PERMISSIONS = {
    # Full scope - доступ ко всем путям
    "full": None,  # None = all paths allowed

    # Certificates only scope - только /certificates/*
    "certificates_only": [
        # Основные операции с сертификатами
        r"^certificates/filter",                              # GET - список/поиск
        r"^certificates/details/",                            # GET - детали {id}
        r"^certificates/export/",                             # GET/POST - экспорт {id}
        r"^certificates/import/",                             # POST - импорт
        r"^certificates/remove",                              # DELETE - удаление
        r"^certificates/restore",                             # POST - восстановление

        # Тестирование сертификатов
        r"^certificates/activeForTesting",                    # GET - список активных
        r"^certificates/activeForTesting/activate/",          # POST - активировать {id}
        r"^certificates/activeForTesting/deactivate/",        # POST - деактивировать {id}
        r"^certificates/activeForTesting/enhanced",           # GET - enhanced info
        r"^certificates/activeForTesting/options/",           # GET - опции {id}
        r"^certificates/activeForTesting/usecases/",          # GET - use cases {id}

        # Обновление и проверка целостности
        r"^certificates/update/",                             # POST - обновить {id}
        r"^certificates/update/cancel",                       # POST - отменить
        r"^certificates/update/metrics",                      # GET - метрики
        r"^certificates/checkSystemIntegrityReport",          # GET - отчет
        r"^certificates/checkSystemIntegrityLog",             # GET - лог
        r"^certificates/checkSystemIntegrityLogExistance",    # GET - проверка лога

        # Конфигурация UI (опционально, может понадобиться для DTS Monaco UI)
        r"^configurations/certificatesColumnOrder",           # GET/POST - порядок столбцов
        r"^configurations/certificatesColumnVisibility",      # GET/POST - видимость столбцов
    ]
}


def validate_path_access(path: str, scope: str) -> bool:
    """
    Проверяет разрешен ли путь для данного scope.

    Args:
        path: Путь запроса (без ведущего слеша), например "certificates/filter"
        scope: Scope токена ("full" или "certificates_only")

    Returns:
        True если доступ разрешен, False иначе

    Examples:
        >>> validate_path_access("certificates/filter", "certificates_only")
        True

        >>> validate_path_access("users/currentUser", "certificates_only")
        False

        >>> validate_path_access("system/version", "full")
        True
    """
    # Нормализация пути (удалить ведущий слеш если есть)
    path = path.lstrip("/")

    # Full scope - доступ ко всем путям
    if scope == "full":
        return True

    # Получаем разрешенные паттерны для scope
    allowed_patterns = SCOPE_PERMISSIONS.get(scope)

    # Если scope неизвестен - запретить доступ
    if allowed_patterns is None and scope != "full":
        logger.warning(f"Unknown scope: {scope}")
        return False

    # Если для scope есть список паттернов - проверяем совпадение
    if allowed_patterns:
        for pattern in allowed_patterns:
            if re.match(pattern, path):
                logger.debug(f"Path '{path}' matched pattern '{pattern}' for scope '{scope}'")
                return True

    logger.info(f"Path '{path}' not allowed for scope '{scope}'")
    return False


def get_allowed_paths(scope: str) -> Optional[List[str]]:
    """
    Возвращает список разрешенных regex паттернов для scope.

    Args:
        scope: Scope токена

    Returns:
        Список regex паттернов или None для full scope
    """
    return SCOPE_PERMISSIONS.get(scope)
```

**Тест файла:**

**Файл:** `tests/test_permissions.py` (новый)

```python
import pytest
from app.core.permissions import validate_path_access, get_allowed_paths


class TestValidatePathAccess:
    """Тесты валидации доступа к путям"""

    def test_full_scope_allows_all_paths(self):
        """Full scope разрешает все пути"""
        assert validate_path_access("certificates/filter", "full") is True
        assert validate_path_access("users/currentUser", "full") is True
        assert validate_path_access("system/version", "full") is True
        assert validate_path_access("any/random/path", "full") is True

    def test_certificates_scope_allows_certificate_paths(self):
        """Certificates_only scope разрешает /certificates/* пути"""
        assert validate_path_access("certificates/filter", "certificates_only") is True
        assert validate_path_access("certificates/details/123", "certificates_only") is True
        assert validate_path_access("certificates/export/456", "certificates_only") is True
        assert validate_path_access("certificates/import/files", "certificates_only") is True
        assert validate_path_access("certificates/update/789", "certificates_only") is True

    def test_certificates_scope_blocks_other_paths(self):
        """Certificates_only scope блокирует не-certificate пути"""
        assert validate_path_access("users/currentUser", "certificates_only") is False
        assert validate_path_access("system/version", "certificates_only") is False
        assert validate_path_access("logs/filter", "certificates_only") is False
        assert validate_path_access("zenzefi/ui/environment", "certificates_only") is False

    def test_path_normalization(self):
        """Пути с ведущим слешем нормализуются"""
        assert validate_path_access("/certificates/filter", "certificates_only") is True
        assert validate_path_access("certificates/filter", "certificates_only") is True

    def test_unknown_scope_denies_access(self):
        """Неизвестный scope запрещает доступ"""
        assert validate_path_access("certificates/filter", "unknown_scope") is False


class TestGetAllowedPaths:
    """Тесты получения разрешенных путей"""

    def test_full_scope_returns_none(self):
        """Full scope возвращает None (все пути)"""
        assert get_allowed_paths("full") is None

    def test_certificates_scope_returns_patterns(self):
        """Certificates_only scope возвращает список паттернов"""
        patterns = get_allowed_paths("certificates_only")
        assert patterns is not None
        assert len(patterns) > 0
        assert any("certificates/filter" in p for p in patterns)

    def test_unknown_scope_returns_none(self):
        """Неизвестный scope возвращает None"""
        assert get_allowed_paths("unknown") is None
```

---

### Этап 4: Обновление TokenService

**Файл:** `app/services/token_service.py`

**Изменения:**

#### 4.1 Метод `generate_access_token()`

```python
@staticmethod
def generate_access_token(
    user_id: str,
    duration_hours: int,
    scope: str,  # NEW PARAMETER
    db: Session
) -> AccessToken:
    """
    Генерирует новый access токен с указанным scope.

    Args:
        user_id: ID пользователя
        duration_hours: Длительность токена в часах
        scope: Scope токена ("full" или "certificates_only")
        db: Database session

    Returns:
        AccessToken объект
    """
    # Generate random token (48 bytes -> 64 chars)
    token_string = secrets.token_urlsafe(48)

    # Create database record
    db_token = AccessToken(
        user_id=UUID(user_id),
        token=token_string,
        duration_hours=duration_hours,
        scope=scope,  # NEW FIELD
        is_active=True,
        created_at=datetime.now(timezone.utc),
        activated_at=None,  # Will be set on first use
        revoked_at=None
    )

    db.add(db_token)
    db.commit()
    db.refresh(db_token)

    logger.info(
        f"Generated access token: user_id={user_id} "
        f"duration={duration_hours}h scope={scope}"  # LOG SCOPE
    )

    return db_token
```

#### 4.2 Метод `_cache_token()` - обновить структуру Redis

```python
def _cache_token(self, token: AccessToken) -> None:
    """
    Кеширует токен в Redis (включая scope).

    Args:
        token: AccessToken объект для кеширования
    """
    if not token.activated_at or not token.is_active:
        return

    # Calculate cache key
    token_hash = hashlib.sha256(token.token.encode()).hexdigest()
    cache_key = f"active_token:{token_hash}"

    # Prepare cache data (ADD SCOPE)
    token_data = {
        "user_id": str(token.user_id),
        "token_id": str(token.id),
        "expires_at": token.expires_at.isoformat(),
        "duration_hours": token.duration_hours,
        "scope": token.scope,  # NEW FIELD
    }

    # Calculate TTL
    ttl = int((token.expires_at - datetime.now(timezone.utc)).total_seconds())
    if ttl > 0:
        self.redis_client.setex(
            cache_key,
            ttl,
            json.dumps(token_data)
        )
        logger.debug(f"Cached token: {cache_key} with scope={token.scope}")
```

#### 4.3 Метод `validate_token()` - возвращать scope

```python
async def validate_token(self, token: str, db: Session) -> dict:
    """
    Валидирует токен и возвращает информацию (включая scope).

    Returns:
        dict с ключами: user_id, token_id, expires_at, scope

    Raises:
        HTTPException(403) если токен невалиден
    """
    # Check Redis cache first
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cache_key = f"active_token:{token_hash}"
    cached_data = self.redis_client.get(cache_key)

    if cached_data:
        data = json.loads(cached_data)
        expires_at = datetime.fromisoformat(data["expires_at"])

        # Check timezone awareness
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Check expiration
        if expires_at > datetime.now(timezone.utc):
            return {
                "user_id": data["user_id"],
                "token_id": data["token_id"],
                "expires_at": expires_at,
                "scope": data.get("scope", "full"),  # NEW FIELD (with fallback)
            }

    # Fallback to database
    db_token = db.query(AccessToken).filter(
        AccessToken.token == token,
        AccessToken.is_active == True,
        AccessToken.revoked_at == None
    ).first()

    if not db_token:
        raise HTTPException(status_code=403, detail="Invalid or expired token")

    # Activate on first use
    if not db_token.activated_at:
        db_token.activated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_token)

    # Check expiration
    if db_token.expires_at and db_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="Token expired")

    # Cache for future requests
    self._cache_token(db_token)

    return {
        "user_id": str(db_token.user_id),
        "token_id": str(db_token.id),
        "expires_at": db_token.expires_at,
        "scope": db_token.scope,  # NEW FIELD
    }
```

---

### Этап 5: Интеграция в Proxy

**Файл:** `app/api/v1/proxy.py`

#### 5.1 HTTP Proxy - добавить scope validation

```python
from app.core.permissions import validate_path_access

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_to_zenzefi(
    request: Request,
    path: str,
    zenzefi_access_token: Optional[str] = Cookie(None),
    x_access_token: Optional[str] = Header(None, alias="X-Access-Token"),
    token_service: TokenService = Depends(get_token_service),
    proxy_service: ProxyService = Depends(get_proxy_service),
    db: Session = Depends(get_db)
):
    """Proxy HTTP requests to Zenzefi with path-based access control"""

    # Get token from cookie or header (cookie has priority)
    access_token = zenzefi_access_token or x_access_token

    # Also check query param (for redirect flow)
    if not access_token:
        query_token = request.query_params.get("token")
        if query_token:
            access_token = query_token

    # Require authentication
    if not access_token:
        raise HTTPException(
            status_code=403,
            detail="Authentication required. Provide X-Access-Token header or zenzefi_access_token cookie."
        )

    # Validate token
    try:
        token_data = await token_service.validate_token(access_token, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(status_code=403, detail="Token validation failed")

    # ============ NEW: SCOPE-BASED PATH VALIDATION ============
    token_scope = token_data.get("scope", "full")

    # Validate path access
    if not validate_path_access(path, token_scope):
        logger.warning(
            f"Access denied: scope='{token_scope}' path='/{path}' "
            f"user_id={token_data.get('user_id')} token_id={token_data.get('token_id')}"
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"Access denied: your token scope ('{token_scope}') "
                f"does not allow access to '/{path}'"
            )
        )

    logger.info(
        f"Access granted: scope='{token_scope}' path='/{path}' "
        f"method={request.method} user_id={token_data.get('user_id')}"
    )
    # ============ END NEW CODE ============

    # Block source maps (existing logic)
    if path.endswith('.map'):
        raise HTTPException(status_code=404, detail="Source maps not available")

    # Determine X-Local-Url for content rewriting
    x_local_url = request.headers.get("X-Local-Url", "")
    use_desktop_client_mode = bool(x_local_url)

    # Proxy the request
    try:
        response = await proxy_service.proxy_request(
            method=request.method,
            path=path,
            headers=dict(request.headers),
            body=await request.body(),
            query_params=dict(request.query_params),
            access_token=access_token,
            use_desktop_client_mode=use_desktop_client_mode,
            x_local_url=x_local_url
        )
        return response
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        raise HTTPException(status_code=502, detail="Proxy error")
```

#### 5.2 WebSocket Proxy - блокировать для certificates_only

```python
@router.websocket("/{path:path}")
async def websocket_proxy(
    websocket: WebSocket,
    path: str,
    token: Optional[str] = Query(None),
    zenzefi_access_token: Optional[str] = Cookie(None),
    token_service: TokenService = Depends(get_token_service),
    proxy_service: ProxyService = Depends(get_proxy_service),
    db: Session = Depends(get_db)
):
    """Proxy WebSocket connections to Zenzefi (blocked for certificates_only scope)"""

    await websocket.accept()

    # Get token
    access_token = token or zenzefi_access_token

    if not access_token:
        await websocket.close(code=1008, reason="Authentication required")
        return

    # Validate token
    try:
        token_data = await token_service.validate_token(access_token, db)
    except HTTPException:
        await websocket.close(code=1008, reason="Invalid token")
        return
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        await websocket.close(code=1011, reason="Token validation failed")
        return

    # ============ NEW: BLOCK WEBSOCKET FOR CERTIFICATES_ONLY ============
    token_scope = token_data.get("scope", "full")

    if token_scope == "certificates_only":
        logger.warning(
            f"WebSocket denied: scope='certificates_only' does not allow WebSocket "
            f"user_id={token_data.get('user_id')}"
        )
        await websocket.close(
            code=1008,
            reason="WebSocket not allowed for certificate-only tokens"
        )
        return
    # ============ END NEW CODE ============

    # Proxy WebSocket (existing logic)
    try:
        await proxy_service.proxy_websocket(
            websocket=websocket,
            path=path,
            access_token=access_token
        )
    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
        await websocket.close(code=1011, reason="Proxy error")
```

---

### Этап 6: API Endpoint для покупки

**Файл:** `app/api/v1/tokens.py`

```python
@router.post("/purchase", response_model=TokenInDB, status_code=201)
async def purchase_token(
    token_create: TokenCreate,  # Теперь включает scope
    current_user: User = Depends(get_current_user),
    token_service: TokenService = Depends(get_token_service),
    db: Session = Depends(get_db)
):
    """
    Покупка нового access токена (MVP: бесплатно).

    Токен может иметь scope:
    - "full": полный доступ ко всем endpoint'ам Zenzefi
    - "certificates_only": доступ только к /certificates/* endpoint'ам
    """
    # Validate duration
    valid_durations = [1, 12, 24, 168, 720]
    if token_create.duration_hours not in valid_durations:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid duration. Allowed: {valid_durations} hours"
        )

    # Validate scope (already validated by Pydantic, but double-check)
    if token_create.scope not in ["full", "certificates_only"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid scope. Allowed: 'full' or 'certificates_only'"
        )

    # Generate token with scope
    new_token = token_service.generate_access_token(
        user_id=str(current_user.id),
        duration_hours=token_create.duration_hours,
        scope=token_create.scope,  # NEW PARAMETER
        db=db
    )

    logger.info(
        f"Token purchased: user={current_user.username} "
        f"duration={token_create.duration_hours}h scope={token_create.scope}"
    )

    return new_token
```

---

### Этап 7: Тестирование

**Файл:** `tests/test_token_scopes.py` (новый)

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.token import AccessToken
from app.models.user import User
from datetime import datetime, timezone
import secrets


class TestTokenScopePurchase:
    """Тесты покупки токенов с scope"""

    def test_purchase_full_scope_token(self, client: TestClient, test_user: User, auth_headers: dict):
        """Покупка токена с full scope"""
        response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24, "scope": "full"},
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["scope"] == "full"
        assert data["duration_hours"] == 24

    def test_purchase_certificates_scope_token(self, client: TestClient, test_user: User, auth_headers: dict):
        """Покупка токена с certificates_only scope"""
        response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24, "scope": "certificates_only"},
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["scope"] == "certificates_only"

    def test_default_scope_is_full(self, client: TestClient, test_user: User, auth_headers: dict):
        """Scope по умолчанию = full"""
        response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24},  # scope не указан
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["scope"] == "full"

    def test_invalid_scope_rejected(self, client: TestClient, test_user: User, auth_headers: dict):
        """Невалидный scope отклоняется"""
        response = client.post(
            "/api/v1/tokens/purchase",
            json={"duration_hours": 24, "scope": "invalid_scope"},
            headers=auth_headers
        )
        assert response.status_code == 422  # Pydantic validation error


class TestTokenScopeValidation:
    """Тесты валидации путей для scopes"""

    def test_full_scope_accesses_all_paths(self, client: TestClient, db: Session, test_user: User):
        """Full scope токен имеет доступ ко всем путям"""
        # Create full scope token
        token = create_test_token(db, test_user, scope="full")

        # Test various paths
        paths = [
            "certificates/filter",
            "users/currentUser",
            "system/version",
            "logs/filter"
        ]

        for path in paths:
            response = client.get(
                f"/api/v1/proxy/{path}",
                headers={"X-Access-Token": token.token}
            )
            assert response.status_code != 403, f"Full scope should allow {path}"

    def test_certificates_scope_allows_certificate_paths(self, client: TestClient, db: Session, test_user: User):
        """Certificates_only токен имеет доступ к /certificates/*"""
        token = create_test_token(db, test_user, scope="certificates_only")

        allowed_paths = [
            "certificates/filter",
            "certificates/details/123",
            "certificates/export/456",
            "certificates/import/files",
            "certificates/activeForTesting",
            "certificates/update/789"
        ]

        for path in allowed_paths:
            response = client.get(
                f"/api/v1/proxy/{path}",
                headers={"X-Access-Token": token.token}
            )
            # Может быть 502 (если Zenzefi недоступен), но НЕ 403
            assert response.status_code != 403, f"Should allow {path}"

    def test_certificates_scope_blocks_other_paths(self, client: TestClient, db: Session, test_user: User):
        """Certificates_only токен блокирует не-certificate пути"""
        token = create_test_token(db, test_user, scope="certificates_only")

        blocked_paths = [
            "users/currentUser",
            "system/version",
            "logs/filter",
            "zenzefi/ui/environment",
            "configurations/autologout"
        ]

        for path in blocked_paths:
            response = client.get(
                f"/api/v1/proxy/{path}",
                headers={"X-Access-Token": token.token}
            )
            assert response.status_code == 403, f"Should block {path}"
            assert "does not allow access" in response.json()["detail"]


class TestWebSocketScope:
    """Тесты WebSocket для scopes"""

    def test_full_scope_allows_websocket(self, client: TestClient, db: Session, test_user: User):
        """Full scope токен может использовать WebSocket"""
        token = create_test_token(db, test_user, scope="full")

        with client.websocket_connect(
            f"/api/v1/proxy/ws/info?token={token.token}"
        ) as websocket:
            # WebSocket должен подключиться без ошибок
            pass  # Connection successful

    def test_certificates_scope_blocks_websocket(self, client: TestClient, db: Session, test_user: User):
        """Certificates_only токен НЕ может использовать WebSocket"""
        token = create_test_token(db, test_user, scope="certificates_only")

        with pytest.raises(Exception) as exc_info:
            with client.websocket_connect(
                f"/api/v1/proxy/ws/info?token={token.token}"
            ) as websocket:
                pass

        # Should close with code 1008 (policy violation)
        assert "1008" in str(exc_info.value) or "WebSocket not allowed" in str(exc_info.value)


class TestRedisCache:
    """Тесты кеширования scope в Redis"""

    def test_redis_cache_includes_scope(self, redis_client, token_service, db: Session, test_user: User):
        """Redis кеш содержит scope информацию"""
        # Create token with certificates_only scope
        token = token_service.generate_access_token(
            user_id=str(test_user.id),
            duration_hours=24,
            scope="certificates_only",
            db=db
        )

        # Activate token
        token.activated_at = datetime.now(timezone.utc)
        db.commit()

        # Cache token
        token_service._cache_token(token)

        # Verify cache
        import hashlib, json
        token_hash = hashlib.sha256(token.token.encode()).hexdigest()
        cache_key = f"active_token:{token_hash}"
        cached_data = redis_client.get(cache_key)

        assert cached_data is not None
        data = json.loads(cached_data)
        assert data["scope"] == "certificates_only"


# Helper function
def create_test_token(db: Session, user: User, scope: str = "full") -> AccessToken:
    """Создает тестовый токен с активацией"""
    token = AccessToken(
        user_id=user.id,
        token=secrets.token_urlsafe(48),
        duration_hours=24,
        scope=scope,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        activated_at=datetime.now(timezone.utc),
        revoked_at=None
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token
```

**Запуск тестов:**

```bash
# Запустить все scope тесты
poetry run pytest tests/test_token_scopes.py -v

# Запустить тесты permissions
poetry run pytest tests/test_permissions.py -v

# Запустить все тесты с coverage
poetry run pytest tests/ -v --cov=app --cov-report=html
```

---

### Этап 8: Документация

#### 8.1 Обновить CLAUDE.md

Добавить секцию:

```markdown
## Token Scopes

**Scope Types:**
- `"full"` - Full access to all Zenzefi endpoints (Desktop Client)
- `"certificates_only"` - Access only to `/certificates/*` endpoints (DTS Monaco)

**Purchasing scoped token:**
\`\`\`bash
POST /api/v1/tokens/purchase
Authorization: Bearer {jwt_token}

{
  "duration_hours": 24,
  "scope": "certificates_only"
}
\`\`\`

**Using scoped token:**
\`\`\`bash
# Allowed
GET /api/v1/proxy/certificates/filter
X-Access-Token: {certificates_only_token}

# Blocked - 403 Forbidden
GET /api/v1/proxy/users/currentUser
X-Access-Token: {certificates_only_token}
\`\`\`

**Adding new allowed paths:**
Edit `app/core/permissions.py` → `SCOPE_PERMISSIONS["certificates_only"]`
```

#### 8.2 Обновить docs/ARCHITECTURE.md

Добавить диаграмму:

```markdown
### Access Control Flow

\`\`\`
[DTS Monaco Client]
    ↓ X-Access-Token: {scope=certificates_only}
[Proxy Endpoint]
    ↓ validate_token() → {user_id, token_id, expires_at, scope}
    ↓ validate_path_access(path, scope)
    ↓ ✅ /certificates/filter → ALLOWED
    ↓ ❌ /users/currentUser → BLOCKED (403)
[Zenzefi Server] (if allowed)
\`\`\`
```

---

### Этап 9: Логирование и мониторинг

#### 9.1 Добавить детальное логирование

**Файл:** `app/core/logging.py` (обновить)

```python
import json
from datetime import datetime

# Структурированный лог для анализа
def log_access_attempt(
    user_id: str,
    token_id: str,
    scope: str,
    path: str,
    method: str,
    allowed: bool
):
    """Логирует попытку доступа для аналитики"""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "token_id": token_id,
        "scope": scope,
        "path": path,
        "method": method,
        "allowed": allowed,
        "event_type": "access_attempt"
    }

    if allowed:
        logger.info(f"ACCESS_GRANTED: {json.dumps(log_entry)}")
    else:
        logger.warning(f"ACCESS_DENIED: {json.dumps(log_entry)}")
```

#### 9.2 (Опционально) Счетчики в Redis

```python
# В proxy.py после валидации
if not allowed:
    # Increment blocked attempts counter
    date_key = datetime.utcnow().strftime("%Y-%m-%d")
    redis_client.incr(f"blocked_access:{scope}:{date_key}")
    redis_client.expire(f"blocked_access:{scope}:{date_key}", 86400 * 30)  # 30 days
```

---

## Чеклист выполнения

### Database & Models

- [ ] Создать Alembic migration для поля `scope`
- [ ] Применить миграцию: `poetry run alembic upgrade head`
- [ ] Обновить `app/models/token.py` (добавить `scope` field)
- [ ] Обновить `app/schemas/token.py` (TokenCreate, TokenInDB)
- [ ] Протестировать миграцию (upgrade/downgrade)

### Core Logic

- [ ] Создать `app/core/permissions.py` с `SCOPE_PERMISSIONS`
- [ ] Реализовать `validate_path_access(path, scope)`
- [ ] Реализовать `get_allowed_paths(scope)`
- [ ] Написать unit-тесты для permissions (`tests/test_permissions.py`)

### Services

- [ ] Обновить `TokenService.generate_access_token()` (принять `scope`)
- [ ] Обновить `TokenService._cache_token()` (включить `scope` в Redis)
- [ ] Обновить `TokenService.validate_token()` (возвращать `scope`)
- [ ] Обновить `TokenService.check_token_status()` (возвращать `scope`)

### API Endpoints

- [ ] Обновить `/api/v1/tokens/purchase` (принять `scope` в body)
- [ ] Обновить `/api/v1/proxy/{path}` HTTP (добавить scope validation)
- [ ] Обновить `/api/v1/proxy/{path}` WebSocket (блокировать certificates_only)

### Testing

- [ ] Написать тесты purchase с scope (`test_token_scopes.py`)
- [ ] Написать тесты path validation
- [ ] Написать тесты WebSocket блокировки
- [ ] Написать тесты Redis кеширования
- [ ] Запустить все тесты: `poetry run pytest tests/ -v`
- [ ] Проверить coverage: `poetry run pytest --cov=app`

### Documentation

- [ ] Создать `docs/FIDDLER_SETUP.md` ✅
- [ ] Создать `docs/DTS_MONACO_SCOPE_PLAN.md` ✅
- [ ] Обновить `CLAUDE.md` (секция Token Scopes)
- [ ] Обновить `docs/ARCHITECTURE.md` (Access Control Flow)

### Validation

- [ ] Перехватить реальные API запросы с Fiddler (см. FIDDLER_SETUP.md)
- [ ] Обновить `SCOPE_PERMISSIONS` с реальными endpoint'ами
- [ ] Протестировать с реальным DTS Monaco клиентом
- [ ] Проверить логи: `tail -f logs/app.log | grep ACCESS_`

### Deployment

- [ ] Создать backup БД перед миграцией
- [ ] Применить миграцию в production
- [ ] Выкатить новый код
- [ ] Мониторинг ошибок в первые 24 часа

## Технические детали

### Redis Cache Structure (обновленная)

```python
Key: "active_token:{sha256(token)}"
Value: {
    "user_id": "uuid",
    "token_id": "uuid",
    "expires_at": "ISO datetime",
    "duration_hours": 24,
    "scope": "certificates_only"  # NEW
}
TTL: До истечения токена
```

### API Examples

**Покупка токена для DTS Monaco:**

```bash
POST /api/v1/tokens/purchase
Authorization: Bearer {jwt_token}

{
  "duration_hours": 24,
  "scope": "certificates_only"
}
```

**Использование токена:**

```bash
GET /api/v1/proxy/certificates/filter
X-Access-Token: {64-char-token}
```

**Заблокированный запрос:**

```bash
GET /api/v1/proxy/users/currentUser
X-Access-Token: {certificates_only_token}

Response: 403 Forbidden
{
  "detail": "Access denied: your token scope ('certificates_only') does not allow access to '/users/currentUser'"
}
```

## Преимущества решения

✅ **Точные пути** - конкретные certificate endpoints из Zenzefi UI
✅ **Минимальные изменения** - одно поле в БД + валидация
✅ **Обратная совместимость** - существующие токены = scope='full'
✅ **Безопасность** - проверка ДО отправки к Zenzefi
✅ **WebSocket блокировка** - для certificates_only
✅ **Гибкость** - легко добавить новые paths в `permissions.py`

## Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Endpoint'ы из JS не полные | Средняя | Среднее | Перехватить реальные запросы с Fiddler |
| Существующие токены сломаются | Низкая | Критическое | Migration с DEFAULT 'full', backward-compatible |
| DTS Monaco нужны дополнительные пути | Средняя | Низкое | Легко добавить в `permissions.py` |
| Performance overhead валидации | Низкая | Низкое | Проверка только regex, кешированные compiled patterns |
| WebSocket блокировка сломает функциональность | Низкая | Среднее | DTS Monaco подтверждает что WS не нужен |

## Следующие шаги после реализации

1. ✅ **Перехватить реальные API** с Fiddler (30-60 минут)
2. ✅ **Обновить SCOPE_PERMISSIONS** с реальными endpoint'ами
3. ✅ **Протестировать интеграцию** с DTS Monaco
4. ✅ **Собрать метрики** заблокированных попыток (7 дней)
5. ✅ **Удалить cookie auth** после успешного тестирования (optional)
6. ✅ **Добавить мониторинг** Prometheus metrics (будущая задача)

## Контакты и ресурсы

- **Документация проекта:** `docs/`
- **Fiddler Setup:** `docs/FIDDLER_SETUP.md`
- **Архитектура:** `docs/ARCHITECTURE.md`
- **Тестирование:** `docs/claude/TESTING.md`

## Оценка трудозатрат

- **Этапы 1-6:** ~5-6 часов (implementation)
- **Этап 7:** ~2-3 часа (tests)
- **Этапы 8-9:** ~1-2 часа (documentation)
- **Fiddler перехват:** ~1 час (validation)
- **Итого:** ~9-12 часов работы

---

**Статус:** ✏️ Планирование завершено, готов к реализации после валидации endpoint'ов
**Обновлено:** 2025-01-10
