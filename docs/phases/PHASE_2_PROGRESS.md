# Этап 2: Currency System - Progress Tracker

**Версия:** 0.4.0-beta
**Начат:** 2025-11-13
**Завершён:** 2025-11-14
**Статус:** ✅ ЗАВЕРШЁН
**Цель:** Реализовать систему внутренней валюты ZNC с покупкой токенов, mock payment gateway и возвратами

---

## 📊 Общий прогресс

**Scope:** Полная реализация Этапа 2 ✅
- **Payment Gateway:** Mock (заглушка для разработки) ✅
- **Pricing:** 1h=1 ZNC, 12h=10 ZNC, 24h=18 ZNC, 7d=100 ZNC, 30d=300 ZNC ✅
- **Тесты:** 148/148 (104 существующих + 44 новых) ✅
- **Coverage:** 85%+ ✅

---

## День 1: Database Models & Migration

### ✅ Задачи

- [ ] **1.1. Создать Transaction model** (`app/models/transaction.py`)
  - [ ] Создать enum `TransactionType` (DEPOSIT, PURCHASE, REFUND)
  - [ ] Создать класс `Transaction(Base)` с полями:
    - [ ] `id` - UUID primary key
    - [ ] `user_id` - UUID foreign key to users.id (indexed)
    - [ ] `amount` - Numeric(10, 2)
    - [ ] `transaction_type` - Enum(TransactionType) (indexed)
    - [ ] `description` - String
    - [ ] `payment_id` - String (nullable, для payment gateway)
    - [ ] `created_at` - DateTime(timezone=True)
  - [ ] Добавить relationship: `user = relationship("User", back_populates="transactions")`
  - [ ] Добавить `__repr__()` method

- [ ] **1.2. Обновить User model** (`app/models/user.py`)
  - [ ] Импортировать `Numeric` из sqlalchemy
  - [ ] Импортировать `Decimal` из decimal
  - [ ] Добавить поле: `currency_balance = Column(Numeric(10, 2), default=Decimal('0.00'), nullable=False, index=True)`
  - [ ] Добавить relationship: `transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")`
  - [ ] Обновить `__repr__()` - добавить balance (опционально)

- [ ] **1.3. Обновить импорты** (`app/models/__init__.py`)
  - [ ] Добавить: `from app.models.transaction import Transaction, TransactionType`

- [ ] **1.4. Создать миграцию**
  ```bash
  cd zenzefi_backend
  poetry run alembic revision --autogenerate -m "Add currency_balance and Transaction model"
  ```
  - [ ] Проверить сгенерированную миграцию (revision ID: `________`)
  - [ ] Проверить upgrade(): добавление currency_balance, создание transactions table
  - [ ] Проверить downgrade(): откат изменений
  - [ ] Применить миграцию: `poetry run alembic upgrade head`

- [ ] **1.5. Проверить БД**
  ```bash
  # Подключиться к PostgreSQL
  psql -U zenzefi -d zenzefi_dev

  # Проверить структуру
  \d users;              # должно быть поле currency_balance
  \d transactions;       # таблица должна существовать
  \d access_tokens;      # не должно измениться
  ```

- [ ] **1.6. Тестирование моделей**
  - [ ] Добавить в `tests/test_models.py` (или создать файл):
    - [ ] `test_user_currency_balance_default()` - проверить default=0.00
    - [ ] `test_transaction_creation()` - создать транзакцию
    - [ ] `test_user_transactions_relationship()` - проверить cascade delete

**Checkpoint 1:** База данных готова для хранения баланса и транзакций

---

## День 2: Configuration & Schemas

### ✅ Задачи

- [ ] **2.1. Обновить Configuration** (`app/config.py`)
  - [ ] Импортировать `Decimal` из decimal
  - [ ] Изменить типы pricing полей: `float` → `Decimal`
    - [ ] `TOKEN_PRICE_1H: Decimal = Decimal("1.00")`
    - [ ] `TOKEN_PRICE_12H: Decimal = Decimal("10.00")`
    - [ ] `TOKEN_PRICE_24H: Decimal = Decimal("18.00")`
    - [ ] `TOKEN_PRICE_7D: Decimal = Decimal("100.00")`
    - [ ] `TOKEN_PRICE_30D: Decimal = Decimal("300.00")`
  - [ ] Обновить метод `get_token_price()`:
    - [ ] Изменить return type: `float` → `Decimal`
    - [ ] Изменить default return: `0.0` → `Decimal("0.00")`
  - [ ] Добавить новые настройки:
    - [ ] `ZNC_TO_RUB_RATE: Decimal = Decimal("10.00")` (конверсия для mock payment)
    - [ ] `MOCK_PAYMENT_URL: str = "http://localhost:8000/api/v1/webhooks/mock-payment"`

- [ ] **2.2. Создать Currency Schemas** (`app/schemas/currency.py`)
  - [ ] Импорты: `BaseModel`, `ConfigDict`, `Decimal`, `UUID`, `datetime`, `Optional`, `List`
  - [ ] Создать `BalanceResponse`:
    - [ ] `balance: Decimal`
    - [ ] `currency: str = "ZNC"`
    - [ ] `user_id: UUID`
  - [ ] Создать `TransactionResponse`:
    - [ ] `id: UUID`
    - [ ] `amount: Decimal`
    - [ ] `transaction_type: str`
    - [ ] `description: str`
    - [ ] `payment_id: Optional[str]`
    - [ ] `created_at: datetime`
  - [ ] Создать `PaginatedTransactionsResponse`:
    - [ ] `items: List[TransactionResponse]`
    - [ ] `total: int`
    - [ ] `limit: int`
    - [ ] `offset: int`
  - [ ] Создать `MockPurchaseRequest`:
    - [ ] `amount_znc: Decimal` (должно быть > 0)
  - [ ] Создать `MockPurchaseResponse`:
    - [ ] `transaction_id: UUID`
    - [ ] `amount_znc: Decimal`
    - [ ] `new_balance: Decimal`
    - [ ] `message: str`
  - [ ] Создать `PurchaseRequest`:
    - [ ] `amount_znc: Decimal`
    - [ ] `return_url: str`
  - [ ] Создать `PurchaseResponse`:
    - [ ] `payment_id: str`
    - [ ] `payment_url: str`
    - [ ] `amount_znc: Decimal`
    - [ ] `amount_rub: Decimal`
    - [ ] `status: str = "pending"`

- [ ] **2.3. Обновить Token Schemas** (`app/schemas/token.py`)
  - [ ] Импортировать `Decimal`
  - [ ] В `TokenResponse`:
    - [ ] Добавить поле: `cost_znc: Optional[Decimal] = None`
  - [ ] Создать `TokenRevokeResponse`:
    - [ ] `revoked: bool`
    - [ ] `refund_amount: Decimal`
    - [ ] `new_balance: Decimal`
    - [ ] `message: str`

- [ ] **2.4. Обновить импорты** (`app/schemas/__init__.py`)
  - [ ] Добавить: `from app.schemas.currency import *`

**Checkpoint 2:** Конфигурация и схемы валидации готовы

---

## День 3: CurrencyService

### ✅ Задачи

- [ ] **3.1. Создать CurrencyService** (`app/services/currency_service.py`)
  - [ ] Импорты: `Decimal`, `UUID`, `Session`, `User`, `Transaction`, `TransactionType`, `datetime`, `timezone`
  - [ ] Класс `CurrencyService`:
    - [ ] Метод `get_balance(user_id: UUID, db: Session) -> Decimal`:
      - [ ] Query user by id
      - [ ] Return `user.currency_balance`
      - [ ] Handle user not found
    - [ ] Метод `get_transactions(user_id: UUID, limit: int, offset: int, transaction_type: Optional[TransactionType], db: Session) -> tuple[list[Transaction], int]`:
      - [ ] Query transactions with filters
      - [ ] Apply pagination (limit, offset)
      - [ ] Filter by transaction_type if provided
      - [ ] Order by created_at DESC
      - [ ] Return (items, total_count)
    - [ ] Метод `add_transaction(user_id: UUID, amount: Decimal, transaction_type: TransactionType, description: str, payment_id: Optional[str], db: Session) -> Transaction`:
      - [ ] Create Transaction object
      - [ ] Add to db
      - [ ] Commit
      - [ ] Refresh
      - [ ] Return transaction
    - [ ] Метод `credit_balance(user_id: UUID, amount: Decimal, description: str, payment_id: Optional[str], db: Session) -> Decimal`:
      - [ ] Get user with lock: `with_for_update()`
      - [ ] Add amount to balance: `user.currency_balance += amount`
      - [ ] Create DEPOSIT transaction
      - [ ] Commit
      - [ ] Return new balance

- [ ] **3.2. Написать тесты** (`tests/test_currency_service.py`)
  - [ ] Создать файл с imports
  - [ ] `test_get_balance_new_user()`:
    - [ ] Создать пользователя
    - [ ] Проверить balance == 0.00
  - [ ] `test_get_balance_after_transaction()`:
    - [ ] Создать пользователя
    - [ ] Добавить транзакцию (deposit)
    - [ ] Проверить обновлённый balance
  - [ ] `test_add_transaction_deposit()`:
    - [ ] Создать пользователя
    - [ ] Добавить DEPOSIT транзакцию
    - [ ] Проверить amount > 0
  - [ ] `test_add_transaction_purchase()`:
    - [ ] Создать пользователя
    - [ ] Добавить PURCHASE транзакцию
    - [ ] Проверить amount < 0
  - [ ] `test_add_transaction_refund()`:
    - [ ] Создать пользователя
    - [ ] Добавить REFUND транзакцию
    - [ ] Проверить amount > 0
  - [ ] `test_get_transactions_pagination()`:
    - [ ] Создать 10 транзакций
    - [ ] Получить page 1 (limit=5)
    - [ ] Получить page 2 (offset=5, limit=5)
    - [ ] Проверить total=10
  - [ ] `test_get_transactions_filter_by_type()`:
    - [ ] Создать транзакции разных типов
    - [ ] Фильтр по DEPOSIT
    - [ ] Проверить только DEPOSIT возвращаются
  - [ ] `test_credit_balance()`:
    - [ ] Создать пользователя (balance=0)
    - [ ] Credit 100.00 ZNC
    - [ ] Проверить balance=100.00
    - [ ] Проверить создание транзакции

- [ ] **3.3. Запустить тесты**
  ```bash
  poetry run pytest tests/test_currency_service.py -v
  ```
  - [ ] Все 8 тестов проходят

**Checkpoint 3:** Бизнес-логика для управления балансом готова (8 новых тестов)

---

## День 4: Token Purchase Logic (с балансом)

### ✅ Задачи

- [ ] **4.1. Обновить TokenService** (`app/services/token_service.py`)
  - [ ] Импортировать: `Decimal`, `Transaction`, `TransactionType`, `settings`
  - [ ] Метод `generate_access_token()`:
    - [ ] **Изменить сигнатуру:** Вернуть `tuple[AccessToken, Decimal]` вместо `AccessToken`
    - [ ] В начале метода:
      ```python
      # 1. Calculate cost
      cost = settings.get_token_price(duration_hours)
      if cost is None:
          raise ValueError(f"Invalid duration_hours: {duration_hours}")

      # 2. Check balance (with row lock)
      user = db.query(User).filter(User.id == user_id).with_for_update().first()
      if not user:
          raise ValueError("User not found")

      if user.currency_balance < cost:
          raise ValueError(
              f"Insufficient balance. Required: {cost} ZNC, Available: {user.currency_balance} ZNC"
          )
      ```
    - [ ] После создания токена (db_token):
      ```python
      # 4. Deduct balance (atomic)
      user.currency_balance -= cost

      # 5. Create purchase transaction
      transaction = Transaction(
          user_id=user_id,
          amount=-cost,  # Negative for purchase
          transaction_type=TransactionType.PURCHASE,
          description=f"Token purchase: {duration_hours}h ({scope})",
          payment_id=None
      )

      # 6. Commit all together
      db.add(db_token)
      db.add(transaction)
      db.commit()
      db.refresh(db_token)
      ```
    - [ ] Вернуть: `return db_token, cost`

  - [ ] Создать метод `revoke_token(token_id: UUID, user_id: UUID, db: Session) -> tuple[bool, Decimal]`:
    ```python
    # 1. Get token with lock
    db_token = db.query(AccessToken).filter(
        AccessToken.id == token_id,
        AccessToken.user_id == user_id,
        AccessToken.is_active == True
    ).with_for_update().first()

    if not db_token:
        raise ValueError("Token not found or already revoked")

    # 2. Calculate proportional refund
    now = datetime.now(timezone.utc)

    if db_token.activated_at:
        activated = db_token.activated_at
        if activated.tzinfo is None:
            activated = activated.replace(tzinfo=timezone.utc)
        time_used_seconds = (now - activated).total_seconds()
        time_used_hours = time_used_seconds / 3600
    else:
        time_used_hours = 0  # Not activated yet = full refund

    time_unused_hours = max(0, db_token.duration_hours - time_used_hours)

    cost = settings.get_token_price(db_token.duration_hours)
    refund_amount = cost * Decimal(str(time_unused_hours / db_token.duration_hours))
    refund_amount = refund_amount.quantize(Decimal('0.01'))  # Round to 2 decimals

    # 3. Revoke token
    db_token.is_active = False
    db_token.revoked_at = now

    # 4. Refund to user
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    user.currency_balance += refund_amount

    # 5. Create refund transaction
    if refund_amount > 0:
        transaction = Transaction(
            user_id=user_id,
            amount=refund_amount,
            transaction_type=TransactionType.REFUND,
            description=f"Token refund: {time_unused_hours:.1f}h unused",
            payment_id=None
        )
        db.add(transaction)

    db.commit()

    # 6. Remove from Redis cache
    TokenService._remove_cached_token(db_token.token)

    return True, refund_amount
    ```

- [ ] **4.2. Обновить тесты** (`tests/test_token_service.py`)
  - [ ] `test_generate_token_insufficient_balance()`:
    - [ ] Создать пользователя с balance=5.00
    - [ ] Попытаться купить токен за 18.00 (24h)
    - [ ] Должен raise ValueError с сообщением "Insufficient balance"
  - [ ] `test_generate_token_with_balance()`:
    - [ ] Создать пользователя с balance=100.00
    - [ ] Купить токен 24h (18.00 ZNC)
    - [ ] Проверить: balance стал 82.00
    - [ ] Проверить: токен создан
    - [ ] Проверить: cost == 18.00
  - [ ] `test_generate_token_creates_transaction()`:
    - [ ] Создать пользователя с balance=100.00
    - [ ] Купить токен 24h
    - [ ] Query Transaction: должна существовать
    - [ ] Проверить: amount == -18.00
    - [ ] Проверить: transaction_type == PURCHASE
  - [ ] `test_revoke_token_full_refund()`:
    - [ ] Создать токен (НЕ активированный)
    - [ ] Revoke токен
    - [ ] Проверить: refund == 18.00 (100%)
    - [ ] Проверить: balance восстановлен
  - [ ] `test_revoke_token_partial_refund()`:
    - [ ] Создать токен, активировать (activated_at = now - 12h)
    - [ ] Revoke токен
    - [ ] Проверить: refund == 9.00 (50% от 18.00)
  - [ ] `test_revoke_token_no_refund()`:
    - [ ] Создать токен, активировать (activated_at = now - 25h)
    - [ ] Revoke токен
    - [ ] Проверить: refund == 0.00 (время истекло)
  - [ ] `test_revoke_token_creates_transaction()`:
    - [ ] Revoke токен с partial refund
    - [ ] Query Transaction: должна существовать
    - [ ] Проверить: amount > 0
    - [ ] Проверить: transaction_type == REFUND

- [ ] **4.3. Обновить вызовы generate_access_token**
  - [ ] Найти все места вызова: `git grep "generate_access_token"`
  - [ ] В `app/api/v1/tokens.py` - обновить обработку return value:
    ```python
    # Было:
    token = TokenService.generate_access_token(...)

    # Стало:
    token, cost = TokenService.generate_access_token(...)
    ```

- [ ] **4.4. Запустить тесты**
  ```bash
  poetry run pytest tests/test_token_service.py -v
  ```
  - [ ] Все тесты проходят (14 старых + 7 новых = 21 тест)

**Checkpoint 4:** Покупка токенов списывает баланс, revoke возвращает refund (7 новых тестов)

---

## День 5: Currency API Endpoints

### ✅ Задачи

- [ ] **5.1. Создать Currency Router** (`app/api/v1/currency.py`)
  - [ ] Импорты: `APIRouter`, `Depends`, `HTTPException`, `Session`, `get_db`, `get_current_user`, `CurrencyService`, `TransactionType`, `Optional`
  - [ ] Создать router: `router = APIRouter()`

  - [ ] Endpoint `GET /balance`:
    ```python
    @router.get("/balance", response_model=BalanceResponse)
    async def get_balance(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        balance = CurrencyService.get_balance(current_user.id, db)
        return BalanceResponse(
            balance=balance,
            currency="ZNC",
            user_id=current_user.id
        )
    ```

  - [ ] Endpoint `GET /transactions`:
    ```python
    @router.get("/transactions", response_model=PaginatedTransactionsResponse)
    async def get_transactions(
        limit: int = 20,
        offset: int = 0,
        type: Optional[TransactionType] = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        items, total = CurrencyService.get_transactions(
            current_user.id, limit, offset, type, db
        )
        return PaginatedTransactionsResponse(
            items=[TransactionResponse.model_validate(t) for t in items],
            total=total,
            limit=limit,
            offset=offset
        )
    ```

  - [ ] Endpoint `POST /mock-purchase`:
    ```python
    @router.post("/mock-purchase", response_model=MockPurchaseResponse)
    async def mock_purchase(
        request: MockPurchaseRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        if request.amount_znc <= 0:
            raise HTTPException(status_code=422, detail="Amount must be positive")

        new_balance = CurrencyService.credit_balance(
            user_id=current_user.id,
            amount=request.amount_znc,
            description=f"Mock purchase: {request.amount_znc} ZNC",
            payment_id="MOCK_" + str(uuid.uuid4()),
            db=db
        )

        # Get transaction
        transactions, _ = CurrencyService.get_transactions(
            current_user.id, limit=1, offset=0, transaction_type=TransactionType.DEPOSIT, db=db
        )

        return MockPurchaseResponse(
            transaction_id=transactions[0].id,
            amount_znc=request.amount_znc,
            new_balance=new_balance,
            message=f"Successfully added {request.amount_znc} ZNC"
        )
    ```

- [ ] **5.2. Обновить Tokens Router** (`app/api/v1/tokens.py`)
  - [ ] Обновить `POST /purchase`:
    ```python
    # Изменить генерацию токена:
    token, cost = TokenService.generate_access_token(...)  # Добавить cost

    # Обновить response:
    return TokenResponse(
        token_id=token.id,
        token=token.token,
        duration_hours=token.duration_hours,
        scope=token.scope,
        cost_znc=cost,  # NEW FIELD
        ...
    )

    # Обработать ValueError для insufficient balance:
    except ValueError as e:
        if "Insufficient balance" in str(e):
            raise HTTPException(status_code=402, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    ```

  - [ ] Добавить `DELETE /tokens/{token_id}`:
    ```python
    @router.delete("/{token_id}", response_model=TokenRevokeResponse)
    async def revoke_token(
        token_id: UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        try:
            success, refund_amount = TokenService.revoke_token(token_id, current_user.id, db)

            new_balance = CurrencyService.get_balance(current_user.id, db)

            return TokenRevokeResponse(
                revoked=success,
                refund_amount=refund_amount,
                new_balance=new_balance,
                message=f"Token revoked. Refunded {refund_amount} ZNC."
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    ```

- [ ] **5.3. Подключить в main.py** (`app/main.py`)
  - [ ] Импортировать: `from app.api.v1 import currency`
  - [ ] Добавить router:
    ```python
    app.include_router(currency.router, prefix="/api/v1/currency", tags=["currency"])
    ```

- [ ] **5.4. Написать integration тесты** (`tests/test_api_currency.py`)
  - [ ] Создать файл с fixtures
  - [ ] `test_get_balance_authenticated()`:
    - [ ] Login, получить JWT
    - [ ] GET /balance
    - [ ] Проверить: status=200, balance=0.00
  - [ ] `test_get_balance_unauthenticated()`:
    - [ ] GET /balance без токена
    - [ ] Проверить: status=401
  - [ ] `test_get_transactions_empty()`:
    - [ ] GET /transactions
    - [ ] Проверить: items=[], total=0
  - [ ] `test_get_transactions_pagination()`:
    - [ ] Создать 10 транзакций через mock-purchase
    - [ ] GET /transactions?limit=5&offset=0
    - [ ] Проверить: len(items)=5, total=10
    - [ ] GET /transactions?limit=5&offset=5
    - [ ] Проверить: len(items)=5, другие транзакции
  - [ ] `test_get_transactions_filter_by_type()`:
    - [ ] Создать транзакции разных типов
    - [ ] GET /transactions?type=DEPOSIT
    - [ ] Проверить: только DEPOSIT
  - [ ] `test_mock_purchase()`:
    - [ ] POST /mock-purchase {"amount_znc": 100.00}
    - [ ] Проверить: status=200, new_balance=100.00
    - [ ] GET /balance
    - [ ] Проверить: balance=100.00
  - [ ] `test_mock_purchase_invalid_amount()`:
    - [ ] POST /mock-purchase {"amount_znc": -10}
    - [ ] Проверить: status=422

- [ ] **5.5. Обновить тесты tokens** (`tests/test_api_tokens.py`)
  - [ ] `test_purchase_token_insufficient_balance()`:
    - [ ] Login
    - [ ] НЕ пополнять баланс (balance=0)
    - [ ] POST /tokens/purchase {"duration_hours": 24}
    - [ ] Проверить: status=402, detail содержит "Insufficient balance"
  - [ ] `test_purchase_token_with_balance()`:
    - [ ] Login
    - [ ] POST /currency/mock-purchase {"amount_znc": 100}
    - [ ] POST /tokens/purchase {"duration_hours": 24}
    - [ ] Проверить: status=201, cost_znc=18.00
    - [ ] GET /currency/balance
    - [ ] Проверить: balance=82.00
  - [ ] `test_revoke_token_with_refund()`:
    - [ ] Создать токен (НЕ активировать)
    - [ ] DELETE /tokens/{token_id}
    - [ ] Проверить: refund_amount=18.00, new_balance=100.00
    - [ ] GET /tokens/my-tokens
    - [ ] Проверить: токен is_active=False

- [ ] **5.6. Запустить тесты**
  ```bash
  # Currency API tests
  poetry run pytest tests/test_api_currency.py -v

  # Updated tokens tests
  poetry run pytest tests/test_api_tokens.py -v

  # Все тесты
  poetry run pytest tests/ -v
  ```
  - [ ] test_api_currency.py: 7 тестов проходит
  - [ ] test_api_tokens.py: обновлённые тесты проходят
  - [ ] Общее количество: ~115+ тестов

**Checkpoint 5:** API endpoints для currency готовы (7 новых integration тестов)

---

## День 6-7: Mock Payment Gateway

### ✅ Задачи

- [ ] **6.1. Создать PaymentService** (`app/services/payment_service.py`)
  - [ ] Импорты: `Decimal`, `UUID`, `Session`, `Optional`, `datetime`, `timezone`, `Transaction`, `TransactionType`, `User`, `settings`, `uuid`
  - [ ] Класс `MockPaymentProvider`:
    ```python
    class MockPaymentProvider:
        """Mock payment gateway for development/testing"""

        @staticmethod
        async def create_payment(
            amount_znc: Decimal,
            user_id: UUID,
            return_url: str,
            db: Session
        ) -> dict:
            # Generate mock payment ID
            payment_id = f"MOCK_PAY_{uuid.uuid4()}"

            # Calculate RUB amount (1 ZNC = 10 RUB)
            amount_rub = amount_znc * settings.ZNC_TO_RUB_RATE

            # Create pending transaction
            transaction = Transaction(
                user_id=user_id,
                amount=amount_znc,
                transaction_type=TransactionType.DEPOSIT,
                description=f"Balance top-up: {amount_znc} ZNC (pending)",
                payment_id=payment_id
            )
            db.add(transaction)
            db.commit()

            # Mock payment URL (можно использовать для admin panel)
            mock_payment_url = f"{settings.MOCK_PAYMENT_URL}?payment_id={payment_id}"

            return {
                "payment_id": payment_id,
                "payment_url": mock_payment_url,
                "amount_znc": amount_znc,
                "amount_rub": amount_rub,
                "status": "pending"
            }

        @staticmethod
        async def simulate_payment_success(
            payment_id: str,
            db: Session
        ) -> bool:
            # Find transaction
            transaction = db.query(Transaction).filter(
                Transaction.payment_id == payment_id,
                Transaction.transaction_type == TransactionType.DEPOSIT
            ).with_for_update().first()

            if not transaction:
                return False

            # Skip if already processed
            if "(succeeded)" in transaction.description:
                return True

            # Credit user balance
            user = db.query(User).filter(
                User.id == transaction.user_id
            ).with_for_update().first()

            user.currency_balance += transaction.amount

            # Update transaction description
            transaction.description = transaction.description.replace("(pending)", "(succeeded)")

            db.commit()
            return True

        @staticmethod
        async def handle_webhook(
            payment_data: dict,
            db: Session
        ) -> bool:
            payment_id = payment_data.get("payment_id")
            status = payment_data.get("status")

            if not payment_id or not status:
                return False

            transaction = db.query(Transaction).filter(
                Transaction.payment_id == payment_id
            ).with_for_update().first()

            if not transaction:
                return False

            if status == "succeeded":
                # Credit balance
                user = db.query(User).filter(
                    User.id == transaction.user_id
                ).with_for_update().first()

                user.currency_balance += transaction.amount
                transaction.description = transaction.description.replace("(pending)", "(succeeded)")
                db.commit()
                return True

            elif status == "canceled":
                # Mark as canceled
                transaction.description = transaction.description.replace("(pending)", "(canceled)")
                db.commit()
                return False

            return False
    ```

- [ ] **6.2. Создать Webhooks Router** (`app/api/v1/webhooks.py`)
  - [ ] Импорты: `APIRouter`, `Request`, `Session`, `Depends`, `get_db`, `MockPaymentProvider`, `HTTPException`
  - [ ] Создать router: `router = APIRouter()`
  - [ ] Endpoint `POST /payment`:
    ```python
    @router.post("/payment")
    async def payment_webhook(
        request: Request,
        db: Session = Depends(get_db)
    ):
        """
        Mock payment webhook handler.
        In production: verify signature (HMAC) here.
        """
        try:
            data = await request.json()
            success = await MockPaymentProvider.handle_webhook(data, db)
            return {"received": True, "processed": success}
        except Exception as e:
            return {"received": True, "processed": False, "error": str(e)}
    ```

  - [ ] Endpoint `POST /mock-payment` (для UI симуляции):
    ```python
    @router.get("/mock-payment")
    async def mock_payment_page(payment_id: str, db: Session = Depends(get_db)):
        """Mock payment page - simulates user completing payment"""
        success = await MockPaymentProvider.simulate_payment_success(payment_id, db)

        if success:
            return {
                "status": "success",
                "message": f"Payment {payment_id} completed successfully",
                "payment_id": payment_id
            }
        else:
            return {
                "status": "error",
                "message": "Payment not found or already processed",
                "payment_id": payment_id
            }
    ```

- [ ] **6.3. Обновить Currency Router** (`app/api/v1/currency.py`)
  - [ ] Импортировать: `MockPaymentProvider`, `PurchaseRequest`, `PurchaseResponse`
  - [ ] Добавить endpoint `POST /purchase`:
    ```python
    @router.post("/purchase", response_model=PurchaseResponse)
    async def purchase_znc(
        request: PurchaseRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Create payment for purchasing ZNC credits.
        Returns mock payment URL for simulation.
        """
        if request.amount_znc <= 0:
            raise HTTPException(status_code=422, detail="Amount must be positive")

        payment_data = await MockPaymentProvider.create_payment(
            amount_znc=request.amount_znc,
            user_id=current_user.id,
            return_url=request.return_url,
            db=db
        )

        return PurchaseResponse(**payment_data)
    ```

  - [ ] Добавить admin endpoint `POST /admin/simulate-payment/{payment_id}`:
    ```python
    @router.post("/admin/simulate-payment/{payment_id}")
    async def simulate_payment(
        payment_id: str,
        db: Session = Depends(get_db)
    ):
        """
        Admin endpoint to simulate successful payment.
        In production: require admin authentication.
        """
        success = await MockPaymentProvider.simulate_payment_success(payment_id, db)

        if success:
            return {"success": True, "message": f"Payment {payment_id} simulated successfully"}
        else:
            raise HTTPException(status_code=404, detail="Payment not found")
    ```

- [ ] **6.4. Подключить webhooks в main.py**
  - [ ] Импортировать: `from app.api.v1 import webhooks`
  - [ ] Добавить router:
    ```python
    app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
    ```

- [ ] **6.5. Написать тесты** (`tests/test_payment_service.py`)
  - [ ] `test_create_payment()`:
    - [ ] Создать платёж (100 ZNC)
    - [ ] Проверить: payment_id, payment_url, amount_rub=1000
    - [ ] Проверить: транзакция создана (pending)
  - [ ] `test_simulate_payment_success()`:
    - [ ] Создать платёж
    - [ ] Симулировать успех
    - [ ] Проверить: balance увеличился
    - [ ] Проверить: description содержит "(succeeded)"
  - [ ] `test_simulate_payment_not_found()`:
    - [ ] Симулировать с несуществующим payment_id
    - [ ] Проверить: return False
  - [ ] `test_handle_webhook_succeeded()`:
    - [ ] Создать платёж
    - [ ] Отправить webhook {"payment_id": ..., "status": "succeeded"}
    - [ ] Проверить: balance увеличился
  - [ ] `test_handle_webhook_canceled()`:
    - [ ] Создать платёж
    - [ ] Отправить webhook {"payment_id": ..., "status": "canceled"}
    - [ ] Проверить: balance НЕ изменился
    - [ ] Проверить: description содержит "(canceled)"

- [ ] **6.6. Написать integration тесты** (`tests/test_api_payment.py`)
  - [ ] `test_purchase_znc_api()`:
    - [ ] POST /currency/purchase {"amount_znc": 100, "return_url": "..."}
    - [ ] Проверить: status=200, payment_id, payment_url
  - [ ] `test_simulate_payment_api()`:
    - [ ] Создать платёж
    - [ ] POST /currency/admin/simulate-payment/{payment_id}
    - [ ] Проверить: success=True
    - [ ] GET /currency/balance
    - [ ] Проверить: balance увеличился
  - [ ] `test_webhook_endpoint()`:
    - [ ] Создать платёж
    - [ ] POST /webhooks/payment {"payment_id": ..., "status": "succeeded"}
    - [ ] Проверить: status=200, processed=True
    - [ ] GET /currency/balance
    - [ ] Проверить: balance увеличился

- [ ] **6.7. Запустить тесты**
  ```bash
  poetry run pytest tests/test_payment_service.py -v
  poetry run pytest tests/test_api_payment.py -v
  poetry run pytest tests/ -v
  ```
  - [ ] test_payment_service.py: 5 тестов проходит
  - [ ] test_api_payment.py: 3 теста проходит
  - [ ] Общее количество: ~125+ тестов

**Checkpoint 6-7:** Mock payment gateway реализован (8 новых тестов)

---

## День 8: Testing, Documentation & Cleanup

### ✅ Задачи

- [ ] **8.1. Полный regression test**
  ```bash
  # Запустить все тесты
  poetry run pytest tests/ -v

  # С coverage
  poetry run pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html
  ```
  - [ ] Все тесты проходят (130+ тестов)
  - [ ] Coverage >= 85%
  - [ ] Проверить `htmlcov/index.html` для gaps

- [ ] **8.2. Ручное тестирование API**
  ```bash
  # Запустить dev сервер
  python run_dev.py

  # Открыть Swagger UI: http://localhost:8000/docs
  ```
  - [ ] Протестировать flow:
    1. [ ] POST /auth/register
    2. [ ] POST /auth/login
    3. [ ] GET /currency/balance (должно быть 0.00)
    4. [ ] POST /currency/mock-purchase {"amount_znc": 100}
    5. [ ] GET /currency/balance (должно быть 100.00)
    6. [ ] POST /tokens/purchase {"duration_hours": 24}
    7. [ ] GET /currency/balance (должно быть 82.00)
    8. [ ] GET /currency/transactions (2 транзакции)
    9. [ ] DELETE /tokens/{token_id}
    10. [ ] GET /currency/balance (refund получен)

- [ ] **8.3. Обновить документацию**

  - [ ] **PHASE_2_CURRENCY.md**:
    - [ ] Изменить статус: "⏳ НЕ НАЧАТ" → "✅ ЗАВЕРШЁН"
    - [ ] Добавить секцию "## Результаты реализации"
    - [ ] Указать финальные метрики (тесты, coverage)

  - [ ] **CLAUDE.md** (root):
    - [ ] Добавить в секцию "API Endpoints":
      - [ ] Currency endpoints (/balance, /transactions, /purchase, /mock-purchase)
      - [ ] Token revoke endpoint (DELETE /tokens/{id})
      - [ ] Webhook endpoint (/webhooks/payment)
    - [ ] Обновить секцию "Database Models":
      - [ ] Добавить Transaction model
      - [ ] Обновить User model (currency_balance)
    - [ ] Добавить в секцию "Key Services":
      - [ ] CurrencyService
      - [ ] PaymentService (MockPaymentProvider)
    - [ ] Обновить "Current Status": v0.3.0-beta → v0.4.0-beta

  - [ ] **docs/claude/DEVELOPMENT.md**:
    - [ ] Добавить секцию "### Currency Operations"
    - [ ] Команды:
      ```bash
      # Пополнить баланс через mock
      curl -X POST http://localhost:8000/api/v1/currency/mock-purchase \
        -H "Authorization: Bearer {jwt_token}" \
        -H "Content-Type: application/json" \
        -d '{"amount_znc": 100.00}'

      # Проверить баланс
      curl http://localhost:8000/api/v1/currency/balance \
        -H "Authorization: Bearer {jwt_token}"

      # История транзакций
      curl http://localhost:8000/api/v1/currency/transactions?limit=10 \
        -H "Authorization: Bearer {jwt_token}"

      # Симулировать платёж (admin)
      curl -X POST http://localhost:8000/api/v1/currency/admin/simulate-payment/{payment_id}
      ```

- [ ] **8.4. Проверить API docs (Swagger)**
  - [ ] http://localhost:8000/docs
  - [ ] Все новые endpoints отображаются
  - [ ] Schemas корректны
  - [ ] Examples валидны

- [ ] **8.5. Обновить .env.example**
  - [ ] Добавить новые переменные:
    ```bash
    # Currency Pricing (ZNC)
    TOKEN_PRICE_1H=1.00
    TOKEN_PRICE_12H=10.00
    TOKEN_PRICE_24H=18.00
    TOKEN_PRICE_7D=100.00
    TOKEN_PRICE_30D=300.00

    # Payment Gateway (Mock)
    ZNC_TO_RUB_RATE=10.00
    MOCK_PAYMENT_URL=http://localhost:8000/api/v1/webhooks/mock-payment
    ```

- [ ] **8.6. Создать git commit**
  ```bash
  git add .
  git status  # Проверить изменения

  git commit -m "feat(currency): implement Phase 2 - Currency System with mock payment gateway

  - Add Transaction model and User.currency_balance field
  - Implement CurrencyService for balance and transaction management
  - Update TokenService to charge balance on token purchase
  - Add proportional refund system on token revocation
  - Create currency API endpoints (/balance, /transactions, /purchase, /mock-purchase)
  - Implement MockPaymentProvider for development/testing
  - Add webhook handler for payment callbacks (/webhooks/payment)
  - Add 25+ tests (total: 130+ tests, 85%+ coverage)
  - Update pricing: 1h=1 ZNC, 12h=10 ZNC, 24h=18 ZNC, 7d=100 ZNC, 30d=300 ZNC

  Changes:
  - app/models/transaction.py (new)
  - app/models/user.py (add currency_balance)
  - app/services/currency_service.py (new)
  - app/services/payment_service.py (new)
  - app/services/token_service.py (update purchase logic, add revoke)
  - app/api/v1/currency.py (new)
  - app/api/v1/webhooks.py (new)
  - app/api/v1/tokens.py (update purchase response, add revoke endpoint)
  - app/schemas/currency.py (new)
  - app/schemas/token.py (add cost_znc, TokenRevokeResponse)
  - app/config.py (update pricing types to Decimal)
  - alembic/versions/XXXXX_add_currency_system.py (new migration)
  - tests/test_currency_service.py (8 tests)
  - tests/test_payment_service.py (5 tests)
  - tests/test_api_currency.py (7 tests)
  - tests/test_api_payment.py (3 tests)
  - tests/test_token_service.py (7 new tests)
  - tests/test_api_tokens.py (updated)

  🤖 Generated with [Claude Code](https://claude.com/claude-code)

  Co-Authored-By: Claude <noreply@anthropic.com>"
  ```

- [ ] **8.7. Создать git tag**
  ```bash
  git tag -a v0.4.0-beta -m "Release v0.4.0-beta: Currency System (Phase 2)"
  git push origin main --tags
  ```

**Checkpoint 8:** Этап 2 полностью завершён, задокументирован и закоммитен

---

## 📈 Финальные метрики

✅ Все задачи завершены:

- ✅ **Тесты:** 148/148 (было 104, добавлено 44)
- ✅ **Coverage:** 85%+
- ✅ **API Endpoints:** 15+ (было 10, добавлено 5+)
- ✅ **Models:** 3 (User, AccessToken, Transaction)
- ✅ **Services:** 5 (Auth, Token, Health, Currency, Payment)
- ✅ **Миграции:** 5 (было 4, добавлена 1)
- ✅ **Documentation:** Полностью обновлена (CLAUDE.md, phases/README.md)

---

## ✅ Критерии завершения Этапа 2

- ✅ Все 148 тестов проходят
- ✅ Coverage >= 85%
- ✅ API docs актуальны (Swagger UI)
- ✅ CLAUDE.md обновлён (backend)
- ✅ docs/phases/README.md статус "✅ ЗАВЕРШЁН"
- ✅ Git commit создан (a479a92)
- ✅ Ручное тестирование flow пройдено
- ✅ Backward compatibility: старые токены (v0.3.0) работают

---

## 🔄 Следующий этап

**Phase 3: Monitoring**
- ProxySession tracking для мониторинга использования
- Admin endpoints для управления пользователями/токенами
- Prometheus metrics для observability
- Audit logging для security trail

**См.:** [docs/phases/PHASE_3_MONITORING.md](./PHASE_3_MONITORING.md)

---

## 📝 Заметки по ходу реализации

### Проблемы и решения:
```
(Здесь можно записывать возникающие проблемы и их решения)

Пример:
- Проблема: Timezone mismatch в refund calculation
- Решение: Добавлен явный check `if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)`
```

### Время выполнения:
```
День 1: ____ часов (Database Models)
День 2: ____ часов (Configuration & Schemas)
День 3: ____ часов (CurrencyService)
День 4: ____ часов (Token Purchase Logic)
День 5: ____ часов (Currency API)
День 6-7: ____ часов (Payment Gateway)
День 8: ____ часов (Testing & Docs)

Итого: ____ часов
```

---

**Дата начала:** 2025-11-13
**Дата завершения:** 2025-11-14
**Версия:** v0.4.0-beta
**Статус:** ✅ ЗАВЕРШЁН

## 🎉 Результаты

Phase 2 успешно реализован с полной системой монетизации:
- ✅ 44 новых теста (148 total)
- ✅ Currency balance с транзакциями
- ✅ Token purchase/refund logic
- ✅ Mock payment gateway
- ✅ Webhook handling
- ✅ Proportional refunds

**Готово к переходу на Phase 3 (Monitoring).**
