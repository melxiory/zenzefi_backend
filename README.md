# Zenzefi Backend

Сервер аутентификации и проксирования для контроля доступа к Zenzefi (Windows 11) по временным токенам.

## Технологический стек

- **FastAPI 0.104+** - async web framework
- **PostgreSQL 15+** - основная БД
- **Redis 7+** - кэш, сессии, rate limiting
- **SQLAlchemy 2.0+** - ORM
- **Alembic** - миграции БД
- **Pydantic v2** - валидация данных
- **PyJWT** - JWT токены
- **Loguru** - логирование
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
```

### Тестирование

```bash
# Запуск всех тестов
poetry run pytest

# Запуск с coverage
poetry run pytest --cov=app tests/

# Запуск конкретного теста
poetry run pytest tests/test_auth.py -v
```

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

### Authentication

- `POST /api/v1/auth/register` - Регистрация нового пользователя
- `POST /api/v1/auth/login` - Логин и получение JWT токена

### Users

- `GET /api/v1/users/me` - Получить профиль текущего пользователя
- `PATCH /api/v1/users/me` - Обновить профиль

### Access Tokens

- `POST /api/v1/tokens/purchase` - Создать токен доступа (MVP: бесплатно)
- `GET /api/v1/tokens/my-tokens` - Получить список своих токенов
- `POST /api/v1/tokens/validate` - Валидировать токен

### Proxy

- `ALL /api/v1/proxy/{path}` - Проксирование к Zenzefi серверу (требует X-Access-Token header)
- `GET /api/v1/proxy/status` - Статус подключения

## Структура проекта

```
zenzefi-backend/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── auth.py          # Authentication endpoints
│   │   │   ├── users.py         # User endpoints
│   │   │   ├── tokens.py        # Token endpoints
│   │   │   └── proxy.py         # Proxy endpoints
│   │   └── deps.py              # API dependencies
│   ├── core/
│   │   ├── database.py          # Database connection
│   │   ├── redis.py             # Redis connection
│   │   ├── security.py          # JWT, password hashing
│   │   └── logging.py           # Logging configuration
│   ├── models/
│   │   ├── user.py              # User model
│   │   └── token.py             # AccessToken model
│   ├── schemas/
│   │   ├── user.py              # User schemas
│   │   ├── token.py             # Token schemas
│   │   └── auth.py              # Auth schemas
│   ├── services/
│   │   ├── auth_service.py      # Auth business logic
│   │   ├── token_service.py     # Token business logic
│   │   └── proxy_service.py     # Proxy business logic
│   ├── config.py                # Application settings
│   └── main.py                  # FastAPI application
├── alembic/                     # Database migrations
├── scripts/                     # Helper scripts
├── tests/                       # Tests
├── docker-compose.dev.yml       # Development Docker setup
├── pyproject.toml               # Poetry dependencies
└── README.md                    # This file
```

## Переменные окружения

См. `.env.example` для списка всех переменных.

Основные:
- `SECRET_KEY` - Секретный ключ для JWT (обязательно!)
- `POSTGRES_*` - Настройки PostgreSQL
- `REDIS_*` - Настройки Redis
- `ZENZEFI_TARGET_URL` - URL целевого Zenzefi сервера
- `DEBUG` - Режим отладки (True/False)

## MVP Features (Этап 1) ✅

- ✅ Регистрация и аутентификация пользователей
- ✅ JWT токены для API доступа
- ✅ Создание токенов доступа (бесплатно для MVP)
- ✅ Валидация токенов
- ✅ Проксирование запросов к Zenzefi серверу
- ✅ Кэширование токенов в Redis

## Следующие этапы

### Этап 2: Система валюты (TODO)
- Внутренняя валюта (ZNC - Zenzefi Credits)
- Пополнение баланса
- Покупка токенов за валюту
- История транзакций
- Система возврата средств

### Этап 3: Мониторинг (TODO)
- Трекинг proxy сессий
- Admin endpoints
- Метрики и логирование

### Этап 4: Production (TODO)
- Nginx с SSL
- Rate limiting
- CORS configuration
- CI/CD pipeline

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

- **[DEPLOYMENT_DOCKER.md](./DEPLOYMENT_DOCKER.md)** - 🐳 Docker deployment (рекомендуется)
- **[DEPLOYMENT.md](./DEPLOYMENT.md)** - 📦 Native installation
- **[QUICKSTART.md](./QUICKSTART.md)** - Шпаргалка по основным командам
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