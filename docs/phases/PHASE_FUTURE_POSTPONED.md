# Phase Future: Postponed Features

**Статус:** 📋 ОТЛОЖЕНО
**Версия:** v0.7.0+ (будущие релизы)
**Причина:** Фичи отложены для фокуса на core monetization и UX improvements

---

## 📖 Содержание

- [Введение](#введение)
- [Token Auto-Renewal (Автопродление)](#token-auto-renewal-автопродление)
- [Token Gifting (Подарочные токены)](#token-gifting-подарочные-токены)
- [Sprint 3: Developer Ecosystem (v0.9.0-beta)](#sprint-3-developer-ecosystem-v090-beta)
  - [Webhook Notifications (Webhook интеграция)](#webhook-notifications-webhook-интеграция)
  - [Multi-Currency Support (Мультивалютность)](#multi-currency-support-мультивалютность)
  - [API Rate Limiting Tiers (Тарифные планы)](#api-rate-limiting-tiers-тарифные-планы)

---

## Введение

Этот документ содержит детальное описание **отложенных фич** для Zenzefi Backend, которые были запланированы, но временно отложены для фокуса на приоритетных задачах:

**Приоритетные фичи (Active Development):**
- ✅ Token Bundles (Пакетные предложения)
- ✅ Referral System (Реферальная программа)
- ✅ Usage Analytics (Аналитика использования)
- ✅ Email Notifications (Email уведомления)
- ✅ Prometheus Dashboards (Grafana мониторинг)

**Отложенные фичи (Postponed):**
- ⏸️ Token Auto-Renewal (Автопродление)
- ⏸️ Token Gifting (Подарочные токены)
- ⏸️ Webhook Notifications (Webhook интеграция)
- ⏸️ Multi-Currency Support (Мультивалютность)
- ⏸️ API Rate Limiting Tiers (Тарифные планы)

**Причины отложения:**
1. **Token Auto-Renewal** - Требует сложной фоновой обработки и email интеграции; можно добавить после стабилизации Email Notifications
2. **Token Gifting** - Социальная фича, полезная после роста user base; требует email интеграции
3. **Sprint 3 (Developer Ecosystem)** - Фичи для enterprise/B2B сегмента; приоритет на B2C monetization

**Когда будут реализованы:**
- Token Auto-Renewal: После успешного запуска Email Notifications (Sprint 2)
- Token Gifting: После роста user base до 500+ активных пользователей
- Sprint 3 фичи: После достижения v1.0.0 и стабилизации платформы

---

## Token Auto-Renewal (Автопродление)

### Бизнес-обоснование

**Проблема:** Пользователи забывают продлевать токены → churn. Одноразовые покупки вместо recurring revenue.

**Решение:** Subscription-like model с автоматическим продлением токенов.

**Механика:**
1. Пользователь включает auto-renewal в настройках (opt-in)
2. Выбирает duration для автопродления (1h, 12h, 24h, 7d, 30d)
3. Когда любой токен < 24 часа до истечения → автоматическая покупка нового
4. Если недостаточно баланса → email notification, auto-renewal pause

**Ценность:**
- **Recurring revenue**: Subscription модель вместо one-time purchases
- **Retention**: Пользователи не забывают продлять → lower churn
- **Convenience**: Set-and-forget experience → higher satisfaction
- **Predictable revenue**: Легче планировать cash flow

**Expected Impact:**
- Recurring revenue: +25-40% через auto-renewal users
- Retention: +20-30% (users don't forget to renew)
- LTV: +50-100% (subscription users stay longer)

---

### Технические детали

**Database Model Changes:**

```python
# app/models/user.py - добавить поля
class User(Base):
    # ... existing fields

    # Auto-renewal settings (NEW)
    auto_renew_enabled = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Enable auto-renewal of tokens"
    )

    auto_renew_duration_hours = Column(
        Integer,
        nullable=True,
        comment="Duration for auto-renewed tokens (1, 12, 24, 168, 720)"
    )

    auto_renew_scope = Column(
        String(50),
        default="full",
        nullable=True,
        comment="Scope for auto-renewed tokens (full or certificates_only)"
    )
```

---

**Service Layer:**

```python
# app/services/token_service.py - новый метод
from datetime import datetime, timedelta, timezone

class TokenService:

    AUTO_RENEWAL_THRESHOLD_HOURS = 24  # Renew when token < 24h remaining

    @staticmethod
    def check_and_renew_user_tokens(
        user_id: UUID,
        db: Session
    ) -> dict:
        """
        Проверка токенов пользователя и автопродление при необходимости.

        Logic:
            1. Если auto_renew_enabled = False → skip
            2. Найти все активные токены пользователя
            3. Для каждого токена с expires_at < (now + 24h) → создать новый
            4. Если недостаточно баланса → pause auto-renewal, send email

        Returns:
            {
                "renewed_count": int,
                "failed": bool,
                "failure_reason": str | None,
                "new_balance": float
            }
        """
        # Get user with lock
        user = db.query(User).filter(User.id == user_id).with_for_update().first()

        if not user or not user.auto_renew_enabled:
            return {"renewed_count": 0, "failed": False}

        # Check auto_renew_duration_hours configured
        if not user.auto_renew_duration_hours:
            return {"renewed_count": 0, "failed": True, "failure_reason": "Auto-renewal duration not configured"}

        # Find expiring tokens
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(hours=TokenService.AUTO_RENEWAL_THRESHOLD_HOURS)

        expiring_tokens = db.query(AccessToken).filter(
            AccessToken.user_id == user.id,
            AccessToken.is_active == True,
            AccessToken.activated_at.isnot(None)  # Only activated tokens
        ).all()

        # Filter tokens that expire within 24h
        tokens_to_renew = [
            t for t in expiring_tokens
            if t.expires_at and t.expires_at <= threshold
        ]

        if not tokens_to_renew:
            return {"renewed_count": 0, "failed": False}

        # Calculate cost
        cost_per_token = TokenService.calculate_token_cost(
            duration_hours=user.auto_renew_duration_hours
        )
        total_cost = cost_per_token * len(tokens_to_renew)

        # Check balance
        if user.currency_balance < total_cost:
            # Pause auto-renewal
            user.auto_renew_enabled = False
            db.commit()

            # Send email notification (будет реализовано в Sprint 2)
            # EmailService.send_auto_renewal_failed(user, total_cost)

            return {
                "renewed_count": 0,
                "failed": True,
                "failure_reason": f"Insufficient balance. Required: {total_cost} ZNC, Available: {user.currency_balance} ZNC"
            }

        # Deduct balance
        user.currency_balance -= total_cost

        # Create new tokens
        renewed_count = 0
        for old_token in tokens_to_renew:
            new_token = TokenService.generate_access_token(
                user_id=user.id,
                duration_hours=user.auto_renew_duration_hours,
                scope=user.auto_renew_scope or "full",
                db=db
            )
            renewed_count += 1

        # Create transaction
        transaction = Transaction(
            user_id=user.id,
            amount=-total_cost,
            transaction_type=TransactionType.PURCHASE,
            description=f"Auto-renewal: {renewed_count} tokens x {user.auto_renew_duration_hours}h"
        )
        db.add(transaction)

        # Award referral bonus (if user was referred)
        CurrencyService.award_referral_bonus(
            user_id=user.id,
            purchase_amount=total_cost,
            db=db
        )

        db.commit()
        db.refresh(user)

        # Send email notification (будет реализовано в Sprint 2)
        # EmailService.send_auto_renewal_success(user, renewed_count, total_cost)

        return {
            "renewed_count": renewed_count,
            "failed": False,
            "new_balance": float(user.currency_balance)
        }
```

---

**Background Task (APScheduler):**

```python
# app/core/renewal_scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.token_service import TokenService
from app.core.database import get_db
from app.models.user import User
import logging

logger = logging.getLogger(__name__)

async def check_all_users_for_renewal():
    """
    Background task: проверка всех пользователей с auto_renew_enabled.

    Scheduled: Daily at 00:00 UTC
    """
    db = next(get_db())

    try:
        # Find users with auto-renewal enabled
        users_to_check = db.query(User).filter(
            User.auto_renew_enabled == True,
            User.is_active == True
        ).all()

        logger.info(f"Checking {len(users_to_check)} users for auto-renewal")

        total_renewed = 0
        failed_count = 0

        for user in users_to_check:
            try:
                result = TokenService.check_and_renew_user_tokens(
                    user_id=user.id,
                    db=db
                )

                if result["renewed_count"] > 0:
                    total_renewed += result["renewed_count"]
                    logger.info(f"User {user.username}: Renewed {result['renewed_count']} tokens")

                if result["failed"]:
                    failed_count += 1
                    logger.warning(f"User {user.username}: Auto-renewal failed - {result.get('failure_reason')}")

            except Exception as e:
                logger.error(f"Error renewing tokens for user {user.username}: {str(e)}")
                failed_count += 1

        logger.info(f"Auto-renewal complete: {total_renewed} tokens renewed, {failed_count} failures")

    finally:
        db.close()

# Add to scheduler in app/main.py
def setup_renewal_scheduler(app: FastAPI):
    scheduler = AsyncIOScheduler()

    # Run daily at 00:00 UTC
    scheduler.add_job(
        check_all_users_for_renewal,
        trigger="cron",
        hour=0,
        minute=0,
        id="auto_renewal_check"
    )

    scheduler.start()

    @app.on_event("shutdown")
    async def shutdown_scheduler():
        scheduler.shutdown()
```

---

**API Endpoints:**

```python
# app/api/v1/users.py - новые endpoints
@router.put("/me/auto-renewal")
async def configure_auto_renewal(
    enabled: bool,
    duration_hours: int = None,
    scope: str = "full",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Настройка автопродления токенов.

    Body:
        {
            "enabled": true,
            "duration_hours": 24,  # Required if enabled=true
            "scope": "full"  # "full" or "certificates_only"
        }

    Validation:
        - duration_hours must be in [1, 12, 24, 168, 720]
        - scope must be "full" or "certificates_only"

    Returns:
        {
            "auto_renew_enabled": true,
            "auto_renew_duration_hours": 24,
            "auto_renew_scope": "full",
            "cost_per_renewal": 18.00
        }
    """
    # Validation
    if enabled and not duration_hours:
        raise HTTPException(status_code=400, detail="duration_hours required when enabling auto-renewal")

    if enabled and duration_hours not in [1, 12, 24, 168, 720]:
        raise HTTPException(status_code=400, detail="Invalid duration_hours. Must be 1, 12, 24, 168, or 720")

    if scope not in ["full", "certificates_only"]:
        raise HTTPException(status_code=400, detail="Invalid scope. Must be 'full' or 'certificates_only'")

    # Update user
    current_user.auto_renew_enabled = enabled
    current_user.auto_renew_duration_hours = duration_hours if enabled else None
    current_user.auto_renew_scope = scope if enabled else None

    db.commit()
    db.refresh(current_user)

    # Calculate cost
    cost_per_renewal = 0.0
    if enabled:
        cost_per_renewal = float(TokenService.calculate_token_cost(duration_hours))

    return {
        "auto_renew_enabled": current_user.auto_renew_enabled,
        "auto_renew_duration_hours": current_user.auto_renew_duration_hours,
        "auto_renew_scope": current_user.auto_renew_scope,
        "cost_per_renewal": cost_per_renewal
    }

@router.get("/me/auto-renewal")
async def get_auto_renewal_config(
    current_user: User = Depends(get_current_active_user)
):
    """
    Получить текущие настройки автопродления.
    """
    cost_per_renewal = 0.0
    if current_user.auto_renew_enabled:
        cost_per_renewal = float(TokenService.calculate_token_cost(
            current_user.auto_renew_duration_hours
        ))

    return {
        "auto_renew_enabled": current_user.auto_renew_enabled,
        "auto_renew_duration_hours": current_user.auto_renew_duration_hours,
        "auto_renew_scope": current_user.auto_renew_scope,
        "cost_per_renewal": cost_per_renewal
    }
```

---

**Database Migration:**

```python
# alembic/versions/xxx_add_auto_renewal.py
"""add auto renewal

Revision ID: xxx
Revises: yyy
Create Date: 2025-XX-XX

"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add auto-renewal fields to users table
    op.add_column('users', sa.Column('auto_renew_enabled', sa.Boolean, nullable=False, server_default='false'))
    op.add_column('users', sa.Column('auto_renew_duration_hours', sa.Integer, nullable=True))
    op.add_column('users', sa.Column('auto_renew_scope', sa.String(50), nullable=True, server_default='full'))

def downgrade():
    op.drop_column('users', 'auto_renew_scope')
    op.drop_column('users', 'auto_renew_duration_hours')
    op.drop_column('users', 'auto_renew_enabled')
```

---

**Testing Plan:**

```python
# tests/test_auto_renewal.py

def test_configure_auto_renewal(test_db, test_user):
    """Тест настройки auto-renewal"""
    # Enable auto-renewal
    test_user.auto_renew_enabled = True
    test_user.auto_renew_duration_hours = 24
    test_user.auto_renew_scope = "full"
    test_db.commit()

    assert test_user.auto_renew_enabled == True
    assert test_user.auto_renew_duration_hours == 24

def test_auto_renew_expiring_tokens(test_db, test_user):
    """Тест автопродления истекающих токенов"""
    # Setup: user with auto-renewal и достаточным балансом
    test_user.auto_renew_enabled = True
    test_user.auto_renew_duration_hours = 24
    test_user.currency_balance = Decimal("100.00")
    test_db.commit()

    # Create expiring token (activated 23 hours ago)
    token = AccessToken(
        user_id=test_user.id,
        token=secrets.token_urlsafe(48),
        duration_hours=24,
        activated_at=datetime.now(timezone.utc) - timedelta(hours=23)
    )
    test_db.add(token)
    test_db.commit()

    # Run renewal check
    result = TokenService.check_and_renew_user_tokens(
        user_id=test_user.id,
        db=test_db
    )

    # Assertions
    assert result["renewed_count"] == 1
    assert result["failed"] == False
    test_db.refresh(test_user)
    assert test_user.currency_balance == Decimal("82.00")  # 100 - 18

def test_auto_renew_insufficient_balance(test_db, test_user):
    """Тест auto-renewal с недостаточным балансом"""
    # Setup: user with low balance
    test_user.auto_renew_enabled = True
    test_user.auto_renew_duration_hours = 24
    test_user.currency_balance = Decimal("5.00")  # Not enough for 24h token (18 ZNC)
    test_db.commit()

    # Create expiring token
    token = AccessToken(
        user_id=test_user.id,
        token=secrets.token_urlsafe(48),
        duration_hours=24,
        activated_at=datetime.now(timezone.utc) - timedelta(hours=23)
    )
    test_db.add(token)
    test_db.commit()

    # Run renewal check
    result = TokenService.check_and_renew_user_tokens(
        user_id=test_user.id,
        db=test_db
    )

    # Assertions
    assert result["renewed_count"] == 0
    assert result["failed"] == True
    assert "Insufficient balance" in result["failure_reason"]

    # Auto-renewal should be disabled
    test_db.refresh(test_user)
    assert test_user.auto_renew_enabled == False

def test_auto_renew_multiple_tokens(test_db, test_user):
    """Тест auto-renewal нескольких токенов одновременно"""
    test_user.auto_renew_enabled = True
    test_user.auto_renew_duration_hours = 24
    test_user.currency_balance = Decimal("200.00")
    test_db.commit()

    # Create 3 expiring tokens
    for i in range(3):
        token = AccessToken(
            user_id=test_user.id,
            token=secrets.token_urlsafe(48),
            duration_hours=24,
            activated_at=datetime.now(timezone.utc) - timedelta(hours=23)
        )
        test_db.add(token)
    test_db.commit()

    # Run renewal
    result = TokenService.check_and_renew_user_tokens(
        user_id=test_user.id,
        db=test_db
    )

    # Assertions
    assert result["renewed_count"] == 3
    test_db.refresh(test_user)
    assert test_user.currency_balance == Decimal("146.00")  # 200 - (18 * 3)
```

---

**Security Considerations:**

- ✅ **Opt-in by default** - auto_renew_enabled = False
- ✅ **Balance validation** перед каждым renewal
- ✅ **Auto-pause** при insufficient balance (не бесконечные попытки)
- ✅ **Email notifications** при success/failure (Sprint 2)
- ✅ **Row-level locking** для balance updates
- ✅ **Audit logging** всех auto-renewal операций

---

**User Experience Considerations:**

1. **Email reminders** (Sprint 2):
   - 3 дня до auto-renewal: "Your token will auto-renew in 3 days"
   - Immediately after renewal: "Your token was auto-renewed"
   - On failure: "Auto-renewal failed due to insufficient balance"

2. **Dashboard indicator**:
   - Show "Auto-Renewal Active" badge в UI
   - Display next renewal date и cost

3. **Easy disable**:
   - One-click toggle в settings
   - No penalty for disabling

---

**Performance Impact:**

- **Daily background task**: <1 minute для 10,000 users
- **Batch processing**: Можно оптимизировать с bulk inserts
- **Database load**: Low (runs once per day, off-peak hours)

---

## Token Gifting (Подарочные токены)

### Бизнес-обоснование

**Проблема:** Нет механизма привлечения через social sharing. Пользователи не могут поделиться опытом с друзьями.

**Решение:** Возможность подарить токен другому пользователю (by email).

**Механика:**
1. User A покупает токен
2. User A отправляет gift другому пользователю (email)
3. Email notification с access token
4. Recipient активирует токен

**Ценность:**
- **Viral growth**: Social sharing механизм
- **Trial experience**: Новые пользователи получают free trial
- **Revenue**: Gifting требует покупки токена

**Expected Impact:**
- User acquisition: +10-20% через gifted tokens
- Conversion: 30-40% gift recipients становятся paying users

---

### Технические детали

**Database Model Changes:**

```python
# app/models/token.py - добавить поля
class AccessToken(Base):
    # ... existing fields

    gifted_to_email = Column(
        String,
        nullable=True,
        comment="Email recipient (if gift)"
    )

    gifted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when token was gifted"
    )
```

---

**API Endpoints:**

```python
# app/api/v1/tokens.py - новый endpoint
@router.post("/{token_id}/gift")
async def gift_token(
    token_id: UUID,
    recipient_email: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Подарить токен другому пользователю по email.

    Requirements:
        - Token must belong to current user
        - Token must not be activated yet
        - Token cannot be already gifted

    Body:
        {
            "recipient_email": "friend@example.com"
        }

    Returns:
        {
            "message": "Token gifted to friend@example.com",
            "token_id": "uuid",
            "recipient_email": "friend@example.com",
            "gifted_at": "ISO timestamp"
        }

    Errors:
        404: Token not found
        400: Token already activated/gifted
    """
    # Get token
    token = db.query(AccessToken).filter(
        AccessToken.id == token_id,
        AccessToken.user_id == current_user.id
    ).first()

    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    if token.activated_at:
        raise HTTPException(status_code=400, detail="Token already activated")

    if token.gifted_at:
        raise HTTPException(status_code=400, detail="Token already gifted")

    # Validate email format
    if not re.match(r"[^@]+@[^@]+\.[^@]+", recipient_email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    # Mark as gifted
    token.gifted_to_email = recipient_email
    token.gifted_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(token)

    # Send email notification
    await EmailService.send_gift_token(
        sender=current_user,
        recipient_email=recipient_email,
        token=token
    )

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        action="token_gifted",
        resource_type="access_token",
        resource_id=str(token.id),
        details={
            "recipient_email": recipient_email,
            "token_duration": token.duration_hours,
            "token_scope": token.scope
        }
    )
    db.add(audit_log)
    db.commit()

    return {
        "message": f"Token gifted to {recipient_email}",
        "token_id": str(token.id),
        "recipient_email": recipient_email,
        "gifted_at": token.gifted_at.isoformat()
    }
```

---

**Email Template:**

```python
# app/services/email_service.py
class EmailService:

    @staticmethod
    async def send_gift_token(sender: User, recipient_email: str, token: AccessToken):
        """
        Send email notification with gifted token.
        """
        message = MessageSchema(
            subject=f"{sender.username} sent you a Zenzefi access token!",
            recipients=[recipient_email],
            body=f"""
            Hello!

            {sender.username} ({sender.email}) has gifted you a Zenzefi access token:

            Token: {token.token}
            Duration: {token.duration_hours} hours
            Scope: {token.scope}

            To use this token:
            1. Download Zenzefi Desktop Client: {settings.FRONTEND_URL}/downloads
            2. Register an account (or login if you already have one)
            3. Activate this token in the client

            The token will expire {token.duration_hours} hours after activation.

            Enjoy your Zenzefi experience!

            Best regards,
            Zenzefi Team
            """,
            subtype="plain"
        )
        await FastMail(conf).send_message(message)
```

---

**Database Migration:**

```python
# alembic/versions/xxx_add_token_gifting.py
"""add token gifting

Revision ID: xxx
Revises: yyy
Create Date: 2025-XX-XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # Add gifting fields to access_tokens table
    op.add_column('access_tokens', sa.Column('gifted_to_email', sa.String, nullable=True))
    op.add_column('access_tokens', sa.Column('gifted_at', sa.DateTime(timezone=True), nullable=True))

    # Create index for gifted tokens lookup
    op.create_index('ix_access_tokens_gifted_to_email', 'access_tokens', ['gifted_to_email'])

def downgrade():
    op.drop_index('ix_access_tokens_gifted_to_email', 'access_tokens')
    op.drop_column('access_tokens', 'gifted_at')
    op.drop_column('access_tokens', 'gifted_to_email')
```

---

**Testing Plan:**

```python
# tests/test_token_gifting.py

def test_gift_token_success(test_db, test_user, client):
    """Тест успешного gifting токена"""
    # Create token
    token = AccessToken(
        user_id=test_user.id,
        token=secrets.token_urlsafe(48),
        duration_hours=24,
        scope="full"
    )
    test_db.add(token)
    test_db.commit()

    # Get JWT
    jwt_token = create_test_jwt_token(test_user)

    # Gift token
    response = client.post(
        f"/api/v1/tokens/{token.id}/gift",
        json={"recipient_email": "friend@example.com"},
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recipient_email"] == "friend@example.com"
    assert "gifted_at" in data

    # Verify database
    test_db.refresh(token)
    assert token.gifted_to_email == "friend@example.com"
    assert token.gifted_at is not None

def test_gift_activated_token(test_db, test_user, client):
    """Тест: нельзя подарить активированный токен"""
    # Create activated token
    token = AccessToken(
        user_id=test_user.id,
        token=secrets.token_urlsafe(48),
        duration_hours=24,
        activated_at=datetime.now(timezone.utc)
    )
    test_db.add(token)
    test_db.commit()

    jwt_token = create_test_jwt_token(test_user)

    # Try to gift
    response = client.post(
        f"/api/v1/tokens/{token.id}/gift",
        json={"recipient_email": "friend@example.com"},
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert response.status_code == 400
    assert "already activated" in response.json()["detail"]

def test_gift_already_gifted_token(test_db, test_user, client):
    """Тест: нельзя подарить уже подаренный токен"""
    # Create gifted token
    token = AccessToken(
        user_id=test_user.id,
        token=secrets.token_urlsafe(48),
        duration_hours=24,
        gifted_to_email="first@example.com",
        gifted_at=datetime.now(timezone.utc)
    )
    test_db.add(token)
    test_db.commit()

    jwt_token = create_test_jwt_token(test_user)

    # Try to gift again
    response = client.post(
        f"/api/v1/tokens/{token.id}/gift",
        json={"recipient_email": "second@example.com"},
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert response.status_code == 400
    assert "already gifted" in response.json()["detail"]

def test_gift_someone_elses_token(test_db, test_user, other_user, client):
    """Тест: нельзя подарить чужой токен"""
    # Create token belonging to other_user
    token = AccessToken(
        user_id=other_user.id,
        token=secrets.token_urlsafe(48),
        duration_hours=24
    )
    test_db.add(token)
    test_db.commit()

    jwt_token = create_test_jwt_token(test_user)

    # Try to gift
    response = client.post(
        f"/api/v1/tokens/{token.id}/gift",
        json={"recipient_email": "friend@example.com"},
        headers={"Authorization": f"Bearer {jwt_token}"}
    )

    assert response.status_code == 404
```

---

**Security Considerations:**

- ✅ **Ownership validation** - только владелец может подарить токен
- ✅ **State validation** - нельзя подарить активированный или уже подаренный токен
- ✅ **Email validation** - проверка формата email
- ✅ **Audit logging** - все gifting операции логируются
- ✅ **No duplicate gifts** - один токен можно подарить только один раз
- ✅ **Email verification** - опционально: verify recipient email before accepting gift

---

**Anti-Abuse Measures:**

1. **Rate limiting**: Max 10 gifts per day per user
2. **Minimum balance requirement**: User must have >50 ZNC to gift
3. **Token value limit**: Cannot gift tokens >24 hours duration without admin approval
4. **Audit monitoring**: Admin dashboard для tracking suspicious gifting patterns

---

## Sprint 3: Developer Ecosystem (v0.9.0-beta)

**Длительность:** 8-10 дней
**Цель:** Расширить платформу для enterprise/developer use cases
**Expected ROI:** +30-50% B2B revenue growth

**Фичи:**
- Webhook Notifications (Webhook интеграция)
- Multi-Currency Support (Мультивалютность)
- API Rate Limiting Tiers (Тарифные планы)

**Статус:** 📋 Отложено - Приоритет на B2C monetization

---

### Webhook Notifications (Webhook интеграция)

#### Бизнес-обоснование

**Проблема:** B2B клиенты хотят интегрировать Zenzefi в свои системы. Нет программатического доступа к событиям платформы.

**Решение:** Webhook notifications для критических событий (token purchased, balance charged, session started).

**Ценность:**
- **B2B integration**: Позволяет корпоративным клиентам автоматизировать workflows
- **Real-time updates**: Instant notifications вместо polling API
- **Developer-friendly**: Standard webhook format (JSON POST)

**Expected Impact:**
- B2B revenue: +30-50% (enterprise customers pay premium for webhooks)
- API usage: -40-60% (webhooks вместо polling)

---

#### Технические детали

**Database Model:**

```python
# app/models/webhook.py
class WebhookEndpoint(Base):
    """
    User-defined webhook endpoint для получения event notifications.
    """
    __tablename__ = "webhook_endpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Webhook configuration
    url = Column(String(500), nullable=False, comment="HTTPS URL для webhook delivery")
    secret = Column(String(64), nullable=False, comment="HMAC secret для signature verification")

    # Event subscriptions (JSON array)
    events = Column(JSONB, nullable=False, comment="List of subscribed events")

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    failed_deliveries = Column(Integer, default=0, nullable=False)
    last_delivery_at = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="webhooks")


class WebhookDelivery(Base):
    """
    Log of webhook delivery attempts (for debugging and retry).
    """
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id = Column(UUID(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False)

    # Event details
    event_type = Column(String(50), nullable=False, comment="Event type (e.g., 'token.purchased')")
    payload = Column(JSONB, nullable=False, comment="Event payload (JSON)")

    # Delivery status
    status = Column(String(20), nullable=False, comment="pending, success, failed")
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    # Timing
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    webhook = relationship("WebhookEndpoint", backref="deliveries")
```

---

**Service Layer:**

```python
# app/services/webhook_service.py
import hmac
import hashlib
import httpx
from typing import Dict, Any

class WebhookService:

    EVENT_TYPES = [
        "token.purchased",
        "token.activated",
        "token.revoked",
        "balance.charged",
        "balance.topped_up",
        "session.started",
        "session.ended"
    ]

    @staticmethod
    async def trigger_event(
        user_id: UUID,
        event_type: str,
        payload: Dict[Any, Any],
        db: Session
    ):
        """
        Trigger webhook event for user's subscribed endpoints.

        Args:
            user_id: User who triggered the event
            event_type: Event type (e.g., "token.purchased")
            payload: Event data
            db: Database session
        """
        # Find user's active webhooks subscribed to this event
        webhooks = db.query(WebhookEndpoint).filter(
            WebhookEndpoint.user_id == user_id,
            WebhookEndpoint.is_active == True,
            WebhookEndpoint.events.contains([event_type])  # PostgreSQL JSONB contains
        ).all()

        for webhook in webhooks:
            # Create delivery record
            delivery = WebhookDelivery(
                webhook_id=webhook.id,
                event_type=event_type,
                payload=payload,
                status="pending"
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            # Deliver asynchronously
            await WebhookService.deliver_webhook(webhook, delivery, payload, db)

    @staticmethod
    async def deliver_webhook(
        webhook: WebhookEndpoint,
        delivery: WebhookDelivery,
        payload: Dict[Any, Any],
        db: Session
    ):
        """
        Deliver webhook to endpoint with HMAC signature.
        """
        # Generate HMAC signature
        signature = WebhookService.generate_signature(
            secret=webhook.secret,
            payload=payload
        )

        # Prepare request
        headers = {
            "Content-Type": "application/json",
            "X-Zenzefi-Signature": signature,
            "X-Zenzefi-Event": delivery.event_type,
            "X-Zenzefi-Delivery-ID": str(delivery.id)
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook.url,
                    json=payload,
                    headers=headers
                )

            # Update delivery record
            delivery.status = "success" if response.status_code == 200 else "failed"
            delivery.response_code = response.status_code
            delivery.response_body = response.text[:1000]  # Truncate
            delivery.delivered_at = datetime.now(timezone.utc)

            # Update webhook stats
            webhook.last_delivery_at = datetime.now(timezone.utc)
            if response.status_code != 200:
                webhook.failed_deliveries += 1

                # Disable webhook after 10 consecutive failures
                if webhook.failed_deliveries >= 10:
                    webhook.is_active = False

        except Exception as e:
            delivery.status = "failed"
            delivery.error_message = str(e)
            webhook.failed_deliveries += 1

        db.commit()

    @staticmethod
    def generate_signature(secret: str, payload: Dict[Any, Any]) -> str:
        """
        Generate HMAC-SHA256 signature for webhook payload.
        """
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        return signature

    @staticmethod
    def verify_signature(secret: str, payload: Dict[Any, Any], signature: str) -> bool:
        """
        Verify HMAC signature from webhook request.
        """
        expected_signature = WebhookService.generate_signature(secret, payload)
        return hmac.compare_digest(expected_signature, signature)
```

---

**API Endpoints:**

```python
# app/api/v1/webhooks.py
@router.post("/")
async def create_webhook(
    url: str,
    events: List[str],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create webhook endpoint.

    Body:
        {
            "url": "https://example.com/webhooks/zenzefi",
            "events": ["token.purchased", "balance.charged"]
        }

    Returns:
        {
            "id": "uuid",
            "url": "https://...",
            "secret": "generated_secret",  # SAVE THIS - shown only once
            "events": ["token.purchased", "balance.charged"],
            "is_active": true
        }
    """
    # Validate URL (must be HTTPS)
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Webhook URL must use HTTPS")

    # Validate events
    invalid_events = [e for e in events if e not in WebhookService.EVENT_TYPES]
    if invalid_events:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid events: {invalid_events}. Valid: {WebhookService.EVENT_TYPES}"
        )

    # Generate secret
    secret = secrets.token_urlsafe(48)

    # Create webhook
    webhook = WebhookEndpoint(
        user_id=current_user.id,
        url=url,
        secret=secret,
        events=events
    )
    db.add(webhook)
    db.commit()
    db.refresh(webhook)

    return {
        "id": str(webhook.id),
        "url": webhook.url,
        "secret": secret,  # IMPORTANT: Show only on creation
        "events": webhook.events,
        "is_active": webhook.is_active,
        "created_at": webhook.created_at.isoformat()
    }

@router.get("/")
async def list_webhooks(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List user's webhooks (secret не показывается).
    """
    webhooks = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.user_id == current_user.id
    ).all()

    return {
        "items": [
            {
                "id": str(w.id),
                "url": w.url,
                "events": w.events,
                "is_active": w.is_active,
                "failed_deliveries": w.failed_deliveries,
                "last_delivery_at": w.last_delivery_at.isoformat() if w.last_delivery_at else None,
                "created_at": w.created_at.isoformat()
            }
            for w in webhooks
        ]
    }

@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete webhook endpoint.
    """
    webhook = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.user_id == current_user.id
    ).first()

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    db.delete(webhook)
    db.commit()

    return {"message": "Webhook deleted"}

@router.get("/{webhook_id}/deliveries")
async def get_webhook_deliveries(
    webhook_id: UUID,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get webhook delivery history (for debugging).
    """
    webhook = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.user_id == current_user.id
    ).first()

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    deliveries = db.query(WebhookDelivery).filter(
        WebhookDelivery.webhook_id == webhook_id
    ).order_by(WebhookDelivery.created_at.desc()).limit(limit).all()

    return {
        "items": [
            {
                "id": str(d.id),
                "event_type": d.event_type,
                "status": d.status,
                "response_code": d.response_code,
                "error_message": d.error_message,
                "created_at": d.created_at.isoformat(),
                "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None
            }
            for d in deliveries
        ]
    }
```

---

**Integration Example:**

```python
# app/services/token_service.py - добавить webhook trigger
async def purchase_token(user_id: UUID, duration_hours: int, db: Session):
    # ... existing token purchase logic

    # Trigger webhook event
    await WebhookService.trigger_event(
        user_id=user.id,
        event_type="token.purchased",
        payload={
            "token_id": str(token.id),
            "duration_hours": duration_hours,
            "cost_znc": float(cost),
            "balance_remaining": float(user.currency_balance),
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        db=db
    )
```

---

### Multi-Currency Support (Мультивалютность)

#### Бизнес-обоснование

**Проблема:** ZNC (internal currency) удобна, но пользователи из разных стран хотят видеть цены в своей валюте (USD, EUR, RUB).

**Решение:** Поддержка multiple currencies с автоматической конвертацией при top-up.

**Expected Impact:**
- Conversion rate: +15-25% (локализованные цены)
- Global expansion: Easier market entry

---

### API Rate Limiting Tiers (Тарифные планы)

#### Бизнес-обоснование

**Проблема:** Все пользователи имеют одинаковые лимиты (100 req/min). Enterprise клиенты нуждаются в higher limits.

**Решение:** Tier-based rate limiting (Free, Pro, Enterprise).

**Tiers:**
- Free: 100 req/min
- Pro: 500 req/min (+10 ZNC/month)
- Enterprise: 2000 req/min (+50 ZNC/month)

**Expected Impact:**
- B2B revenue: +40-60% (subscription fees)
- Premium users: 10-15% upgrade rate

---

## Roadmap для Postponed Features

**Short-term (After v0.8.0):**
- ✅ Stabilize Email Notifications (Sprint 2)
- ✅ Monitor user engagement metrics

**Mid-term (v0.9.0-v1.0.0):**
- ⏸️ Token Auto-Renewal (после Email Notifications)
- ⏸️ Token Gifting (после роста user base >500 активных)

**Long-term (v1.1.0+):**
- ⏸️ Sprint 3 фичи (B2B/Enterprise focus)
- ⏸️ Webhook Notifications
- ⏸️ Multi-Currency Support
- ⏸️ API Rate Limiting Tiers

**Success Metrics для разблокировки:**
- Token Auto-Renewal: Email delivery rate >95%, bounce rate <5%
- Token Gifting: MAU >500, retention rate >40%
- Sprint 3: B2B leads >10, enterprise inquiries >3

---

## Заключение

Эти фичи **отложены, но не отменены**. Они будут реализованы после достижения следующих milestones:

1. **Phase 5-6 (v0.7.0-v0.8.0)** успешно развернуты в production
2. **User base** вырос до 500+ активных пользователей
3. **Email infrastructure** стабильна и надежна
4. **B2B demand** подтвержден (>10 enterprise inquiries)

**Next Steps:**
- Фокус на Token Bundles + Referral System (Sprint 1)
- Реализация Usage Analytics + Email Notifications (Sprint 2)
- Мониторинг метрик для оценки готовности к postponed features

**См. также:**
- [ROADMAP_V1.md](./ROADMAP_V1.md) - Обновленный roadmap без postponed features
- [PHASE_FUTURE_DETAILED.md](./PHASE_FUTURE_DETAILED.md) - Активный план развития (v0.7.0-v0.8.0)
