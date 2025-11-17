# Zenzefi Backend

**Production-Ready** сервер аутентификации и проксирования для контроля доступа к Zenzefi (Windows 11) с системой монетизации через внутреннюю валюту ZNC.

**Версия:** v0.6.0-beta
**Статус:** ✅ Production-Ready (все 4 этапа завершены)

## Технологический стек

- **Python 3.13+** - Runtime environment
- **FastAPI 0.119+** - Async web framework
- **PostgreSQL 15+** - Основная БД (SQLAlchemy 2.0 ORM)
- **Redis 7+** - Кэширование токенов, сессий, rate limiting
- **Alembic** - Миграции БД
- **Pydantic v2** - Валидация данных
- **PyJWT** - JWT токены для API аутентификации (HS256)
- **pytest** - Тестирование с реальными сервисами (174 теста, 85%+ покрытие)
- **Prometheus** - Метрики и мониторинг
- **Locust** - Load testing
- **APScheduler** - Background tasks (health checks, session cleanup)
- **Uvicorn** - ASGI сервер

## Быстрый старт

### 1. Установка зависимостей

```bash
poetry install
```

### 2. Настройка окружения

Скопируйте `.env.example` в `.env` и настройте переменные:

```bash
cp .env.example .env
```

Отредактируйте `.env` файл с вашими настройками.

**Для Claude Code (опционально):**

```bash
# Настройка MCP серверов
cp .mcp.json.example .mcp.json
# Отредактируйте .mcp.json с вашими учётными данными

# Настройка локальных разрешений Claude Code
cp .claude/settings.local.json.example .claude/settings.local.json
```

### 3. Запуск БД и Redis (Docker)

```bash
docker-compose -f docker-compose.dev.yml up -d
```

Проверка статуса:

```bash
docker-compose -f docker-compose.dev.yml ps
```

### 4. Применение миграций

```bash
poetry run alembic upgrade head
```

### 5. Запуск сервера

```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Приложение будет доступно по адресу:
- API: http://localhost:8000
- Документация (Swagger): http://localhost:8000/docs
- Документация (ReDoc): http://localhost:8000/redoc

## Основные команды

### Разработка

```bash
# Запуск dev сервера с hot reload
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Запуск БД и Redis
docker-compose -f docker-compose.dev.yml up -d

# Остановка БД и Redis
docker-compose -f docker-compose.dev.yml down

# Просмотр логов
docker-compose -f docker-compose.dev.yml logs -f
```

### Миграции базы данных

```bash
# Создать новую миграцию (autogenerate)
poetry run alembic revision --autogenerate -m "Description"

# Применить все миграции
poetry run alembic upgrade head

# Откатить последнюю миграцию
poetry run alembic downgrade -1

# Показать историю миграций
poetry run alembic history

# Показать текущую версию БД
poetry run alembic current
```

### Вспомогательные скрипты

```bash
# Инициализация БД (создание таблиц)
poetry run python scripts/init_db.py

# Создание суперпользователя
poetry run python scripts/create_superuser.py

# Создание тестовой БД
poetry run python scripts/create_test_database.py

# Тест полного flow аутентификации (регистрация, логин, создание токена)
poetry run python scripts/test_create_token.py

# Сброс БД (удаление и пересоздание всех таблиц)
poetry run python scripts/reset_database.py

# Очистка БД (удаление всех данных, но сохранение таблиц)
poetry run python scripts/clear_database.py
```

### Тестирование

```bash
# Запуск всех тестов (требуется запущенные PostgreSQL и Redis)
poetry run pytest tests/ -v

# Запуск с coverage
poetry run pytest tests/ --cov=app --cov-report=term

# Запуск с HTML coverage report
poetry run pytest tests/ --cov=app --cov-report=html

# Запуск конкретного файла тестов
poetry run pytest tests/test_api_tokens.py -v

# Запуск конкретного теста
poetry run pytest tests/test_api_tokens.py::TestTokenPurchaseEndpoint::test_purchase_token_success -v

# Параллельный запуск (быстрее)
poetry run pytest tests/ -n auto
```

**Важно:**
- Тесты требуют запущенных PostgreSQL и Redis (через `docker-compose.dev.yml`)
- Используется отдельная БД `zenzefi_test` (создаётся автоматически скриптом)
- Тесты используют **реальные сервисы**, не моки
- **174 теста, 85%+ покрытие кода**

### Load Testing

```bash
# Запуск load testing (Interactive mode с Web UI)
locust -f tests/load/locustfile.py --host http://localhost:8000
# Открыть http://localhost:8089

# Headless mode (автоматический запуск)
locust -f tests/load/locustfile.py \
    --host http://localhost:8000 \
    --users 100 \
    --spawn-rate 10 \
    --run-time 5m \
    --headless \
    --html report.html
```

**Performance Targets:**
- Throughput: 1000 req/s
- p50 latency: < 50ms
- p95 latency: < 200ms
- Error rate: < 0.1%

### Код-стайл

```bash
# Форматирование кода
poetry run black app/

# Сортировка импортов
poetry run isort app/

# Линтинг
poetry run flake8 app/

# Проверка типов
poetry run mypy app/
```

## API Endpoints

### Authentication (`/api/v1/auth`)

- `POST /register` - Регистрация нового пользователя
- `POST /login` - Логин и получение JWT токена

### Users (`/api/v1/users`)

- `GET /me` - Получить профиль текущего пользователя (требуется JWT)

### Access Tokens (`/api/v1/tokens`)

- `POST /purchase` - Создать токен доступа (требуется JWT, стоимость в ZNC)
  - Body: `{"duration_hours": 1|12|24|168|720, "scope": "full|certificates_only"}`
  - Cost: 1h=1 ZNC, 12h=10 ZNC, 24h=18 ZNC, 7d=100 ZNC, 30d=300 ZNC
  - Returns: TokenResponse с token string
- `GET /my-tokens?active_only=true` - Получить список токенов пользователя (требуется JWT)
  - Query param: `active_only` (по умолчанию: true)
- `DELETE /{token_id}` - Отозвать токен с пропорциональным возвратом ZNC (требуется JWT)

### Currency (`/api/v1/currency`)

- `GET /balance` - Получить текущий баланс ZNC (требуется JWT)
- `GET /transactions` - История транзакций с пагинацией (требуется JWT)
  - Query params: `skip`, `limit`, `transaction_type`
- `POST /mock-purchase` - Mock пополнение баланса (тестирование, требуется JWT)
  - Body: `{"amount": 100}`
- `POST /purchase` - Создать платёж для пополнения ZNC (requires JWT)
  - Body: `{"amount": 100}`
  - Returns: Payment URL для оплаты

### Admin (`/api/v1/admin`)

- `GET /users` - Список всех пользователей (требуется superuser)
  - Query params: `skip`, `limit`, `search`, `is_active`
- `PATCH /users/{user_id}` - Обновить пользователя (требуется superuser)
  - Body: `{"currency_balance": 500, "is_active": true}`
- `GET /tokens` - Список токенов по user_id (требуется superuser)
- `DELETE /tokens/{token_id}` - Force revoke без refund (требуется superuser)

### Proxy (`/api/v1/proxy`)

- `GET /status` - Проверить статус аутентификации
  - Headers: `X-Access-Token`, `X-Device-ID` (обязательно)
  - Returns: Статус токена и информация о сессии
- `ALL /{path:path}` - Проксирование HTTP запроса к Zenzefi
  - Headers: `X-Access-Token`, `X-Device-ID` (обязательно)
  - Валидирует токен, device conflict detection, scope permissions
  - Пересылает запрос на Zenzefi server

### Health & Metrics

- `GET /health` - Простая проверка здоровья (~1ms из Redis)
- `GET /metrics` - Prometheus metrics (counters, gauges, histograms)

## Структура проекта

```
zenzefi_backend/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── auth.py              # Authentication endpoints
│   │   │   ├── users.py             # User endpoints
│   │   │   ├── tokens.py            # Token endpoints
│   │   │   └── proxy.py             # Proxy endpoints (HTTP + WebSocket)
│   │   └── deps.py                  # API dependencies
│   ├── core/
│   │   ├── database.py              # Database connection
│   │   ├── redis.py                 # Redis connection
│   │   ├── security.py              # JWT, password hashing
│   │   └── logging.py               # Logging configuration
│   ├── models/
│   │   ├── user.py                  # User model
│   │   └── token.py                 # AccessToken model
│   ├── schemas/
│   │   ├── user.py                  # User schemas
│   │   ├── token.py                 # Token schemas
│   │   └── auth.py                  # Auth schemas
│   ├── services/
│   │   ├── auth_service.py          # Auth business logic
│   │   ├── token_service.py         # Token business logic
│   │   ├── proxy_service.py         # HTTP/WebSocket proxying
│   │   └── content_rewriter.py      # URL rewriting в проксированном контенте
│   ├── config.py                    # Application settings
│   └── main.py                      # FastAPI application
├── alembic/                         # Database migrations
├── scripts/                         # Helper scripts
│   ├── deploy_docker.sh             # Docker deployment script
│   ├── redis_mcp.py                 # Redis MCP server
│   └── test_create_token.py         # Test auth flow
├── tests/                           # Tests (85 тестов, 85%+ coverage)
│   ├── conftest.py                  # Test fixtures
│   ├── test_security.py             # Security tests
│   ├── test_auth_service.py         # Auth service tests
│   ├── test_token_service.py        # Token service tests
│   ├── test_api_auth.py             # Auth API tests
│   ├── test_api_tokens.py           # Token API tests
│   ├── test_cookie_auth.py          # Cookie auth tests
│   └── test_main.py                 # Main app tests
├── .mcp.json                        # MCP servers configuration
├── docker-compose.dev.yml           # Development Docker setup
├── pyproject.toml                   # Poetry dependencies
├── CLAUDE.md                        # Detailed development guide
└── README.md                        # This file
```

## Переменные окружения

См. `.env.example` для списка всех переменных.

### Обязательные:
- `SECRET_KEY` - Секретный ключ для JWT (HS256 algorithm)
- `POSTGRES_SERVER`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` - Настройки PostgreSQL
- `REDIS_HOST`, `REDIS_PORT` - Настройки Redis (по умолчанию: redis:6379)
- `ZENZEFI_TARGET_URL` - URL целевого Zenzefi сервера для проксирования
- `BACKEND_URL` - URL бэкенда для ContentRewriter (например, http://localhost:8000)

### Cookie Security:
- `COOKIE_SECURE` - HTTPS only (False для dev/HTTP, True для production/HTTPS)
- `COOKIE_SAMESITE` - Cross-site политика ("lax" для dev, "none" для production с HTTPS)
- Cookie `path` всегда `"/"` (хардкод, критично для работы браузера)
- Cookie `httponly=True` (всегда включено для XSS защиты)

### Опциональные:
- `DEBUG` - Режим отладки (по умолчанию: False)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Время жизни JWT токена (по умолчанию: 60 минут)
- `REDIS_PASSWORD` - Пароль Redis (по умолчанию: None)
- `REDIS_DB` - Номер БД Redis (по умолчанию: 0)
- `TOKEN_PRICE_*` - Цены на токены (сейчас 0.0 для MVP)

## Архитектура

### Поток запросов (Desktop Client)

```
[Desktop Client] → [FastAPI Backend] → [Zenzefi Server]
  X-Access-Token     Token Validation    Proxy Request
  X-Device-ID        Device Conflict
                     Check Session
                           ↓
                    [PostgreSQL] + [Redis Cache]
                    ProxySession tracking
```

### Два типа токенов

1. **JWT Tokens** - Для API аутентификации (register, login, purchase tokens)
   - Генерируются при логине через `/api/v1/auth/login`
   - Алгоритм: HS256 с `SECRET_KEY` из окружения
   - Payload: `{"sub": user_id, "username": username}` (НЕ email)
   - Используются в `Authorization: Bearer {token}` заголовке
   - Истекают через 60 минут (настраивается через `ACCESS_TOKEN_EXPIRE_MINUTES`)

2. **Access Tokens** - Для проксирования к Zenzefi серверу
   - Генерируются через `/api/v1/tokens/purchase` (требуется JWT auth, стоимость в ZNC)
   - Формат: 64-символьная URL-safe случайная строка (`secrets.token_urlsafe(48)`)
   - НЕ JWT - простые случайные токены в PostgreSQL
   - Допустимые длительности: 1, 12, 24, 168 (неделя), 720 (месяц) часов
   - Scope: `full` (все endpoints) или `certificates_only` (только /certificates/*)
   - Двухуровневая валидация: Redis кэш (~1мс) → PostgreSQL (~10мс)
   - **"1 token = 1 device" policy:** Device conflict detection через X-Device-ID header

### Методы аутентификации

1. **JWT Authentication** - Для API endpoints (Authorization: Bearer token)
2. **X-Access-Token Header** - Для proxy requests (с обязательным X-Device-ID)

## ✅ Реализованные возможности

### Phase 1: MVP ✅ ЗАВЕРШЁН (v0.3.0-beta)

**Базовая функциональность:**
- ✅ Регистрация и аутентификация пользователей (JWT)
- ✅ JWT токены для API доступа (60 минут lifetime)
- ✅ Создание access tokens (64-char random strings)
- ✅ Двухуровневое кэширование токенов (Redis ~1ms → PostgreSQL ~10ms)
- ✅ HTTP проксирование к Zenzefi серверу
- ✅ Scope-based access control (full / certificates_only)
- ✅ Health check system (PostgreSQL, Redis, Zenzefi)
- ✅ Background scheduler (APScheduler)
- ✅ MCP серверы (PostgreSQL, Docker, Redis, API)

### Phase 2: Система валюты ✅ ЗАВЕРШЁН (v0.4.0-beta)

**Монетизация:**
- ✅ Внутренняя валюта ZNC (Zenzefi Credits)
- ✅ Transaction model (DEPOSIT, PURCHASE, REFUND types)
- ✅ Mock payment gateway (YooKassa/Stripe в production)
- ✅ Покупка токенов за ZNC (1h=1, 12h=10, 24h=18, 7d=100, 30d=300 ZNC)
- ✅ Пропорциональный refund при revoke токена
- ✅ Currency API endpoints (balance, transactions, purchase)
- ✅ Webhook handler для payment gateway

### Phase 3: Мониторинг ✅ ЗАВЕРШЁН (v0.5.0-beta)

**Трекинг и управление:**
- ✅ ProxySession tracking (IP, user_agent, bytes, requests)
- ✅ Device conflict detection ("1 token = 1 device" policy)
- ✅ Session timeout (5 минут inactivity, auto-cleanup каждые 2 минуты)
- ✅ Admin API endpoints (users, tokens management)
- ✅ Audit logging system (actions, resources, IP tracking)
- ✅ Health checks с background scheduler (50s interval)

### Phase 4: Production Readiness ✅ ЗАВЕРШЁН (v0.6.0-beta)

**Production инфраструктура:**
- ✅ Rate Limiting middleware (Redis sliding window, 3 limit types)
- ✅ CI/CD Pipeline (GitHub Actions: test + deploy workflows)
- ✅ Prometheus metrics endpoint (/metrics с counters, gauges, histograms)
- ✅ Automated backups (PostgreSQL daily backup + restore scripts)
- ✅ Load testing suite (Locust с realistic user workflows)
- ✅ 174 теста с реальными сервисами (85%+ покрытие)

**Итого:** ✅ Все 4 этапа завершены, система готова к production deployment!

## 💡 Будущие возможности (Optional)

### Phase 2.5: Token Bundles & Referrals
- Пакетные предложения со скидками
- Реферальная система с бонусами
- GET /api/v1/bundles, POST /api/v1/bundles/{id}/purchase

### Phase 3.5: Usage Analytics
- Статистика использования по пользователям
- Global stats для админов
- Period filtering (day, week, month)

### Phase 4.5: Notification System
- Email notifications (token expiring, balance low)
- Webhook notifications с HMAC verification
- Background notification tasks

## Production Deployment

### 🐳 Docker Deployment (Рекомендуется)

Самый простой и быстрый способ - используйте Docker:

```bash
# Скачать скрипт
wget https://raw.githubusercontent.com/yourusername/zenzefi_backend/main/scripts/deploy_docker.sh

# Запустить (требуется root)
sudo bash deploy_docker.sh
```

**Преимущества Docker:**
- ⚡ Установка за 5-10 минут
- 📦 Всё в контейнерах (PostgreSQL, Redis, Backend, Nginx)
- 🔒 Автоматический SSL через Let's Encrypt
- 🔄 Легкие обновления и откаты
- 💾 Автоматические backup

### 📦 Native Installation

Классическая установка без Docker:

```bash
# Скачать скрипт
wget https://raw.githubusercontent.com/yourusername/zenzefi_backend/main/scripts/deploy.sh

# Запустить (требуется root)
sudo bash deploy.sh
```

Установит:
- PostgreSQL 15 (native)
- Redis (native)
- Python 3.11 + Poetry
- Nginx с SSL/TLS (Let's Encrypt)
- Systemd service
- Backup скрипт

### 📚 Документация

- **[docs/DEPLOYMENT_TAILSCALE.md](./docs/DEPLOYMENT_TAILSCALE.md)** - 🐳 Docker deployment с Tailscale VPN (рекомендуется)
- **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)** - 📦 Native installation
- **[CLAUDE.md](./CLAUDE.md)** - Документация для разработки

### После установки

1. Обновите `.env` с вашими настройками:
   ```bash
   sudo nano /home/zenzefi/apps/zenzefi_backend/.env
   ```

2. Перезапустите сервис:
   ```bash
   sudo systemctl restart zenzefi-backend
   ```

3. Проверьте статус:
   ```bash
   sudo systemctl status zenzefi-backend
   ```

4. API будет доступен по адресу: `https://api.yourdomain.com`

## Разработка

Для получения подробной информации о разработке см. [CLAUDE.md](./CLAUDE.md)

## Лицензия

Proprietary - Все права защищены