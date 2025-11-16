# Будущие возможности (Future Features)

**Статус:** 💡 ИДЕИ ДЛЯ БУДУЩЕЙ РАЗРАБОТКИ
**Приоритет:** Низкий (после завершения этапов 1-4)
**Время:** 10-15 дней (распределено по функциям)

---

## Обзор

Этот документ описывает дополнительные функции, которые могут быть реализованы после завершения основных этапов MVP, Currency System, Monitoring и Production Readiness. Эти фичи направлены на расширение монетизации, улучшение пользовательского опыта и увеличение retention.

---

## Этап 2.5: Token Bundles & Referrals

**Зависимости:** Этап 2 (Currency System) завершён
**Время:** 3-4 дня
**Цель:** Увеличить продажи через пакетные предложения и реферальную программу

### 1. Token Bundles (Пакетные предложения)

#### TokenBundle Model

```python
# app/models/bundle.py
from sqlalchemy import Column, String, Integer, Boolean, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid

class TokenBundle(Base):
    __tablename__ = "token_bundles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)  # "Starter Pack", "Pro Bundle", "Ultimate Package"
    description = Column(String, nullable=True)
    token_count = Column(Integer, nullable=False)  # 5, 10, 20 tokens
    duration_hours = Column(Integer, nullable=False)  # Each token duration
    scope = Column(String, default="full", nullable=False)  # Token scope
    discount_percent = Column(Numeric(5, 2), nullable=False)  # 10.00 = 10% off
    base_price = Column(Numeric(10, 2), nullable=False)  # Without discount
    total_price = Column(Numeric(10, 2), nullable=False)  # With discount
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
```

#### Bundle Purchase Endpoint

```python
# app/api/v1/bundles.py
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/bundles", tags=["bundles"])

@router.get("/")
async def list_bundles(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """List available token bundles"""
    query = db.query(TokenBundle)

    if active_only:
        query = query.filter(TokenBundle.is_active == True)

    bundles = query.order_by(TokenBundle.total_price).all()

    return {"items": [BundleResponse.from_orm(b) for b in bundles]}

@router.post("/{bundle_id}/purchase")
async def purchase_bundle(
    bundle_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Purchase token bundle"""
    bundle = db.query(TokenBundle).filter(
        TokenBundle.id == bundle_id,
        TokenBundle.is_active == True
    ).first()

    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    # Check balance
    if current_user.currency_balance < bundle.total_price:
        raise HTTPException(status_code=402, detail="Insufficient balance")

    # Deduct balance
    current_user.currency_balance -= bundle.total_price

    # Generate tokens
    tokens = []
    for _ in range(bundle.token_count):
        token = TokenService.generate_access_token(
            user_id=current_user.id,
            duration_hours=bundle.duration_hours,
            scope=bundle.scope,
            db=db
        )
        tokens.append(token)

    # Create transaction
    transaction = Transaction(
        user_id=current_user.id,
        amount=-bundle.total_price,
        transaction_type=TransactionType.PURCHASE,
        description=f"Bundle purchase: {bundle.name} ({bundle.token_count} tokens)"
    )
    db.add(transaction)
    db.commit()

    return {
        "bundle_name": bundle.name,
        "tokens_generated": len(tokens),
        "cost_znc": float(bundle.total_price),
        "tokens": [TokenResponse.from_orm(t) for t in tokens]
    }
```

**Примеры бандлов:**
```python
# Starter Pack
{
    "name": "Starter Pack",
    "token_count": 5,
    "duration_hours": 24,
    "discount_percent": 10.00,
    "base_price": 90.00,  # 5 * 18 ZNC
    "total_price": 81.00   # 10% off
}

# Pro Bundle
{
    "name": "Pro Bundle",
    "token_count": 10,
    "duration_hours": 24,
    "discount_percent": 15.00,
    "base_price": 180.00,
    "total_price": 153.00  # 15% off
}

# Ultimate Package
{
    "name": "Ultimate Package",
    "token_count": 20,
    "duration_hours": 168,  # 7 days each
    "discount_percent": 20.00,
    "base_price": 2000.00,
    "total_price": 1600.00  # 20% off
}
```

---

### 2. Referral System (Реферальная программа)

#### User Model Updates

```python
# app/models/user.py - добавить поля
referral_code = Column(String(12), unique=True, nullable=False, index=True)
referred_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
referral_bonus_earned = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)

# Relationships
referred_by = relationship("User", foreign_keys=[referred_by_id], remote_side=[id])
referrals = relationship("User", foreign_keys=[referred_by_id])
```

#### Referral Code Generation

```python
# app/services/auth_service.py - обновить register()
import secrets

def register(email, username, password, referral_code=None, db):
    # ... existing validation

    # Generate unique referral code
    user_referral_code = secrets.token_urlsafe(8)[:12].upper()

    # Find referrer
    referrer_id = None
    if referral_code:
        referrer = db.query(User).filter(User.referral_code == referral_code).first()
        if referrer:
            referrer_id = referrer.id

    db_user = User(
        email=email,
        username=username,
        hashed_password=hash_password(password),
        referral_code=user_referral_code,
        referred_by_id=referrer_id
    )

    db.add(db_user)
    db.commit()

    return db_user
```

#### Referral Bonus Logic

```python
# app/services/currency_service.py
REFERRAL_BONUS_PERCENT = Decimal("0.10")  # 10% bonus

def award_referral_bonus(user_id, purchase_amount, db):
    """Award referral bonus to referrer"""
    user = db.query(User).filter(User.id == user_id).first()

    if user.referred_by_id:
        bonus = purchase_amount * REFERRAL_BONUS_PERCENT
        bonus = bonus.quantize(Decimal("0.01"))

        referrer = db.query(User).filter(User.id == user.referred_by_id).with_for_update().first()
        referrer.currency_balance += bonus
        referrer.referral_bonus_earned += bonus

        # Create transaction
        transaction = Transaction(
            user_id=referrer.id,
            amount=bonus,
            transaction_type=TransactionType.DEPOSIT,
            description=f"Referral bonus from {user.username}"
        )

        db.add(transaction)
        db.commit()

        return bonus

    return Decimal("0.00")
```

#### Referral Stats Endpoint

```python
# app/api/v1/users.py
@router.get("/me/referrals")
async def get_referral_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user's referral statistics"""
    referrals = db.query(User).filter(User.referred_by_id == current_user.id).all()

    return {
        "referral_code": current_user.referral_code,
        "total_referrals": len(referrals),
        "bonus_earned": float(current_user.referral_bonus_earned),
        "referrals": [
            {
                "username": r.username,
                "joined_at": r.created_at.isoformat()
            }
            for r in referrals
        ]
    }
```

---

## Этап 3.5: Usage Analytics

**Зависимости:** Этап 3 (Monitoring) завершён
**Время:** 2-3 дня
**Цель:** Предоставить пользователям и админам статистику использования

### User Usage Analytics

```python
# app/api/v1/analytics.py
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/usage")
async def get_usage_stats(
    period: str = Query("day", regex="^(day|week|month)$"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """User usage statistics"""
    # Calculate time range
    now = datetime.now(timezone.utc)
    period_map = {
        "day": timedelta(days=1),
        "week": timedelta(weeks=1),
        "month": timedelta(days=30)
    }
    start_time = now - period_map[period]

    # Aggregate ProxySession data
    sessions = db.query(ProxySession).filter(
        ProxySession.user_id == current_user.id,
        ProxySession.started_at >= start_time
    ).all()

    total_requests = sum(s.request_count for s in sessions)
    total_bytes = sum(s.bytes_transferred for s in sessions)

    # Active sessions
    active_sessions = db.query(ProxySession).filter(
        ProxySession.user_id == current_user.id,
        ProxySession.is_active == True
    ).count()

    # Token usage
    active_tokens = db.query(AccessToken).filter(
        AccessToken.user_id == current_user.id,
        AccessToken.is_active == True
    ).count()

    return {
        "period": period,
        "start_time": start_time.isoformat(),
        "end_time": now.isoformat(),
        "total_requests": total_requests,
        "total_bytes_transferred": total_bytes,
        "active_sessions": active_sessions,
        "active_tokens": active_tokens,
        "avg_session_duration_minutes": sum(
            (s.ended_at or now).timestamp() - s.started_at.timestamp()
            for s in sessions
        ) / len(sessions) / 60 if sessions else 0
    }

@router.get("/admin/global-stats")
async def get_global_stats(
    period: str = Query("day", regex="^(day|week|month)$"),
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """Global platform statistics (admin only)"""
    now = datetime.now(timezone.utc)
    period_map = {
        "day": timedelta(days=1),
        "week": timedelta(weeks=1),
        "month": timedelta(days=30)
    }
    start_time = now - period_map[period]

    # New users
    new_users = db.query(User).filter(User.created_at >= start_time).count()

    # Token purchases
    token_purchases = db.query(Transaction).filter(
        Transaction.transaction_type == TransactionType.PURCHASE,
        Transaction.created_at >= start_time
    ).count()

    # Revenue
    revenue = db.query(func.sum(Transaction.amount)).filter(
        Transaction.transaction_type == TransactionType.PURCHASE,
        Transaction.created_at >= start_time
    ).scalar() or Decimal("0.00")

    # Total proxy requests
    total_requests = db.query(func.sum(ProxySession.request_count)).filter(
        ProxySession.started_at >= start_time
    ).scalar() or 0

    return {
        "period": period,
        "start_time": start_time.isoformat(),
        "new_users": new_users,
        "token_purchases": token_purchases,
        "revenue_znc": float(abs(revenue)),
        "total_proxy_requests": total_requests
    }
```

---

## Этап 4.5: Notification System

**Зависимости:** Этапы 2-3 завершены
**Время:** 4-5 дней
**Цель:** Уведомления пользователей о важных событиях

### 1. Email Notifications

#### Email Service

```python
# app/services/email_service.py
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.config import settings

conf = ConnectionConfig(
    MAIL_USERNAME=settings.SMTP_USERNAME,
    MAIL_PASSWORD=settings.SMTP_PASSWORD,
    MAIL_FROM=settings.SMTP_FROM_EMAIL,
    MAIL_PORT=settings.SMTP_PORT,
    MAIL_SERVER=settings.SMTP_HOST,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True
)

class EmailService:

    @staticmethod
    async def send_token_expiring_soon(user: User, token: AccessToken):
        """Notify user that token expires in 24 hours"""
        message = MessageSchema(
            subject="Your access token expires soon",
            recipients=[user.email],
            body=f"""
            Hello {user.username},

            Your access token (ID: {token.id}) will expire in 24 hours.

            Duration: {token.duration_hours} hours
            Expires at: {token.expires_at}

            Purchase a new token to continue using Zenzefi:
            {settings.FRONTEND_URL}/tokens/purchase

            Best regards,
            Zenzefi Team
            """,
            subtype="plain"
        )

        fm = FastMail(conf)
        await fm.send_message(message)

    @staticmethod
    async def send_balance_low(user: User):
        """Notify user that balance is low (< 10 ZNC)"""
        message = MessageSchema(
            subject="Low balance alert",
            recipients=[user.email],
            body=f"""
            Hello {user.username},

            Your balance is low: {user.currency_balance} ZNC

            Top up your balance to continue purchasing tokens:
            {settings.FRONTEND_URL}/currency/purchase

            Best regards,
            Zenzefi Team
            """,
            subtype="plain"
        )

        fm = FastMail(conf)
        await fm.send_message(message)

    @staticmethod
    async def send_referral_bonus(user: User, bonus_amount: Decimal):
        """Notify user about referral bonus earned"""
        message = MessageSchema(
            subject="You earned a referral bonus!",
            recipients=[user.email],
            body=f"""
            Hello {user.username},

            Congratulations! You earned a referral bonus of {bonus_amount} ZNC.

            Your new balance: {user.currency_balance} ZNC

            Keep sharing your referral code: {user.referral_code}

            Best regards,
            Zenzefi Team
            """,
            subtype="plain"
        )

        fm = FastMail(conf)
        await fm.send_message(message)
```

#### Background Notification Tasks

```python
# app/core/notification_scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def check_expiring_tokens():
    """Check for tokens expiring in 24 hours"""
    db = next(get_db())
    now = datetime.now(timezone.utc)
    threshold = now + timedelta(hours=24)

    expiring_tokens = db.query(AccessToken).join(User).filter(
        AccessToken.is_active == True,
        AccessToken.expires_at <= threshold,
        AccessToken.expires_at > now
    ).all()

    for token in expiring_tokens:
        await EmailService.send_token_expiring_soon(token.user, token)

    db.close()

async def check_low_balance():
    """Check for users with low balance"""
    db = next(get_db())

    low_balance_users = db.query(User).filter(
        User.currency_balance < Decimal("10.00"),
        User.is_active == True
    ).all()

    for user in low_balance_users:
        await EmailService.send_balance_low(user)

    db.close()

# Schedule tasks
scheduler.add_job(check_expiring_tokens, "interval", hours=6)  # Every 6 hours
scheduler.add_job(check_low_balance, "interval", hours=12)  # Every 12 hours
```

---

### 2. Webhook Notifications

#### WebhookEndpoint Model

```python
# app/models/webhook.py
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID

class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    url = Column(String, nullable=False)
    events = Column(ARRAY(String), nullable=False)  # ["token.expired", "balance.low", "referral.bonus"]
    secret = Column(String, nullable=False)  # HMAC secret for signature verification
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))

    # Relationships
    user = relationship("User")
```

#### Webhook Service

```python
# app/services/webhook_service.py
import httpx
import hmac
import hashlib
import json

class WebhookService:

    @staticmethod
    async def trigger_webhook(event_type: str, payload: dict, user_id: UUID, db: Session):
        """Trigger webhook for specific event"""
        webhooks = db.query(WebhookEndpoint).filter(
            WebhookEndpoint.user_id == user_id,
            WebhookEndpoint.is_active == True,
            WebhookEndpoint.events.contains([event_type])
        ).all()

        for webhook in webhooks:
            # Prepare payload
            webhook_payload = {
                "event": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": payload
            }

            # Generate signature
            body = json.dumps(webhook_payload)
            signature = hmac.new(
                webhook.secret.encode(),
                body.encode(),
                hashlib.sha256
            ).hexdigest()

            # Send webhook
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        webhook.url,
                        json=webhook_payload,
                        headers={
                            "X-Webhook-Signature": signature,
                            "Content-Type": "application/json"
                        }
                    )

                    if response.status_code != 200:
                        logger.warning(f"Webhook failed: {webhook.url}, status={response.status_code}")

            except Exception as e:
                logger.error(f"Webhook error: {webhook.url}, error={str(e)}")
```

#### Webhook Management Endpoints

```python
# app/api/v1/webhooks.py
@router.post("/")
async def create_webhook(
    request: WebhookCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create webhook endpoint"""
    secret = secrets.token_urlsafe(32)

    webhook = WebhookEndpoint(
        user_id=current_user.id,
        url=request.url,
        events=request.events,
        secret=secret
    )

    db.add(webhook)
    db.commit()

    return {
        "webhook_id": str(webhook.id),
        "secret": secret,  # Return once, user should store securely
        "url": webhook.url,
        "events": webhook.events
    }

@router.get("/")
async def list_webhooks(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List user's webhooks"""
    webhooks = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.user_id == current_user.id
    ).all()

    return {"items": [WebhookResponse.from_orm(w) for w in webhooks]}
```

---

## Этап 4.6: Prometheus Metrics

**Зависимости:** Этапы 3-4 завершены (ProxySession tracking, health checks)
**Время:** 2-3 дня
**Цель:** Реал-тайм метрики, алертинг, capacity planning

### 1. Зачем нужен Prometheus?

**Prometheus** - open-source система мониторинга и алертинга для сбора метрик в виде временных рядов.

#### Ключевые преимущества:

1. **Проактивный мониторинг** - обнаружение проблем ДО жалоб пользователей
2. **Быстрая диагностика** - понимание причины проблемы за секунды
3. **Автоматические алерты** - уведомления в Telegram/Email
4. **Capacity planning** - планирование масштабирования на основе трендов
5. **Business insights** - понимание монетизации и поведения пользователей

#### Дополняет существующие компоненты Phase 3:

| Компонент | Хранилище | Назначение |
|-----------|-----------|------------|
| ProxySession | PostgreSQL | Детальная история сессий |
| AuditLog | PostgreSQL | Audit trail для compliance |
| Health Checks | Redis cache | Статус сервисов (PostgreSQL, Redis, Zenzefi) |
| **Prometheus** | Time-series DB | **Реал-тайм метрики, тренды, алерты** |

---

### 2. Метрики для Zenzefi Backend

```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Summary

# HTTP метрики (автоматически через Instrumentator)
# - http_requests_total
# - http_request_duration_seconds

# Token метрики
token_validations_total = Counter(
    "token_validations_total",
    "Total token validation attempts",
    ["status"]  # success, cache_hit, cache_miss, invalid
)

token_cache_hit_rate = Gauge(
    "token_cache_hit_rate",
    "Redis cache hit rate for token validation"
)

active_tokens_gauge = Gauge(
    "active_tokens_gauge",
    "Current number of active tokens"
)

# Proxy метрики
proxy_requests_total = Counter(
    "proxy_requests_total",
    "Total proxy requests to Zenzefi",
    ["method", "path", "status_code"]
)

proxy_latency = Histogram(
    "proxy_request_duration_seconds",
    "Proxy request latency to Zenzefi",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

proxy_bytes_transferred = Counter(
    "proxy_bytes_transferred_total",
    "Total bytes transferred through proxy",
    ["direction"]  # request, response
)

# Currency метрики
znc_balance_changes = Counter(
    "znc_balance_changes_total",
    "Total ZNC balance changes",
    ["operation"]  # deposit, purchase, refund
)

token_purchases = Counter(
    "token_purchases_total",
    "Total token purchases",
    ["duration_hours"]  # 1, 12, 24, 168, 720
)

znc_revenue_total = Counter(
    "znc_revenue_total",
    "Total revenue in ZNC"
)

# Session метрики
active_sessions = Gauge(
    "active_proxy_sessions",
    "Current number of active proxy sessions"
)

# Database метрики
db_query_duration = Histogram(
    "db_query_duration_seconds",
    "Database query duration",
    ["operation"]  # select, insert, update, delete
)

db_connection_pool_usage = Gauge(
    "db_connection_pool_usage",
    "PostgreSQL connection pool usage"
)
```

---

### 3. Интеграция в код

#### app/main.py

```python
from prometheus_client import make_asgi_app
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

# Prometheus endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Auto-instrument FastAPI
Instrumentator().instrument(app).expose(app)

# Background task для gauge метрик
@app.on_event("startup")
async def update_metrics():
    scheduler.add_job(
        update_gauge_metrics,
        trigger="interval",
        seconds=30,
        id="metrics_update"
    )

async def update_gauge_metrics():
    """Обновляет gauge метрики"""
    db = next(get_db())

    # Active tokens
    count = db.query(AccessToken).filter(
        AccessToken.is_active == True
    ).count()
    active_tokens_gauge.set(count)

    # Active sessions
    count = db.query(ProxySession).filter(
        ProxySession.is_active == True
    ).count()
    active_sessions.set(count)

    db.close()
```

#### app/services/token_service.py

```python
@staticmethod
def validate_token(token: str, db: Session) -> dict:
    # Redis cache check
    cached = redis_client.get(f"active_token:{sha256_hash}")
    if cached:
        token_validations_total.labels(status="cache_hit").inc()
        return json.loads(cached)

    # PostgreSQL fallback
    token_validations_total.labels(status="cache_miss").inc()
    token_obj = db.query(AccessToken).filter(...).first()

    if not token_obj or not token_obj.is_active:
        token_validations_total.labels(status="invalid").inc()
        raise HTTPException(...)

    token_validations_total.labels(status="success").inc()
    return token_data
```

#### app/api/v1/proxy.py

```python
@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_request(request: Request):
    start_time = time.time()

    # ... existing proxy logic

    # Metrics
    proxy_requests_total.labels(
        method=request.method,
        path=path,
        status_code=response.status_code
    ).inc()

    latency = time.time() - start_time
    proxy_latency.observe(latency)

    proxy_bytes_transferred.labels(direction="request").inc(len(await request.body()))
    proxy_bytes_transferred.labels(direction="response").inc(len(response.content))

    return response
```

#### app/api/v1/tokens.py

```python
@router.post("/purchase")
async def purchase_token(request: TokenPurchase):
    # ... existing purchase logic

    # Metrics
    token_purchases.labels(duration_hours=str(request.duration_hours)).inc()
    znc_balance_changes.labels(operation="purchase").inc()
    znc_revenue_total.inc(float(cost))

    return token
```

---

### 4. Alertmanager Configuration

```yaml
# alertmanager.yml
global:
  telegram_api_url: 'https://api.telegram.org'

route:
  receiver: 'telegram'
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 3h

receivers:
  - name: 'telegram'
    telegram_configs:
      - bot_token: 'YOUR_BOT_TOKEN'
        chat_id: YOUR_CHAT_ID
        parse_mode: 'HTML'
```

#### Примеры алертов (prometheus_alerts.yml):

```yaml
groups:
  - name: zenzefi_alerts
    interval: 30s
    rules:
      # Высокая latency проксирования
      - alert: HighProxyLatency
        expr: histogram_quantile(0.99, proxy_request_duration_seconds) > 2.0
        for: 5m
        annotations:
          summary: "Zenzefi proxy слишком медленный (p99 > 2s)"
          description: "p99 latency: {{ $value }}s"

      # Низкий cache hit rate
      - alert: LowCacheHitRate
        expr: rate(token_validations_total{status="cache_hit"}[5m]) / rate(token_validations_total[5m]) < 0.8
        for: 10m
        annotations:
          summary: "Redis кеш работает плохо (<80% hit rate)"

      # Zenzefi сервер недоступен
      - alert: ZenzefiServerDown
        expr: up{job="zenzefi-backend"} == 0
        for: 1m
        annotations:
          summary: "Zenzefi backend недоступен"

      # Высокий error rate
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "Высокий процент ошибок (>5%)"

      # Подозрительная активность баланса
      - alert: SuspiciousBalanceActivity
        expr: rate(znc_balance_changes_total[1h]) > 1000
        for: 5m
        annotations:
          summary: "Необычно высокая активность по балансу ZNC"
```

---

### 5. Deployment (Docker Compose)

```yaml
# docker-compose.yml - добавить сервисы
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus_alerts.yml:/etc/prometheus/alerts.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
      - '--web.enable-lifecycle'

  grafana:
    image: grafana/grafana:latest
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=redis-datasource

  alertmanager:
    image: prom/alertmanager:latest
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
    ports:
      - "9093:9093"
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'

volumes:
  prometheus_data:
  grafana_data:
```

#### prometheus.yml:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

rule_files:
  - '/etc/prometheus/alerts.yml'

scrape_configs:
  - job_name: 'zenzefi-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
```

---

### 6. Grafana Dashboards

**System Health Dashboard:**
- HTTP Request Rate (requests/min)
- Response Time (p50, p95, p99)
- Cache Hit Rate (%)
- Error Rate (%)
- Active Sessions
- Active Tokens

**Business Metrics Dashboard:**
- ZNC Revenue (24h, 7d, 30d)
- Token Purchases by Duration
- Active Users (DAU, MAU)
- Refund Rate (%)
- Average Token Lifetime

**Infrastructure Dashboard:**
- CPU Usage (%)
- Memory Usage (%)
- PostgreSQL Connection Pool
- Redis Memory Usage
- Disk Space

---

### 7. Dependencies

```toml
# pyproject.toml - добавить зависимости
[tool.poetry.dependencies]
prometheus-client = "^0.19.0"
prometheus-fastapi-instrumentator = "^6.1.0"
```

```bash
# Установка
poetry add prometheus-client prometheus-fastapi-instrumentator
```

---

### 8. Testing

```python
# tests/test_metrics.py
from prometheus_client import REGISTRY

def test_token_validation_metrics(client, test_user, test_db):
    """Test that token validation increments metrics"""
    # Get initial metric value
    initial = REGISTRY.get_sample_value(
        'token_validations_total',
        labels={'status': 'success'}
    )

    # Perform token validation
    token = create_test_token(test_user, test_db)
    validate_token(token.token, test_db)

    # Check metric incremented
    final = REGISTRY.get_sample_value(
        'token_validations_total',
        labels={'status': 'success'}
    )

    assert final == initial + 1

def test_proxy_latency_metric(client, test_token):
    """Test that proxy requests record latency"""
    response = client.get(
        "/api/v1/proxy/status",
        headers={"X-Access-Token": test_token.token}
    )

    # Check histogram recorded observation
    samples = REGISTRY.get_sample_value('proxy_request_duration_seconds_count')
    assert samples > 0
```

---

### 9. Migration Plan

**Week 1:**
- ✅ Установка зависимостей
- ✅ Настройка базовых метрик (HTTP, tokens, proxy)
- ✅ Интеграция в существующий код
- ✅ Тестирование метрик

**Week 2:**
- ✅ Deployment Prometheus + Grafana + Alertmanager
- ✅ Создание Grafana dashboards
- ✅ Настройка алертов
- ✅ Документация

---

## Roadmap Future Features

**Общее время:** 13-18 дней

| Этап | Время | Задачи |
|------|-------|--------|
| 2.5 - Token Bundles | 2 дня | Model, endpoints, purchase logic |
| 2.5 - Referrals | 2 дня | Model updates, bonus logic, stats |
| 3.5 - Analytics | 2-3 дня | User stats, admin stats, visualizations |
| 4.5 - Email Notifications | 2 дня | Email service, background tasks |
| 4.5 - Webhooks | 3 дня | Model, webhook service, management endpoints |
| **4.6 - Prometheus Metrics** | **2-3 дня** | **Metrics, Grafana dashboards, alerting** |

**Итого:** 13-16 дней

---

## Результат

После реализации всех future features:
- 💰 **Увеличение продаж** через пакетные предложения и реферальную программу
- 📊 **Прозрачность** для пользователей (usage analytics)
- 🔔 **Engagement** через уведомления о важных событиях
- 🔗 **Интеграция** с внешними системами через webhooks

---

**См. также:**
- [PHASE_1_MVP.md](./PHASE_1_MVP.md) - MVP (завершён)
- [PHASE_2_CURRENCY.md](./PHASE_2_CURRENCY.md) - Система валюты
- [PHASE_3_MONITORING.md](./PHASE_3_MONITORING.md) - Мониторинг
- [PHASE_4_PRODUCTION.md](./PHASE_4_PRODUCTION.md) - Production Readiness
- [BACKEND.md](../BACKEND.md) - Overview
