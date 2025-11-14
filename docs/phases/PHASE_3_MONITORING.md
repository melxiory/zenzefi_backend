# Этап 3: Мониторинг

**Статус:** ⏳ ЧАСТИЧНО РЕАЛИЗОВАНО
**Зависимости:** Этап 2 (Валюта) должен быть завершён
**Время:** 3-5 дней

---

## Цель

Добавить инструменты для мониторинга активности, управления пользователями и audit logging.

---

## ✅ УЖЕ РЕАЛИЗОВАНО (из Этапа 1)

**Health Check System:**
- GET /health - минимальная проверка из Redis (~1ms, только status + timestamp)
- Background scheduler (APScheduler, 50s interval)
- Проверки: PostgreSQL, Redis, Zenzefi server
- Redis кеширование результатов (TTL: 120s)

---

## Задачи

### Задача 1: ProxySession Tracking (1-2 дня)

#### ProxySession Model

```python
# app/models/proxy_session.py
from sqlalchemy import Column, String, Boolean, DateTime, BigInteger, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship

class ProxySession(Base):
    __tablename__ = "proxy_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token_id = Column(UUID(as_uuid=True), ForeignKey("access_tokens.id"), nullable=False, index=True)
    ip_address = Column(INET, nullable=False)  # PostgreSQL INET type
    user_agent = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False)
    last_activity = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    bytes_transferred = Column(BigInteger, default=0, nullable=False)
    request_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="proxy_sessions")
    token = relationship("AccessToken", back_populates="proxy_sessions")
```

**Update User model:**
```python
# app/models/user.py - добавить
proxy_sessions = relationship("ProxySession", back_populates="user", cascade="all, delete-orphan")
```

**Update AccessToken model:**
```python
# app/models/token.py - добавить
proxy_sessions = relationship("ProxySession", back_populates="token")
```

#### Middleware для автоматического трекинга

```python
# app/middleware/session_tracking.py
from starlette.middleware.base import BaseHTTPMiddleware
from app.models.proxy_session import ProxySession

class ProxySessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip non-proxy requests
        if not request.url.path.startswith("/api/v1/proxy"):
            return await call_next(request)

        # Extract token data from request state (set by auth dependency)
        user_id = request.state.user_id
        token_id = request.state.token_id
        ip_address = request.client.host

        db = next(get_db())

        try:
            # Find or create session
            session = db.query(ProxySession).filter(
                ProxySession.user_id == user_id,
                ProxySession.token_id == token_id,
                ProxySession.is_active == True
            ).first()

            if not session:
                session = ProxySession(
                    user_id=user_id,
                    token_id=token_id,
                    ip_address=ip_address,
                    user_agent=request.headers.get("user-agent")
                )
                db.add(session)

            # Process request
            response = await call_next(request)

            # Update session stats
            session.last_activity = datetime.now(timezone.utc)
            session.request_count += 1

            if hasattr(response, "body_length"):
                session.bytes_transferred += response.body_length

            db.commit()

            return response

        finally:
            db.close()
```

#### Background Cleanup Task

```python
# app/core/session_cleanup.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

def cleanup_inactive_sessions():
    """Close sessions inactive for > 1 hour"""
    db = next(get_db())

    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)

    sessions = db.query(ProxySession).filter(
        ProxySession.is_active == True,
        ProxySession.last_activity < cutoff_time
    ).all()

    for session in sessions:
        session.is_active = False
        session.ended_at = datetime.now(timezone.utc)

    db.commit()
    db.close()

# Schedule in app/main.py startup
scheduler.add_job(cleanup_inactive_sessions, "interval", minutes=15)
```

**Миграция:**
```bash
poetry run alembic revision --autogenerate -m "Add ProxySession model"
poetry run alembic upgrade head
```

---

### Задача 2: Admin Endpoints (1 день)

#### Admin Dependency

```python
# app/api/deps.py
def get_current_superuser(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Require superuser permissions"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Superuser permissions required"
        )
    return current_user
```

#### Admin API

```python
# app/api/v1/admin.py
from fastapi import APIRouter, Depends, Query
from app.api.deps import get_current_superuser

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/users")
async def list_users(
    limit: int = Query(50, le=100),
    offset: int = 0,
    search: str | None = None,
    is_active: bool | None = None,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """List all users (superuser only)"""
    query = db.query(User)

    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) |
            (User.username.ilike(f"%{search}%"))
        )

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    users = query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()

    return {
        "items": [UserResponse.from_orm(u) for u in users],
        "total": total,
        "limit": limit,
        "offset": offset
    }

@router.get("/tokens")
async def list_tokens(
    user_id: UUID | None = None,
    active_only: bool = True,
    limit: int = Query(50, le=100),
    offset: int = 0,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """List all access tokens (superuser only)"""
    query = db.query(AccessToken)

    if user_id:
        query = query.filter(AccessToken.user_id == user_id)

    if active_only:
        query = query.filter(AccessToken.is_active == True)

    total = query.count()
    tokens = query.order_by(AccessToken.created_at.desc()).limit(limit).offset(offset).all()

    return {
        "items": [TokenResponse.from_orm(t) for t in tokens],
        "total": total,
        "limit": limit,
        "offset": offset
    }

@router.patch("/users/{user_id}")
async def update_user(
    user_id: UUID,
    request: AdminUserUpdate,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Update user (superuser only)"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update fields
    if request.is_active is not None:
        user.is_active = request.is_active

    if request.is_superuser is not None:
        user.is_superuser = request.is_superuser

    if request.currency_balance is not None:
        user.currency_balance = request.currency_balance

    db.commit()
    db.refresh(user)

    return UserResponse.from_orm(user)

@router.delete("/tokens/{token_id}")
async def force_revoke_token(
    token_id: UUID,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Force revoke token without refund (superuser only)"""
    token = db.query(AccessToken).filter(AccessToken.id == token_id).first()

    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    token.is_active = False
    token.revoked_at = datetime.now(timezone.utc)

    db.commit()

    # Remove from Redis
    TokenService._remove_cached_token(token.token)

    return {"revoked": True, "token_id": str(token_id)}
```

---

### Задача 3: Audit Logging (1 день)

#### AuditLog Model

```python
# app/models/audit_log.py
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)  # "token_purchase", "token_revoke", "user_update"
    resource_type = Column(String, nullable=False)  # "AccessToken", "User", "Transaction"
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(JSON, nullable=True)  # Additional context
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False, index=True)
```

#### Audit Service

```python
# app/services/audit_service.py
class AuditService:

    @staticmethod
    def log(
        action: str,
        resource_type: str,
        resource_id: UUID | None,
        user_id: UUID | None,
        details: dict | None,
        db: Session,
        request: Request | None = None
    ):
        """Create audit log entry"""
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None
        )

        db.add(audit_log)
        # Commit handled by caller
```

#### Использование в сервисах

```python
# app/services/token_service.py - добавить audit logging
def generate_access_token(...):
    # ... existing code

    # Audit log
    AuditService.log(
        action="token_purchase",
        resource_type="AccessToken",
        resource_id=db_token.id,
        user_id=user_id,
        details={"duration_hours": duration_hours, "cost_znc": float(cost), "scope": scope},
        db=db
    )

    db.commit()
    return db_token, cost
```

#### Retention Policy (Background Task)

```python
# app/core/audit_cleanup.py
def cleanup_old_audit_logs():
    """Delete audit logs older than 30 days"""
    db = next(get_db())

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

    db.query(AuditLog).filter(AuditLog.created_at < cutoff_date).delete()

    db.commit()
    db.close()

# Schedule daily at 3 AM
scheduler.add_job(cleanup_old_audit_logs, "cron", hour=3, minute=0)
```

**Миграция:**
```bash
poetry run alembic revision --autogenerate -m "Add AuditLog model"
poetry run alembic upgrade head
```

---

### Задача 4: Prometheus Metrics (1 день)

#### Setup Prometheus

```python
# app/core/metrics.py
from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Counters
proxy_requests_total = Counter(
    "zenzefi_proxy_requests_total",
    "Total proxy requests",
    ["method", "status", "scope"]
)

auth_attempts_total = Counter(
    "zenzefi_auth_attempts_total",
    "Total authentication attempts",
    ["status"]
)

token_purchases_total = Counter(
    "zenzefi_token_purchases_total",
    "Total token purchases",
    ["duration_hours", "scope"]
)

# Gauges
active_tokens = Gauge(
    "zenzefi_active_tokens",
    "Number of active tokens"
)

active_sessions = Gauge(
    "zenzefi_active_sessions",
    "Number of active proxy sessions"
)

user_count = Gauge(
    "zenzefi_user_count",
    "Total number of users"
)

# Histograms
proxy_latency_seconds = Histogram(
    "zenzefi_proxy_latency_seconds",
    "Proxy request latency",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

db_query_duration_seconds = Histogram(
    "zenzefi_db_query_duration_seconds",
    "Database query duration",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1]
)
```

#### Metrics Endpoint

```python
# app/api/v1/metrics.py
from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter()

@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

#### Update Proxy Middleware

```python
# app/middleware/session_tracking.py - добавить metrics
import time

async def dispatch(self, request: Request, call_next):
    start_time = time.time()

    response = await call_next(request)

    # Metrics
    latency = time.time() - start_time
    proxy_latency_seconds.observe(latency)
    proxy_requests_total.labels(
        method=request.method,
        status=response.status_code,
        scope=request.state.scope
    ).inc()

    return response
```

#### Background Metrics Updater

```python
# app/core/metrics_updater.py
def update_gauges():
    """Update gauge metrics"""
    db = next(get_db())

    # Active tokens
    active_tokens.set(db.query(AccessToken).filter(AccessToken.is_active == True).count())

    # Active sessions
    active_sessions.set(db.query(ProxySession).filter(ProxySession.is_active == True).count())

    # User count
    user_count.set(db.query(User).count())

    db.close()

# Schedule every 30 seconds
scheduler.add_job(update_gauges, "interval", seconds=30)
```

**Dependencies:**
```bash
poetry add prometheus-client
```

---

## Roadmap Этапа 3

| День | Задача | Описание |
|------|--------|----------|
| 1 | ProxySession Model | Database model + миграции |
| 2 | Session Tracking | Middleware + background cleanup |
| 3 | Admin Endpoints | GET/PATCH users, tokens, force revoke |
| 4 | Audit Logging | Model, service, integration, cleanup |
| 5 | Prometheus Metrics | Setup, endpoint, middleware integration |

**Результат:** Полный мониторинг активности с admin панелью и audit trail.

---

## Testing

**Test Coverage:**
```python
# tests/test_proxy_session.py
test_session_creation()
test_session_update_stats()
test_session_cleanup()

# tests/test_admin_endpoints.py
test_list_users_requires_superuser()
test_list_tokens_filtering()
test_force_revoke_token()

# tests/test_audit_log.py
test_audit_log_creation()
test_audit_log_cleanup()

# tests/test_metrics.py
test_prometheus_metrics_endpoint()
test_metrics_incremented_on_request()
```

**Запуск:**
```bash
poetry run pytest tests/test_proxy_session.py -v
poetry run pytest tests/test_admin_endpoints.py -v
```

---

**Следующий этап:** [Этап 4 (Production)](./PHASE_4_PRODUCTION.md) - Rate limiting, CI/CD, Load testing

---

**См. также:**
- [PHASE_1_MVP.md](./PHASE_1_MVP.md) - MVP (завершён)
- [PHASE_2_CURRENCY.md](./PHASE_2_CURRENCY.md) - Система валюты (предыдущий этап)
- [BACKEND.md](../BACKEND.md) - Overview
- [ADR.md](../ADR.md) - Architecture Decision Records
