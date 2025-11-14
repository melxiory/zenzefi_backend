# Phase 2: Currency System - Полное руководство

**Версия:** 0.4.0-beta
**Дата:** 2025-11-14
**Статус:** ✅ ЗАВЕРШЁН

---

## 📋 Содержание

1. [Обзор системы](#обзор-системы)
2. [Архитектура](#архитектура)
3. [Модели данных](#модели-данных)
4. [Сервисы](#сервисы)
5. [API Endpoints](#api-endpoints)
6. [Бизнес-логика](#бизнес-логика)
7. [Примеры использования](#примеры-использования)
8. [Безопасность](#безопасность)
9. [Тестирование](#тестирование)

---

## Обзор системы

Phase 2 добавляет **систему внутренней валюты ZNC (Zenzefi Credits)** для монетизации доступа к Zenzefi серверу через токены.

### Ключевые возможности

- ✅ **Внутренняя валюта ZNC** - пополнение баланса через payment gateway
- ✅ **Покупка токенов за ZNC** - списание с баланса при создании токена
- ✅ **Система возвратов** - 100% возврат за неактивированные токены
- ✅ **История транзакций** - полный аудит всех операций с балансом
- ✅ **Mock Payment Gateway** - заглушка для разработки (YooKassa/Stripe в production)
- ✅ **Webhook handling** - обработка коллбэков от payment gateway

### Pricing (Цены токенов)

| Длительность | Цена ZNC | Скидка |
|--------------|----------|--------|
| 1 час        | 1 ZNC    | -      |
| 12 часов     | 10 ZNC   | 16%    |
| 24 часа      | 18 ZNC   | 25%    |
| 7 дней       | 100 ZNC  | 40%    |
| 30 дней      | 300 ZNC  | 58%    |

### Конверсия валюты

- **1 ZNC = 10 RUB** (по умолчанию, настраивается в `.env`)
- Пример: пополнение на 100 RUB = 10 ZNC

---

## Архитектура

### Диаграмма компонентов

```
┌─────────────────────────────────────────────────────────────┐
│                      CLIENT (User)                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     API Endpoints                           │
│  /currency/balance │ /currency/purchase │ /tokens/purchase  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                       Services                              │
│  CurrencyService │ PaymentService │ TokenService            │
└─────────────────────────────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
┌──────────────────────┐    ┌──────────────────────┐
│   PostgreSQL DB      │    │  Payment Gateway     │
│  - User.balance      │    │  (Mock/YooKassa)     │
│  - Transaction       │    │                      │
│  - AccessToken       │    │  Webhook callback    │
└──────────────────────┘    └──────────────────────┘
```

### Request Flow: Покупка токена

```
1. User запрос → POST /api/v1/tokens/purchase
                  Authorization: Bearer {jwt_token}
                  Body: {duration_hours: 24, scope: "full"}

2. TokenService.generate_access_token()
   ├─ Проверка цены: settings.get_token_price(24) → 18 ZNC
   ├─ Блокировка user: db.query(User).with_for_update()
   ├─ Проверка баланса: user.currency_balance >= 18
   ├─ Списание: user.currency_balance -= 18
   ├─ Создание токена: AccessToken(duration_hours=24)
   └─ Транзакция: Transaction(type=PURCHASE, amount=-18)

3. Response → {token: "...", duration_hours: 24, cost_znc: 18}
```

### Request Flow: Пополнение баланса

```
1. User запрос → POST /api/v1/currency/purchase
                  Body: {amount_znc: 100}

2. PaymentService.create_payment()
   ├─ Конверсия: 100 ZNC * 10 RUB = 1000 RUB
   ├─ MockPaymentProvider.create_payment()
   └─ Payment URL: http://localhost:8000/webhooks/mock-payment?payment_id=...

3. User оплачивает → GET /webhooks/mock-payment?payment_id=xxx&status=succeeded

4. Webhook → POST /api/v1/webhooks/payment
              Body: {payment_id: "xxx", status: "succeeded"}

5. PaymentService.handle_webhook()
   ├─ Проверка статуса: "succeeded"
   ├─ CurrencyService.credit_balance(100 ZNC)
   ├─ Блокировка user: with_for_update()
   ├─ Начисление: user.currency_balance += 100
   └─ Транзакция: Transaction(type=DEPOSIT, amount=+100)

6. Response → User balance увеличен на 100 ZNC
```

---

## Модели данных

### User Model (обновлена)

**Файл:** `app/models/user.py`

```python
class User(Base):
    __tablename__ = "users"

    # Существующие поля
    id: UUID
    email: str
    username: str
    hashed_password: str
    full_name: str | None
    is_active: bool
    is_superuser: bool

    # ✅ НОВОЕ в Phase 2
    currency_balance: Decimal  # Decimal(10, 2), default=0.00, indexed

    # Relationships
    tokens: list[AccessToken]      # one-to-many, cascade delete
    transactions: list[Transaction] # one-to-many, cascade delete ✅ НОВОЕ
```

**Ключевые особенности:**

- `currency_balance` - тип **Decimal(10, 2)** для точности (не float!)
- Индекс на `currency_balance` для быстрых запросов
- Max значение: 99,999,999.99 ZNC (10 цифр, 2 после запятой)

### AccessToken Model (обновлена)

**Файл:** `app/models/token.py`

```python
class AccessToken(Base):
    __tablename__ = "access_tokens"

    # Существующие поля
    id: UUID
    user_id: UUID  # FK to users
    token: str     # 64-char random string
    duration_hours: int
    scope: str     # "full" | "certificates_only"
    activated_at: datetime | None
    is_active: bool
    revoked_at: datetime | None

    # Computed properties
    @property
    def expires_at(self) -> datetime | None:
        """Calculated: activated_at + duration_hours"""
        if not self.activated_at:
            return None
        return self.activated_at + timedelta(hours=self.duration_hours)

    # ✅ НОВОЕ в Phase 2
    @property
    def cost_znc(self) -> Decimal | None:
        """Calculate cost dynamically from duration"""
        from app.config import settings
        return settings.get_token_price(self.duration_hours)
```

**Почему `cost_znc` - property?**

- Не хранится в БД (избегаем дублирования данных)
- Вычисляется динамически из `duration_hours`
- Позволяет изменить цены без миграции БД
- Автоматически сериализуется в Pydantic schemas

### Transaction Model (новая)

**Файл:** `app/models/transaction.py`

```python
class TransactionType(str, Enum):
    """Types of balance transactions"""
    DEPOSIT = "deposit"    # Пополнение баланса (payment gateway)
    PURCHASE = "purchase"  # Покупка токена
    REFUND = "refund"      # Возврат за отменённый токен


class Transaction(Base):
    __tablename__ = "transactions"

    id: UUID                           # Primary key
    user_id: UUID                      # FK to users
    amount: Decimal                    # Decimal(10, 2)
    transaction_type: TransactionType  # DEPOSIT | PURCHASE | REFUND
    description: str                   # Human-readable description
    payment_id: str | None             # External payment gateway ID
    created_at: datetime               # Timestamp (UTC)

    # Relationship
    user: User  # many-to-one
```

**Правила для `amount`:**

| Тип транзакции | Знак amount | Пример |
|----------------|-------------|--------|
| DEPOSIT        | + (положительный) | +100.00 ZNC |
| PURCHASE       | - (отрицательный) | -18.00 ZNC |
| REFUND         | + (положительный) | +18.00 ZNC |

**Примеры `description`:**

- `"Balance top-up via payment gateway"`
- `"Token purchase: 24h full access"`
- `"Token refund: 24h (not activated)"`

**`payment_id`:**

- Опциональный, для связи с внешним платёжным шлюзом
- В mock gateway: UUID строка
- В production (YooKassa): их transaction ID

---

## Сервисы

### CurrencyService

**Файл:** `app/services/currency_service.py`

Отвечает за управление балансом ZNC и историей транзакций.

#### Методы

##### 1. `get_balance(user_id: UUID, db: Session) -> Decimal`

Получить текущий баланс пользователя.

```python
balance = CurrencyService.get_balance(user_id, db)
# Returns: Decimal("42.50")
```

**Реализация:**
```python
user = db.query(User).filter(User.id == user_id).first()
if not user:
    raise ValueError("User not found")
return user.currency_balance
```

##### 2. `credit_balance(user_id, amount, description, payment_id, db) -> Transaction`

Начислить баланс пользователю (атомарно).

```python
transaction = CurrencyService.credit_balance(
    user_id=user_id,
    amount=Decimal("100.00"),
    description="Balance top-up via YooKassa",
    payment_id="yookassa_123456",
    db=db
)
```

**Критическая логика:**
```python
# 1. Блокировка строки user (row-level lock)
user = db.query(User).filter(User.id == user_id).with_for_update().first()

# 2. Увеличение баланса
user.currency_balance += amount

# 3. Создание транзакции
transaction = Transaction(
    user_id=user_id,
    amount=amount,  # Положительное значение
    transaction_type=TransactionType.DEPOSIT,
    description=description,
    payment_id=payment_id
)
db.add(transaction)
db.commit()
```

**Зачем `with_for_update()`?**

Предотвращает race condition при параллельных пополнениях:

```
Thread 1: Читает balance=100
Thread 2: Читает balance=100
Thread 1: Пишет balance=100+50=150
Thread 2: Пишет balance=100+30=130  ❌ ПОТЕРЯ 50 ZNC!

С with_for_update():
Thread 1: Блокирует строку, balance=100
Thread 2: Ждёт...
Thread 1: Пишет balance=150, коммит, отпускает блокировку
Thread 2: Читает balance=150, пишет balance=180 ✅
```

##### 3. `get_transactions(user_id, skip, limit, transaction_type, db) -> Tuple`

Получить историю транзакций с пагинацией и фильтрацией.

```python
transactions, total = CurrencyService.get_transactions(
    user_id=user_id,
    skip=0,
    limit=20,
    transaction_type="PURCHASE",  # Опциональный фильтр
    db=db
)
```

**Реализация:**
```python
query = db.query(Transaction).filter(Transaction.user_id == user_id)

# Опциональный фильтр по типу
if transaction_type:
    query = query.filter(Transaction.transaction_type == transaction_type)

# Подсчёт total
total = query.count()

# Пагинация + сортировка
transactions = query.order_by(Transaction.created_at.desc()) \
                   .offset(skip) \
                   .limit(limit) \
                   .all()

return transactions, total
```

---

### PaymentService

**Файл:** `app/services/payment_service.py`

Отвечает за интеграцию с payment gateway (mock или production).

#### Архитектура

```python
class PaymentProvider(ABC):
    """Abstract base для payment providers"""

    @abstractmethod
    def create_payment(self, amount_rub: Decimal, user_id: UUID, amount_znc: Decimal) -> Dict:
        """Создать платёж, вернуть payment_id и URL"""
        pass

    @abstractmethod
    def verify_webhook(self, payload: Dict) -> bool:
        """Проверить подпись webhook (HMAC)"""
        pass
```

#### MockPaymentProvider (для development)

```python
class MockPaymentProvider(PaymentProvider):
    """Заглушка payment gateway для разработки"""

    def create_payment(self, amount_rub, user_id, amount_znc):
        payment_id = str(uuid.uuid4())

        # Возвращаем URL на mock страницу оплаты
        payment_url = f"{settings.MOCK_PAYMENT_URL}?payment_id={payment_id}"

        return {
            "payment_id": payment_id,
            "payment_url": payment_url,
            "amount_rub": amount_rub,
            "amount_znc": amount_znc,
            "status": "pending"
        }

    def verify_webhook(self, payload):
        # В mock всегда возвращаем True
        # В production здесь HMAC проверка
        return True
```

#### YooKassaProvider (для production)

**Файл:** `app/services/payment_providers/yookassa.py` (будущее)

```python
class YooKassaProvider(PaymentProvider):
    def __init__(self):
        from yookassa import Configuration, Payment
        Configuration.account_id = settings.YOOKASSA_SHOP_ID
        Configuration.secret_key = settings.YOOKASSA_SECRET_KEY

    def create_payment(self, amount_rub, user_id, amount_znc):
        payment = Payment.create({
            "amount": {"value": str(amount_rub), "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": f"{settings.BACKEND_URL}/payment/success"
            },
            "description": f"ZNC purchase: {amount_znc} ZNC"
        })

        return {
            "payment_id": payment.id,
            "payment_url": payment.confirmation.confirmation_url,
            "amount_rub": amount_rub,
            "amount_znc": amount_znc,
            "status": payment.status
        }

    def verify_webhook(self, payload):
        # HMAC signature verification
        signature = payload.get("signature")
        data = payload.get("data")
        expected = hmac.new(
            settings.YOOKASSA_SECRET_KEY.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
```

#### PaymentService методы

##### 1. `create_payment(amount_znc: Decimal, user_id: UUID, db: Session) -> Dict`

Создать платёж для пополнения баланса.

```python
payment = PaymentService.create_payment(
    amount_znc=Decimal("100.00"),
    user_id=user_id,
    db=db
)
# Returns:
# {
#   "payment_id": "uuid-...",
#   "payment_url": "http://localhost:8000/webhooks/mock-payment?...",
#   "amount_rub": Decimal("1000.00"),
#   "amount_znc": Decimal("100.00"),
#   "status": "pending"
# }
```

**Flow:**
```python
# 1. Конверсия ZNC → RUB
amount_rub = amount_znc * settings.ZNC_TO_RUB_RATE  # 100 * 10 = 1000

# 2. Создание платежа через provider
provider = MockPaymentProvider()
payment = provider.create_payment(amount_rub, user_id, amount_znc)

# 3. Сохранение metadata в Redis (TTL: 1 час)
redis_client.setex(
    f"payment:{payment_id}",
    3600,
    json.dumps({
        "user_id": str(user_id),
        "amount_znc": str(amount_znc),
        "amount_rub": str(amount_rub),
        "status": "pending"
    })
)

return payment
```

##### 2. `handle_webhook(payload: Dict, db: Session) -> bool`

Обработать webhook от payment gateway.

```python
success = PaymentService.handle_webhook(
    payload={
        "payment_id": "uuid-...",
        "status": "succeeded",
        "amount": "1000.00"
    },
    db=db
)
```

**Flow:**
```python
# 1. Проверка подписи (в production)
if not provider.verify_webhook(payload):
    raise ValueError("Invalid webhook signature")

# 2. Получение metadata из Redis
payment_data = redis_client.get(f"payment:{payment_id}")
if not payment_data:
    raise ValueError("Payment not found")

data = json.loads(payment_data)

# 3. Проверка статуса
if payload["status"] != "succeeded":
    # Обработка отмены/ошибки
    return False

# 4. Начисление баланса
CurrencyService.credit_balance(
    user_id=UUID(data["user_id"]),
    amount=Decimal(data["amount_znc"]),
    description="Balance top-up via payment gateway",
    payment_id=payment_id,
    db=db
)

# 5. Удаление metadata из Redis
redis_client.delete(f"payment:{payment_id}")

return True
```

---

### TokenService (обновлён)

**Файл:** `app/services/token_service.py`

#### Обновлённые методы Phase 2

##### 1. `generate_access_token(user_id, duration_hours, scope, db) -> AccessToken`

**ИЗМЕНЕНО:** Теперь списывает ZNC баланс при покупке токена.

```python
token = TokenService.generate_access_token(
    user_id=str(user_id),
    duration_hours=24,
    scope="full",
    db=db
)
# Списывает 18 ZNC с баланса
```

**Новая логика:**
```python
# 1. Получение цены
cost = settings.get_token_price(duration_hours)
if cost is None:
    raise ValueError("Invalid duration")

# 2. Блокировка user
user = db.query(User).filter(User.id == user_id).with_for_update().first()

# 3. Проверка баланса
if user.currency_balance < cost:
    raise ValueError(
        f"Insufficient balance. Required: {cost} ZNC, "
        f"Available: {user.currency_balance} ZNC"
    )

# 4. Списание баланса
user.currency_balance -= cost

# 5. Создание токена
token = AccessToken(
    user_id=user_id,
    token=secrets.token_urlsafe(48),  # 64 chars
    duration_hours=duration_hours,
    scope=scope,
    is_active=True
)
db.add(token)

# 6. Транзакция PURCHASE
transaction = Transaction(
    user_id=user_id,
    amount=-cost,  # Отрицательное!
    transaction_type=TransactionType.PURCHASE,
    description=f"Token purchase: {duration_hours}h {scope} access"
)
db.add(transaction)

db.commit()
return token
```

##### 2. `revoke_token(token_id, user_id, db) -> Tuple[bool, Decimal]`

**ИЗМЕНЕНО:** Возврат только для **неактивированных** токенов.

```python
success, refund = TokenService.revoke_token(
    token_id=token_id,
    user_id=user_id,
    db=db
)
# Returns: (True, Decimal("18.00"))  если токен не активирован
# Raises: ValueError("Cannot revoke activated token") если активирован
```

**Новая политика возврата:**

| Состояние токена | Возврат | Причина |
|------------------|---------|---------|
| Не активирован (`activated_at=None`) | 100% | Токен не использовался |
| Активирован (`activated_at!=None`) | ❌ ERROR | Токен уже использовался |
| Истёк (`expires_at < now`) | ❌ ERROR | Токен был активирован |

**Логика:**
```python
# 1. Блокировка токена
db_token = db.query(AccessToken).filter(
    AccessToken.id == token_id,
    AccessToken.user_id == user_id,
    AccessToken.is_active == True,
    AccessToken.revoked_at == None
).with_for_update().first()

if not db_token:
    raise ValueError("Token not found or already revoked")

# 2. Проверка активации
if db_token.activated_at is not None:
    raise ValueError(
        "Cannot revoke activated token. "
        "Refunds are only available for non-activated tokens."
    )

# 3. Полный возврат
cost = settings.get_token_price(db_token.duration_hours)
refund_amount = cost  # 100%

# 4. Revoke токена
db_token.is_active = False
db_token.revoked_at = datetime.now(timezone.utc)

# 5. Возврат баланса
user = db.query(User).filter(User.id == user_id).with_for_update().first()
user.currency_balance += refund_amount

# 6. Транзакция REFUND
transaction = Transaction(
    user_id=user_id,
    amount=refund_amount,  # Положительное
    transaction_type=TransactionType.REFUND,
    description=f"Token refund: {db_token.duration_hours}h (not activated)"
)
db.add(transaction)

db.commit()
return True, refund_amount
```

**Почему только неактивированные?**

- Упрощённая политика refund
- Избегаем сложных вычислений времени использования
- Предотвращаем злоупотребления (использовал → вернул)
- В production можно добавить частичный refund через customer support

---

## API Endpoints

### Currency Endpoints

#### 1. GET `/api/v1/currency/balance`

Получить текущий баланс ZNC.

**Auth:** JWT token required

**Request:**
```http
GET /api/v1/currency/balance HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response:**
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "balance": "42.50",
  "last_updated": "2025-11-14T12:34:56.789Z"
}
```

#### 2. GET `/api/v1/currency/transactions`

Получить историю транзакций.

**Auth:** JWT token required

**Query Parameters:**
- `skip` (int, default=0) - Pagination offset
- `limit` (int, default=20, max=100) - Items per page
- `transaction_type` (str, optional) - Filter: "DEPOSIT" | "PURCHASE" | "REFUND"

**Request:**
```http
GET /api/v1/currency/transactions?skip=0&limit=10&transaction_type=PURCHASE HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response:**
```json
{
  "transactions": [
    {
      "id": "uuid-1",
      "amount": "-18.00",
      "transaction_type": "PURCHASE",
      "description": "Token purchase: 24h full access",
      "payment_id": null,
      "created_at": "2025-11-14T12:00:00Z"
    },
    {
      "id": "uuid-2",
      "amount": "100.00",
      "transaction_type": "DEPOSIT",
      "description": "Balance top-up via payment gateway",
      "payment_id": "yookassa_123456",
      "created_at": "2025-11-14T10:00:00Z"
    }
  ],
  "total": 42,
  "skip": 0,
  "limit": 10
}
```

#### 3. POST `/api/v1/currency/purchase`

Создать платёж для пополнения баланса.

**Auth:** JWT token required

**Request:**
```http
POST /api/v1/currency/purchase HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "amount_znc": "100.00"
}
```

**Response:**
```json
{
  "payment_id": "uuid-abc123",
  "payment_url": "http://localhost:8000/api/v1/webhooks/mock-payment?payment_id=uuid-abc123",
  "amount_znc": "100.00",
  "amount_rub": "1000.00",
  "status": "pending"
}
```

**Действия пользователя:**
1. Перейти по `payment_url`
2. На mock странице нажать "Successful Payment" или "Cancel"
3. Webhook автоматически начислит баланс

#### 4. POST `/api/v1/currency/mock-purchase`

**⚠️ ТОЛЬКО ДЛЯ ТЕСТИРОВАНИЯ!** Прямое пополнение баланса без payment gateway.

**Auth:** JWT token required

**Request:**
```http
POST /api/v1/currency/mock-purchase HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "amount": "100.00"
}
```

**Response:**
```json
{
  "user_id": "uuid-user",
  "amount": "100.00",
  "transaction_type": "DEPOSIT",
  "description": "Mock balance purchase (testing)",
  "created_at": "2025-11-14T12:34:56Z"
}
```

**⚠️ В production:** Этот endpoint должен быть удалён или защищён admin правами!

#### 5. POST `/api/v1/currency/admin/simulate-payment/{payment_id}`

**⚠️ ТОЛЬКО ДЛЯ ТЕСТИРОВАНИЯ!** Симуляция успешного платежа.

**Auth:** JWT token required (в production: admin only)

**Request:**
```http
POST /api/v1/currency/admin/simulate-payment/uuid-abc123 HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response:**
```json
{
  "message": "Payment simulated successfully",
  "payment_id": "uuid-abc123",
  "user_id": "uuid-user",
  "amount_znc": "100.00",
  "balance_after": "142.50"
}
```

---

### Webhook Endpoints

#### 1. POST `/api/v1/webhooks/payment`

Обработка webhook от payment gateway.

**Auth:** HMAC signature (в production), public endpoint

**Request:**
```http
POST /api/v1/webhooks/payment HTTP/1.1
Content-Type: application/json
X-Signature: sha256_hmac_signature_here (в production)

{
  "payment_id": "uuid-abc123",
  "status": "succeeded",
  "amount": "1000.00"
}
```

**Response:**
```json
{
  "status": "ok"
}
```

**Errors:**
- `400 Bad Request` - Invalid signature
- `404 Not Found` - Payment not found
- `422 Unprocessable Entity` - Invalid payload

#### 2. GET `/api/v1/webhooks/mock-payment`

**⚠️ ТОЛЬКО ДЛЯ ТЕСТИРОВАНИЯ!** Mock страница оплаты.

**Request:**
```http
GET /api/v1/webhooks/mock-payment?payment_id=uuid-abc123&status=succeeded HTTP/1.1
```

**Response:** HTML страница с кнопками "Successful Payment" / "Cancel Payment"

---

### Tokens Endpoints (обновлены)

#### 1. POST `/api/v1/tokens/purchase`

Купить access token за ZNC.

**ИЗМЕНЕНО:** Теперь списывает баланс, вместо бесплатной генерации.

**Auth:** JWT token required

**Request:**
```http
POST /api/v1/tokens/purchase HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "duration_hours": 24,
  "scope": "full"
}
```

**Response Success (200):**
```json
{
  "id": "token-uuid",
  "token": "64-character-random-string-here",
  "duration_hours": 24,
  "scope": "full",
  "cost_znc": "18.00",
  "activated_at": null,
  "expires_at": null,
  "is_active": true,
  "revoked_at": null,
  "created_at": "2025-11-14T12:34:56Z"
}
```

**Response Error (402 Payment Required):**
```json
{
  "detail": "Insufficient balance. Required: 18.00 ZNC, Available: 5.00 ZNC"
}
```

**Response Error (400 Bad Request):**
```json
{
  "detail": "Invalid duration_hours. Allowed: 1, 12, 24, 168, 720"
}
```

#### 2. DELETE `/api/v1/tokens/{token_id}`

Отменить токен с возвратом баланса.

**ИЗМЕНЕНО:** Возврат только для неактивированных токенов.

**Auth:** JWT token required

**Request:**
```http
DELETE /api/v1/tokens/abc-token-uuid HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response Success (200):**
```json
{
  "message": "Token revoked successfully",
  "refund_amount": "18.00"
}
```

**Response Error (400 Bad Request):**
```json
{
  "detail": "Cannot revoke activated token. Refunds are only available for non-activated tokens."
}
```

**Response Error (404 Not Found):**
```json
{
  "detail": "Token not found or already revoked"
}
```

---

## Бизнес-логика

### 1. Покупка токена - Full Flow

```
┌─────────────────────────────────────────────────────────────┐
│ User: Хочу купить токен на 24 часа                          │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Проверка баланса                                    │
│  - Текущий баланс: 100 ZNC                                  │
│  - Требуется: 18 ZNC (цена за 24h)                          │
│  - Достаточно? ✅ Да                                         │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Атомарная транзакция (PostgreSQL)                  │
│  BEGIN;                                                     │
│  1. SELECT * FROM users WHERE id=... FOR UPDATE;           │
│  2. UPDATE users SET currency_balance = 100-18 = 82;       │
│  3. INSERT INTO access_tokens (...);                        │
│  4. INSERT INTO transactions (amount=-18, type=PURCHASE);   │
│  COMMIT;                                                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Результат                                           │
│  - Баланс после: 82 ZNC                                     │
│  - Токен создан: "abc123..." (64 chars)                     │
│  - Длительность: 24 часа                                    │
│  - Активирован: Нет (activated_at=None)                     │
│  - Истекает: Null (активируется при первом использовании)   │
└─────────────────────────────────────────────────────────────┘
```

### 2. Активация токена - First Use

```
┌─────────────────────────────────────────────────────────────┐
│ User: Запускает DTS Monaco с токеном "abc123..."           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Desktop Client: Добавляет X-Access-Token header             │
│  GET /certificates/filter                                   │
│  X-Access-Token: abc123...                                  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend: TokenService.validate_token()                      │
│  1. Check Redis: active_token:sha256(abc123)  ❌ Not found  │
│  2. Check PostgreSQL:                                       │
│     - Token exists? ✅                                       │
│     - is_active? ✅                                          │
│     - revoked_at? ❌ Null                                    │
│     - activated_at? ❌ Null → ПЕРВОЕ ИСПОЛЬЗОВАНИЕ!         │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Активация токена                                    │
│  UPDATE access_tokens                                       │
│  SET activated_at = '2025-11-14 12:00:00'                   │
│  WHERE id = token_id;                                       │
│                                                             │
│  Expires at = activated_at + 24h = '2025-11-15 12:00:00'   │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: Кеширование в Redis                                 │
│  SET active_token:sha256(abc123) {                          │
│    "user_id": "uuid",                                       │
│    "token_id": "uuid",                                      │
│    "expires_at": "2025-11-15T12:00:00Z",                    │
│    "duration_hours": 24,                                    │
│    "scope": "full"                                          │
│  }                                                          │
│  EXPIRE active_token:sha256(abc123) 86400  # 24h           │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Проксирование запроса к Zenzefi                     │
│  ✅ Доступ разрешён                                          │
└─────────────────────────────────────────────────────────────┘
```

### 3. Возврат токена - Refund Flow

```
┌─────────────────────────────────────────────────────────────┐
│ User: Хочу отменить токен и вернуть деньги                  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Проверка возможности возврата                       │
│  DELETE /api/v1/tokens/{token_id}                           │
│                                                             │
│  Проверки:                                                  │
│  ✅ Токен существует                                         │
│  ✅ Принадлежит текущему user                                │
│  ✅ is_active = True                                         │
│  ✅ revoked_at = None                                        │
│  ❓ activated_at = ?                                         │
└─────────────────────────────────────────────────────────────┘
                           │
                  ┌────────┴─────────┐
                  ▼                  ▼
         activated_at = None   activated_at != None
         (не использован)      (уже использован)
                  │                  │
                  ▼                  ▼
    ┌─────────────────────┐  ┌──────────────────────┐
    │ ✅ ВОЗВРАТ 100%     │  │ ❌ ERROR             │
    │                     │  │ "Cannot revoke       │
    │ Refund = 18 ZNC     │  │  activated token"    │
    └─────────────────────┘  └──────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Атомарная транзакция                                │
│  BEGIN;                                                     │
│  1. UPDATE access_tokens SET                                │
│     is_active=False, revoked_at=NOW();                      │
│  2. SELECT * FROM users WHERE id=... FOR UPDATE;           │
│  3. UPDATE users SET currency_balance = 82+18 = 100;       │
│  4. INSERT INTO transactions (amount=+18, type=REFUND);     │
│  5. DELETE FROM Redis: active_token:sha256(abc123);         │
│  COMMIT;                                                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Результат                                           │
│  - Баланс после: 100 ZNC (вернулось 18 ZNC)                 │
│  - Токен revoked: is_active=False                           │
│  - Транзакция: REFUND +18.00                                │
└─────────────────────────────────────────────────────────────┘
```

### 4. Пополнение баланса - Payment Flow

```
┌─────────────────────────────────────────────────────────────┐
│ User: Хочу пополнить баланс на 100 ZNC                      │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Создание платежа                                    │
│  POST /api/v1/currency/purchase                             │
│  Body: {"amount_znc": "100.00"}                             │
│                                                             │
│  Backend:                                                   │
│  - Конверсия: 100 ZNC * 10 RUB = 1000 RUB                  │
│  - PaymentService.create_payment()                          │
│  - MockPaymentProvider.create_payment()                     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Сохранение metadata в Redis                         │
│  SET payment:uuid-abc123 {                                  │
│    "user_id": "uuid-user",                                  │
│    "amount_znc": "100.00",                                  │
│    "amount_rub": "1000.00",                                 │
│    "status": "pending"                                      │
│  }                                                          │
│  EXPIRE payment:uuid-abc123 3600  # 1 час                  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Redirect на payment_url                             │
│  Response: {                                                │
│    "payment_url": "http://.../mock-payment?payment_id=..." │
│  }                                                          │
│                                                             │
│  User переходит по ссылке → Mock страница оплаты            │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: User нажимает "Successful Payment"                  │
│  GET /webhooks/mock-payment?payment_id=...&status=succeeded │
│                                                             │
│  Mock endpoint вызывает webhook:                            │
│  POST /api/v1/webhooks/payment                              │
│  Body: {"payment_id": "...", "status": "succeeded"}         │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Webhook handler                                     │
│  PaymentService.handle_webhook()                            │
│  1. Проверка подписи (в production)                         │
│  2. Получение metadata из Redis                             │
│  3. Проверка status = "succeeded"                           │
│  4. CurrencyService.credit_balance(100 ZNC)                 │
│  5. DELETE payment:uuid-abc123 из Redis                     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 6: Результат                                           │
│  - Баланс увеличен: +100 ZNC                                │
│  - Транзакция: DEPOSIT +100.00                              │
│  - payment_id: "uuid-abc123" (из YooKassa)                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Безопасность

### 1. Row-Level Locking

**Проблема:** Race condition при параллельных операциях с балансом.

**Решение:** `with_for_update()` блокирует строку в PostgreSQL.

```python
# ❌ БЕЗ блокировки (race condition)
user = db.query(User).filter(User.id == user_id).first()
user.currency_balance += 100
db.commit()

# ✅ С блокировкой (thread-safe)
user = db.query(User).filter(User.id == user_id).with_for_update().first()
user.currency_balance += 100
db.commit()
```

**Как работает:**
```sql
-- PostgreSQL генерирует:
SELECT * FROM users WHERE id = 'uuid' FOR UPDATE;

-- FOR UPDATE блокирует строку до COMMIT/ROLLBACK
-- Другие транзакции будут ждать
```

### 2. Decimal для денег

**Проблема:** Float неточен для денежных операций.

```python
# ❌ Float - ошибки округления
balance = 0.1 + 0.2  # 0.30000000000000004

# ✅ Decimal - точные вычисления
from decimal import Decimal
balance = Decimal("0.1") + Decimal("0.2")  # Decimal("0.3")
```

**В моделях:**
```python
currency_balance: Mapped[Decimal] = mapped_column(
    Numeric(10, 2),  # PostgreSQL NUMERIC(10, 2)
    default=Decimal("0.00")
)
```

### 3. HMAC Webhook Verification

**Проблема:** Злоумышленник может отправить фейковый webhook.

**Решение:** HMAC подпись (в production).

```python
# В YooKassaProvider
def verify_webhook(self, payload):
    signature = payload.get("signature")
    data = json.dumps(payload.get("data"), sort_keys=True)

    expected = hmac.new(
        settings.YOOKASSA_SECRET_KEY.encode(),
        data.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)
```

**Почему `hmac.compare_digest()`?**
- Защита от timing attacks
- Обычное `==` может leak информацию через время сравнения

### 4. Payment Metadata в Redis

**Проблема:** Нужно связать webhook с user_id и amount_znc.

**Решение:** Временное хранилище в Redis (TTL: 1 час).

```python
# При создании платежа
redis_client.setex(
    f"payment:{payment_id}",
    3600,  # 1 час
    json.dumps({
        "user_id": str(user_id),
        "amount_znc": "100.00",
        "amount_rub": "1000.00"
    })
)

# В webhook
payment_data = redis_client.get(f"payment:{payment_id}")
if not payment_data:
    raise ValueError("Payment expired or not found")
```

**Почему TTL:**
- Автоматическая очистка expired платежей
- Защита от повторной обработки старых webhook
- Экономия памяти Redis

### 5. Idempotent Webhook Handling

**Проблема:** Payment gateway может отправить webhook несколько раз.

**Решение:** Проверка существования transaction с payment_id.

```python
def handle_webhook(payload, db):
    payment_id = payload["payment_id"]

    # Проверка duplicate
    existing = db.query(Transaction).filter(
        Transaction.payment_id == payment_id
    ).first()

    if existing:
        logger.warning(f"Duplicate webhook for {payment_id}")
        return True  # Уже обработано

    # Обработка...
```

---

## Тестирование

### Статистика тестов Phase 2

**Новые тесты:** 44
**Всего тестов:** 148
**Coverage:** 85%+

### Тестовые файлы

#### 1. `tests/test_currency_service.py` (10 тестов)

Тестирование CurrencyService.

```python
def test_credit_balance(test_db, test_user):
    """Test crediting balance to user"""
    transaction = CurrencyService.credit_balance(
        user_id=test_user.id,
        amount=Decimal("100.00"),
        description="Test credit",
        payment_id="test_payment_123",
        db=test_db
    )

    assert transaction.amount == Decimal("100.00")
    assert transaction.transaction_type == TransactionType.DEPOSIT

    # Verify balance updated
    balance = CurrencyService.get_balance(test_user.id, test_db)
    assert balance == Decimal("100.00")
```

**Покрывает:**
- get_balance()
- credit_balance()
- get_transactions() - pagination, filtering
- Concurrent credit (race condition)
- Decimal precision

#### 2. `tests/test_payment_service.py` (5 тестов)

Тестирование PaymentService и MockPaymentProvider.

```python
def test_create_payment(test_db, test_user):
    """Test creating a payment"""
    payment = PaymentService.create_payment(
        amount_znc=Decimal("100.00"),
        user_id=test_user.id,
        db=test_db
    )

    assert payment["payment_id"] is not None
    assert payment["amount_znc"] == Decimal("100.00")
    assert payment["amount_rub"] == Decimal("1000.00")  # 100 * 10
    assert payment["status"] == "pending"

    # Verify Redis metadata
    data = redis_client.get(f"payment:{payment['payment_id']}")
    assert data is not None
```

**Покрывает:**
- create_payment() - ZNC → RUB conversion
- handle_webhook() - успешный платёж
- handle_webhook() - отменённый платёж
- Redis metadata TTL
- Idempotent webhook handling

#### 3. `tests/test_token_purchase.py` (8 тестов)

Интеграционные тесты покупки/возврата токенов.

```python
def test_purchase_token_insufficient_balance(test_db, test_user):
    """Test purchasing token with insufficient balance"""
    # User has 0 ZNC, tries to buy 24h token (18 ZNC)
    with pytest.raises(ValueError, match="Insufficient balance"):
        TokenService.generate_access_token(
            user_id=str(test_user.id),
            duration_hours=24,
            scope="full",
            db=test_db
        )
```

```python
def test_revoke_token_full_refund(test_db, test_user):
    """Test revoking non-activated token (100% refund)"""
    # Credit balance and purchase
    CurrencyService.credit_balance(...)
    token = TokenService.generate_access_token(...)

    # Revoke immediately (not activated)
    success, refund = TokenService.revoke_token(
        token_id=token.id,
        user_id=test_user.id,
        db=test_db
    )

    assert success is True
    assert refund == Decimal("18.00")  # 100% refund
```

```python
def test_revoke_activated_token_error(test_db, test_user):
    """Test that revoking activated token raises error"""
    # Credit, purchase, and activate token
    token = TokenService.generate_access_token(...)
    token.activated_at = datetime.now(timezone.utc)
    test_db.commit()

    # Try to revoke - should fail
    with pytest.raises(ValueError, match="Cannot revoke activated token"):
        TokenService.revoke_token(token.id, test_user.id, test_db)
```

**Покрывает:**
- Покупка токена с балансом
- Покупка с недостаточным балансом (402 error)
- Возврат неактивированного токена (100%)
- Попытка возврата активированного токена (error)
- Создание транзакций PURCHASE/REFUND
- Атомарность операций

#### 4. `tests/test_api_currency.py` (13 тестов)

API endpoints для currency.

```python
def test_get_balance(client, auth_headers):
    """Test GET /api/v1/currency/balance"""
    response = client.get(
        "/api/v1/currency/balance",
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert "balance" in data
    assert Decimal(data["balance"]) >= 0
```

```python
def test_purchase_currency(client, auth_headers):
    """Test POST /api/v1/currency/purchase"""
    response = client.post(
        "/api/v1/currency/purchase",
        headers=auth_headers,
        json={"amount_znc": "100.00"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["payment_url"] is not None
    assert data["amount_rub"] == "1000.00"
```

**Покрывает:**
- GET /balance
- GET /transactions - pagination, filtering
- POST /purchase - создание платежа
- POST /mock-purchase - прямое пополнение
- POST /admin/simulate-payment - симуляция оплаты
- Авторизация (JWT required)
- Валидация (Pydantic)

#### 5. `tests/test_api_payment.py` (8 тестов)

Webhook endpoints.

```python
def test_payment_webhook_success(client, test_user, test_db):
    """Test successful payment webhook"""
    # Create payment first
    payment = PaymentService.create_payment(
        amount_znc=Decimal("100.00"),
        user_id=test_user.id,
        db=test_db
    )

    # Simulate webhook
    response = client.post(
        "/api/v1/webhooks/payment",
        json={
            "payment_id": payment["payment_id"],
            "status": "succeeded"
        }
    )

    assert response.status_code == 200

    # Verify balance credited
    balance = CurrencyService.get_balance(test_user.id, test_db)
    assert balance == Decimal("100.00")
```

**Покрывает:**
- POST /webhooks/payment - успешный
- POST /webhooks/payment - отменённый
- POST /webhooks/payment - invalid signature
- GET /webhooks/mock-payment - HTML страница
- Idempotent webhook (duplicate)

---

## Примеры использования

### Сценарий 1: Новый пользователь

```bash
# 1. Регистрация
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "user123",
    "password": "SecurePass123!",
    "full_name": "John Doe"
  }'

# Response: User created, currency_balance = 0.00

# 2. Логин
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "user123",
    "password": "SecurePass123!"
  }'

# Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}

# 3. Проверка баланса
curl -X GET http://localhost:8000/api/v1/currency/balance \
  -H "Authorization: Bearer eyJhbGci..."

# Response:
{
  "user_id": "uuid-user",
  "balance": "0.00",
  "last_updated": "2025-11-14T12:00:00Z"
}

# 4. Пополнение баланса
curl -X POST http://localhost:8000/api/v1/currency/purchase \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"amount_znc": "100.00"}'

# Response:
{
  "payment_id": "uuid-payment",
  "payment_url": "http://localhost:8000/api/v1/webhooks/mock-payment?payment_id=uuid-payment",
  "amount_znc": "100.00",
  "amount_rub": "1000.00",
  "status": "pending"
}

# 5. Переход по payment_url и оплата
# User нажимает "Successful Payment"

# 6. Проверка баланса после оплаты
curl -X GET http://localhost:8000/api/v1/currency/balance \
  -H "Authorization: Bearer eyJhbGci..."

# Response:
{
  "balance": "100.00"  # Баланс начислен!
}

# 7. Покупка токена
curl -X POST http://localhost:8000/api/v1/tokens/purchase \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{
    "duration_hours": 24,
    "scope": "full"
  }'

# Response:
{
  "id": "uuid-token",
  "token": "64-char-random-string-here",
  "duration_hours": 24,
  "scope": "full",
  "cost_znc": "18.00",
  "activated_at": null,
  "expires_at": null,
  "is_active": true
}

# 8. Проверка баланса после покупки
curl -X GET http://localhost:8000/api/v1/currency/balance \
  -H "Authorization: Bearer eyJhbGci..."

# Response:
{
  "balance": "82.00"  # 100 - 18 = 82
}

# 9. История транзакций
curl -X GET "http://localhost:8000/api/v1/currency/transactions?skip=0&limit=10" \
  -H "Authorization: Bearer eyJhbGci..."

# Response:
{
  "transactions": [
    {
      "amount": "-18.00",
      "transaction_type": "PURCHASE",
      "description": "Token purchase: 24h full access",
      "created_at": "2025-11-14T12:05:00Z"
    },
    {
      "amount": "100.00",
      "transaction_type": "DEPOSIT",
      "description": "Balance top-up via payment gateway",
      "payment_id": "uuid-payment",
      "created_at": "2025-11-14T12:00:00Z"
    }
  ],
  "total": 2
}
```

### Сценарий 2: Возврат неиспользованного токена

```bash
# 1. Покупка токена (баланс: 82 ZNC)
curl -X POST http://localhost:8000/api/v1/tokens/purchase \
  -H "Authorization: Bearer eyJhbGci..." \
  -d '{"duration_hours": 1, "scope": "full"}'

# Response: token purchased, cost_znc = 1.00, balance = 81.00

# 2. Передумали - сразу отменяем (НЕ активировали)
curl -X DELETE http://localhost:8000/api/v1/tokens/{token_id} \
  -H "Authorization: Bearer eyJhbGci..."

# Response:
{
  "message": "Token revoked successfully",
  "refund_amount": "1.00"
}

# 3. Проверка баланса
curl -X GET http://localhost:8000/api/v1/currency/balance \
  -H "Authorization: Bearer eyJhbGci..."

# Response:
{
  "balance": "82.00"  # Возврат 100%!
}

# 4. Попытка отменить АКТИВИРОВАННЫЙ токен
# (токен использовался в DTS Monaco)
curl -X DELETE http://localhost:8000/api/v1/tokens/{activated_token_id} \
  -H "Authorization: Bearer eyJhbGci..."

# Response (400 Bad Request):
{
  "detail": "Cannot revoke activated token. Refunds are only available for non-activated tokens."
}
```

### Сценарий 3: Mock testing (development)

```bash
# Быстрое пополнение баланса БЕЗ payment gateway
curl -X POST http://localhost:8000/api/v1/currency/mock-purchase \
  -H "Authorization: Bearer eyJhbGci..." \
  -d '{"amount": "1000.00"}'

# Response:
{
  "user_id": "uuid-user",
  "amount": "1000.00",
  "transaction_type": "DEPOSIT",
  "description": "Mock balance purchase (testing)"
}

# Баланс сразу начислен, без redirect на payment gateway
```

---

## Production Checklist

Перед деплоем в production:

### 1. Payment Gateway

- [ ] Заменить MockPaymentProvider на YooKassaProvider/StripeProvider
- [ ] Настроить YOOKASSA_SECRET_KEY в `.env`
- [ ] Настроить webhook URL в личном кабинете YooKassa
- [ ] Включить HMAC verification в `verify_webhook()`
- [ ] Удалить/защитить `/api/v1/currency/mock-purchase` endpoint
- [ ] Удалить/защитить `/api/v1/currency/admin/simulate-payment` endpoint
- [ ] Удалить `/api/v1/webhooks/mock-payment` endpoint

### 2. Безопасность

- [ ] Rate limiting на webhook endpoint (защита от spam)
- [ ] HTTPS для всех endpoints (SSL certificate)
- [ ] Логирование всех webhook для audit
- [ ] Мониторинг failed payments
- [ ] Alerts для duplicate/suspicious webhooks

### 3. База данных

- [ ] Index на `transactions.user_id` (если много транзакций)
- [ ] Index на `transactions.payment_id` (для идемпотентности)
- [ ] Partition на `transactions` table (по месяцам, если >10M записей)
- [ ] Автоматические бэкапы PostgreSQL (ежедневно)

### 4. Redis

- [ ] Persistence (AOF или RDB) для payment metadata
- [ ] Мониторинг memory usage
- [ ] Maxmemory policy: `allkeys-lru`
- [ ] Репликация (master-slave) для high availability

### 5. Мониторинг

- [ ] Prometheus metrics: payment_created, payment_succeeded, payment_failed
- [ ] Grafana dashboard: conversion rate, avg payment amount
- [ ] Sentry для webhook errors
- [ ] Email alerts для critical failures

### 6. Тестирование

- [ ] Load testing webhook endpoint (10k+ requests/sec)
- [ ] Chaos engineering: Redis down во время webhook
- [ ] Concurrent payment stress test (1000 users)
- [ ] Refund abuse testing (злоумышленник)

---

## Миграция из Phase 1

Если у вас есть существующая база данных с Phase 1:

### Шаг 1: Backup

```bash
# PostgreSQL backup
pg_dump zenzefi_dev > backup_phase1.sql
```

### Шаг 2: Миграция

```bash
# Применить миграцию
cd zenzefi_backend
poetry run alembic upgrade head
```

**Миграция добавит:**
- `users.currency_balance` column (default=0.00)
- `transactions` table
- Indexes

### Шаг 3: Начисление начального баланса (опционально)

```python
# scripts/grant_initial_balance.py
from app.core.database import SessionLocal
from app.services.currency_service import CurrencyService
from app.models.user import User
from decimal import Decimal

db = SessionLocal()
users = db.query(User).all()

for user in users:
    # Начислить 100 ZNC всем существующим пользователям
    CurrencyService.credit_balance(
        user_id=user.id,
        amount=Decimal("100.00"),
        description="Initial balance grant (Phase 2 migration)",
        payment_id=None,
        db=db
    )
    print(f"Granted 100 ZNC to {user.username}")

db.close()
```

### Шаг 4: Обновление существующих токенов

Существующие токены из Phase 1 **продолжают работать** без изменений:
- `cost_znc` property вычисляется динамически
- Старые токены имеют `activated_at=None` (можно вернуть)
- Новые токены требуют баланс

---

## FAQ

### Q: Можно ли изменить цены токенов?

**A:** Да, просто измените значения в `.env`:

```bash
TOKEN_PRICE_1H=2.00
TOKEN_PRICE_24H=30.00
```

Существующие токены сохранят старую цену (она не хранится в БД).

### Q: Что если пользователь оплатил, но webhook не пришёл?

**A:** В production:
1. YooKassa повторяет webhook до 10 раз (exponential backoff)
2. Можно вручную проверить статус платежа через YooKassa API
3. Admin endpoint для ручного начисления: `POST /admin/manual-credit`

### Q: Можно ли частичный refund для активированных токенов?

**A:** В текущей версии - нет. Но можно добавить:

```python
# В TokenService.revoke_token()
if db_token.activated_at:
    # Partial refund logic
    time_used = (now - db_token.activated_at).total_seconds() / 3600
    time_unused = max(0, db_token.duration_hours - time_used)
    refund_amount = cost * (time_unused / db_token.duration_hours)
```

### Q: Как защититься от злоупотреблений (токен → возврат → токен)?

**A:** Варианты:
1. Текущий подход: возврат только для неактивированных
2. Лимит на количество refund в месяц (например, max 3)
3. Fee за refund (возврат 90% вместо 100%)
4. Cooldown период (нельзя купить снова в течение 24ч после refund)

### Q: Decimal vs Float - почему важно?

**A:** Пример проблемы с float:

```python
# ❌ Float
balance = 0.1 + 0.2  # 0.30000000000000004
if balance == 0.3:   # False!
    print("Equal")

# ✅ Decimal
balance = Decimal("0.1") + Decimal("0.2")  # Decimal("0.3")
if balance == Decimal("0.3"):  # True!
    print("Equal")
```

Для денег ВСЕГДА используйте Decimal!

---

## Заключение

Phase 2 реализует полноценную систему монетизации с:
- ✅ Внутренней валютой ZNC
- ✅ Покупкой токенов за баланс
- ✅ Возвратами за неиспользованные токены
- ✅ Mock payment gateway для development
- ✅ Полной историей транзакций
- ✅ 148 тестами (85%+ coverage)

**Следующий этап:** Phase 3 - Monitoring (ProxySession tracking, admin endpoints, analytics)

**Документация актуальна на:** 2025-11-14
**Версия:** v0.4.0-beta
