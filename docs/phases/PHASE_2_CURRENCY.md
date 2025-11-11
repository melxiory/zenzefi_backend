# Этап 2: Система валюты

**Статус:** ⏳ НЕ НАЧАТ
**Зависимости:** Этап 1 (MVP) ✅ завершён
**Время:** 5-7 дней

---

## Цель

Реализовать монетизацию через внутреннюю валюту **ZNC (Zenzefi Credits)** с покупкой токенов за баланс, интеграцией payment gateway и системой возвратов.

---

## Roadmap

| День | Задача | Описание |
|------|--------|----------|
| 1 | Database Models | Transaction model, User.currency_balance, миграции |
| 2 | Pricing Configuration | Settings pricing, get_token_price() |
| 3 | Currency API | GET /balance, GET /transactions |
| 4 | Token Purchase Logic | Списание баланса, atomic transactions, 402 error |
| 5 | Refund System | DELETE /tokens/{id}, proportional refund |
| 6-7 | Payment Gateway | YooKassa/Stripe integration, webhook handler |
| 8 | Testing & Docs | 15+ tests, documentation |

---

## Задачи

### Задача 1: Database Models (1 день)

**Transaction Model:**
```python
# app/models/transaction.py
class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"      # Пополнение баланса
    PURCHASE = "purchase"    # Покупка токена
    REFUND = "refund"        # Возврат за неиспользованное время

class Transaction(Base):
    id = Column(UUID, primary_key=True)
    user_id = Column(UUID, ForeignKey("users.id"), index=True)
    amount = Column(Numeric(10, 2))  # + deposit/refund, - purchase
    transaction_type = Column(Enum(TransactionType), index=True)
    description = Column(String)
    payment_id = Column(String, nullable=True)  # YooKassa/Stripe ID
    created_at = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="transactions")
```

**User.currency_balance:**
```python
# app/models/user.py - добавить
currency_balance = Column(Numeric(10, 2), default=Decimal('0.00'), index=True)
transactions = relationship("Transaction", cascade="all, delete-orphan")
```

**Миграция:**
```bash
poetry run alembic revision --autogenerate -m "Add currency_balance and Transaction model"
poetry run alembic upgrade head
```

---

### Задача 2: Pricing Configuration (1 день)

**Settings:**
```python
# app/config.py
class Settings(BaseSettings):
    # Token Pricing (ZNC credits)
    TOKEN_PRICE_1H: Decimal = Decimal("1.00")
    TOKEN_PRICE_12H: Decimal = Decimal("10.00")
    TOKEN_PRICE_24H: Decimal = Decimal("18.00")
    TOKEN_PRICE_7D: Decimal = Decimal("100.00")   # 168 hours
    TOKEN_PRICE_30D: Decimal = Decimal("300.00")  # 720 hours

    def get_token_price(self, duration_hours: int) -> Decimal:
        price_map = {
            1: self.TOKEN_PRICE_1H,
            12: self.TOKEN_PRICE_12H,
            24: self.TOKEN_PRICE_24H,
            168: self.TOKEN_PRICE_7D,
            720: self.TOKEN_PRICE_30D,
        }
        return price_map.get(duration_hours)
```

**Environment Variables:**
```bash
# .env - опционально (defaults в Settings)
TOKEN_PRICE_1H=1.00
TOKEN_PRICE_24H=18.00
```

---

### Задача 3: Currency API Endpoints (1-2 дня)

**GET /api/v1/currency/balance:**
```python
# Response
{
  "balance": 150.00,
  "currency": "ZNC",
  "user_id": "uuid"
}
```

**GET /api/v1/currency/transactions:**
```python
# Query params: ?limit=20&offset=0&type=deposit
# Response
{
  "items": [...],
  "total": 50,
  "limit": 20,
  "offset": 0
}
```

**POST /api/v1/currency/purchase:**
```python
# Request
{
  "amount_znc": 100.00,
  "payment_method": "yookassa",
  "return_url": "https://zenzefi.app/payment/success"
}

# Response
{
  "payment_id": "uuid",
  "payment_url": "https://yookassa.ru/checkout/...",
  "amount_znc": 100.00,
  "amount_rub": 1000.00,  # Conversion: 1 ZNC = 10 RUB
  "status": "pending"
}
```

---

### Задача 4: Token Purchase Logic (1 день)

**Update TokenService.generate_access_token():**
```python
def generate_access_token(user_id, duration_hours, scope, db):
    # 1. Calculate cost
    cost = settings.get_token_price(duration_hours)

    # 2. Check balance (with lock)
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user.currency_balance < cost:
        raise ValueError(f"Insufficient balance. Required: {cost} ZNC")

    # 3. Generate token
    token_string = secrets.token_urlsafe(48)
    db_token = AccessToken(...)

    # 4. Deduct cost (atomic)
    user.currency_balance -= cost

    # 5. Create transaction
    transaction = Transaction(
        user_id=user_id,
        amount=-cost,
        transaction_type=TransactionType.PURCHASE,
        description=f"Token purchase: {duration_hours}h ({scope})"
    )

    db.add_all([db_token, transaction])
    db.commit()

    return db_token, cost
```

**API Response (updated):**
```python
# POST /tokens/purchase
# Response 201
{
  "token_id": "uuid",
  "token": "abc123...",
  "cost_znc": 18.00,  # NEW
  "duration_hours": 24,
  ...
}

# Response 402 (Insufficient funds)
{
  "detail": "Insufficient balance. Required: 18.00 ZNC, Available: 10.00 ZNC"
}
```

---

### Задача 5: Refund System (1 день)

**TokenService.revoke_token():**
```python
def revoke_token(token_id, user_id, db):
    token = db.query(AccessToken).filter(...).with_for_update().first()

    # Calculate refund (proportional to unused time)
    now = datetime.now(timezone.utc)
    time_used_hours = (now - token.activated_at).total_seconds() / 3600 if token.activated_at else 0
    time_unused_hours = max(0, token.duration_hours - time_used_hours)

    cost = settings.get_token_price(token.duration_hours)
    refund_amount = cost * Decimal(time_unused_hours / token.duration_hours)
    refund_amount = refund_amount.quantize(Decimal('0.01'))

    # Revoke + refund
    token.is_active = False
    token.revoked_at = now

    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    user.currency_balance += refund_amount

    if refund_amount > 0:
        transaction = Transaction(
            user_id=user_id,
            amount=refund_amount,
            transaction_type=TransactionType.REFUND,
            description=f"Token refund: {time_unused_hours:.1f}h unused"
        )
        db.add(transaction)

    db.commit()
    TokenService._remove_cached_token(token.token)

    return True, refund_amount
```

**API Endpoint:**
```python
# DELETE /api/v1/tokens/{token_id}
# Response
{
  "revoked": true,
  "refund_amount": 5.00,
  "new_balance": 155.00,
  "message": "Token revoked. Refunded 5.00 ZNC."
}
```

---

### Задача 6: Payment Gateway Integration (2-3 дня) 🆕

**YooKassa/Stripe Integration:**

#### PaymentService (`app/services/payment_service.py`):
```python
async def create_payment(amount_znc, user_id, return_url, db):
    amount_rub = amount_znc * Decimal("10.00")  # Conversion rate

    # Create payment in YooKassa
    payment = Payment.create({
        "amount": {"value": str(amount_rub), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": f"Zenzefi Credits: {amount_znc} ZNC",
        "metadata": {"user_id": str(user_id), "amount_znc": str(amount_znc)}
    })

    # Create pending transaction
    transaction = Transaction(
        user_id=user_id,
        amount=amount_znc,
        transaction_type=TransactionType.DEPOSIT,
        description=f"Balance top-up: {amount_znc} ZNC (pending)",
        payment_id=payment.id
    )
    db.add(transaction)
    db.commit()

    return {
        "payment_id": payment.id,
        "payment_url": payment.confirmation.confirmation_url,
        "amount_znc": amount_znc,
        "amount_rub": amount_rub
    }

async def handle_webhook(payment_data, db):
    payment_id = payment_data["object"]["id"]
    status = payment_data["object"]["status"]

    transaction = db.query(Transaction).filter(
        Transaction.payment_id == payment_id
    ).with_for_update().first()

    if status == "succeeded":
        # Credit user balance
        user = db.query(User).filter(User.id == transaction.user_id).with_for_update().first()
        user.currency_balance += transaction.amount
        transaction.description = transaction.description.replace("(pending)", "(succeeded)")
        db.commit()
        return True

    elif status == "canceled":
        transaction.description = transaction.description.replace("(pending)", "(canceled)")
        db.commit()
        return False
```

#### Webhook Endpoint (`app/api/v1/webhooks.py`):
```python
@router.post("/payment")
async def payment_webhook(request: Request, db: Session = Depends(get_db)):
    # Verify signature (YooKassa)
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature")
    expected = hmac.new(settings.YOOKASSA_SECRET_KEY.encode(), body, hashlib.sha256).hexdigest()

    if signature != expected:
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Process payment
    data = await request.json()
    success = await PaymentService.handle_webhook(data, db)

    return {"received": True, "processed": success}
```

**Environment Variables:**
```bash
# .env
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
```

**Dependencies:**
```bash
poetry add yookassa  # or stripe for Stripe integration
```

---

## Testing (1 день)

**Test Coverage:**
```python
# tests/test_currency_service.py
test_insufficient_balance_token_purchase()  # 402 error
test_token_purchase_with_balance()          # Balance deduction
test_token_refund()                          # Proportional refund
test_payment_webhook_success()               # YooKassa webhook
test_payment_webhook_canceled()              # Failed payment
```

**Запуск:**
```bash
poetry run pytest tests/test_currency_service.py -v
poetry run pytest tests/test_api_tokens.py -v  # Updated tests
```

---

## Результат

После завершения Этапа 2:
- ✅ Полная система монетизации с внутренней валютой ZNC
- ✅ Интеграция payment gateway (YooKassa/Stripe)
- ✅ Автоматическая система refund за неиспользованное время
- ✅ Transaction history для audit trail
- ✅ 15+ новых тестов с реальной payment logic

**Следующий этап:** [Этап 3 (Мониторинг)](./PHASE_3_MONITORING.md) - ProxySession tracking, Admin endpoints, Prometheus metrics

---

**См. также:**
- [BACKEND.md](../BACKEND.md) - Overview
- [PHASE_1_MVP.md](./PHASE_1_MVP.md) - Предыдущий этап
- [ADR.md](../ADR.md) - Architecture Decision Records
