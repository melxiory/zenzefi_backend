# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 📚 Documentation Navigation

**Root Documentation (Overview):**
- 🏗️ [Architecture Overview](./docs/ARCHITECTURE.md) - System architecture, data flow, services
- 🔧 [Tech Stack](./docs/TECH_STACK.md) - Complete technology stack for both components
- ⚙️ [Configuration Guide](./docs/CONFIGURATION.md) - Environment variables, settings, security
- 🚀 [Development Guide](./docs/DEVELOPMENT.md) - Setup, workflows, debugging, common tasks

**Backend Documentation:**
- 📖 [Backend CLAUDE.md](./CLAUDE.md) - This file (backend in current directory)
- 🧪 [Testing Guide](./docs/claude/TESTING.md) - Testing patterns and fixtures
- 🐛 [Troubleshooting](./docs/claude/TROUBLESHOOTING.md) - Common issues and solutions
- 💻 [Development Commands](./docs/claude/DEVELOPMENT.md) - All backend commands
- 🏥 [Health Checks](./docs/HEALTH_CHECKS.md) - Health monitoring system
- 🚢 [Deployment](./docs/DEPLOYMENT_TAILSCALE.md) - Docker deployment with Tailscale

**Desktop Client Documentation:**
- 📱 Client-specific documentation (zenzefi_client/CLAUDE.md) - when client submodule added

## Project Overview

**Zenzefi Proxy Platform** - Полная система контроля доступа и монетизации для окружений Zenzefi (Windows 11). Платформа состоит из двух взаимосвязанных компонентов:

1. **Zenzefi Backend** - FastAPI сервер аутентификации и проксирования с токенами доступа
2. **Zenzefi Client** - Windows desktop приложение с локальным HTTPS прокси

### Architecture Flow

```
[Browser] → [Local HTTPS Proxy] → [FastAPI Backend] → [Zenzefi Server]
           (127.0.0.1:61000)       (127.0.0.1:8000)     (VPN)
                 ↓                        ↓
           SSL Termination          Cookie Validation
           Cookie Forwarding        Token Validation
                                    Content Rewriting
                                         ↓
                                   [PostgreSQL] + [Redis]
```

**Current Status:** MVP Phase - Аутентификация, генерация токенов, cookie-based auth, проксирование реализованы и протестированы (85+ тестов).

## Repository Structure

Это **монорепозиторий** с двумя отдельными приложениями:

```
Zenzefi Proxy Platform/
├── docs/                         # Root-level documentation
│   ├── ARCHITECTURE.md           # System architecture
│   ├── TECH_STACK.md            # Technology stack
│   ├── CONFIGURATION.md         # Configuration guide
│   ├── DEVELOPMENT.md           # Development guide
│   ├── BACKEND.md               # Legacy backend docs
│   ├── DEPLOYMENT.md            # Legacy deployment docs
│   ├── DEPLOYMENT_TAILSCALE.md  # Docker + Tailscale deployment
│   ├── HEALTH_CHECKS.md         # Health monitoring
│   └── claude/                  # Legacy Claude documentation
│
├── zenzefi_backend/             # FastAPI backend server
│   ├── app/                     # Application code
│   │   ├── api/v1/             # HTTP endpoints
│   │   ├── services/           # Business logic
│   │   ├── models/             # SQLAlchemy ORM
│   │   ├── schemas/            # Pydantic validation
│   │   └── core/               # Core utilities
│   ├── alembic/                # Database migrations
│   ├── tests/                  # Pytest test suite (85+ tests)
│   ├── scripts/                # Database utilities
│   ├── docs/                   # Backend documentation
│   │   ├── claude/             # Claude-specific docs
│   │   │   ├── DEVELOPMENT.md  # Backend commands
│   │   │   ├── TESTING.md      # Testing guide
│   │   │   └── TROUBLESHOOTING.md
│   │   ├── HEALTH_CHECKS.md    # Health system
│   │   └── DEPLOYMENT_TAILSCALE.md
│   ├── pyproject.toml          # Poetry dependencies
│   └── CLAUDE.md               # Backend-specific guide
│
├── zenzefi_client/             # PySide6 desktop client (future submodule)
│   ├── core/                   # Proxy, auth, config
│   ├── ui/                     # Qt GUI components
│   ├── utils/                  # Logging, process management
│   ├── resources/              # UI resources
│   ├── main.py                 # Entry point
│   ├── pyproject.toml          # Poetry dependencies
│   └── CLAUDE.md               # Client-specific guide
│
└── CLAUDE.md                   # This file (root overview)
```

## Quick Start

### Backend Development

```bash
# Navigate to backend
cd zenzefi_backend

# Start services (PostgreSQL + Redis)
docker-compose -f docker-compose.dev.yml up -d

# Install dependencies
poetry install

# Run migrations
poetry run alembic upgrade head

# Start development server
python run_dev.py
```

Backend running: http://localhost:8000
API Docs: http://localhost:8000/docs

### Desktop Client Development

```bash
# Navigate to client
cd zenzefi_client

# Install dependencies
poetry install

# Run client (requires backend running)
python main.py
```

Client running: https://127.0.0.1:61000

### Full Stack Development

**Terminal 1: Backend**
```bash
cd zenzefi_backend
docker-compose -f docker-compose.dev.yml up -d
poetry run alembic upgrade head
python run_dev.py
```

**Terminal 2: Desktop Client**
```bash
cd zenzefi_client
python main.py
```

## Component Responsibilities

### Desktop Client - Simplified Forwarding Proxy

**Ответственности:**
- SSL/TLS терминация (самоподписанный сертификат)
- Пересылка HTTP/HTTPS запросов к бекенду
- Пересылка cookies между браузером и бекендом
- Отправка заголовка `X-Local-Url` для переписывания URL
- Управление GUI и системным треем
- Шифрование токенов (Fernet)

**НЕ выполняет:**
- Валидация аутентификации
- Переписывание контента
- Кеширование
- Обработка WebSocket
- Любая бизнес-логика

### Backend Server - Authentication & Proxy

**Ответственности:**
- Аутентификация пользователей (JWT + cookie)
- Валидация токенов (двухуровневое кеширование: Redis → PostgreSQL)
- Проксирование к Zenzefi серверу
- Переписывание контента (ContentRewriter)
- Обработка WebSocket
- Управление БД и кешем
- Health checks

## Key Integration Points

### 1. Cookie-Based Authentication

Desktop Client использует cookie для аутентификации браузера:

1. Пользователь вводит токен в Desktop Client (хранится зашифрованным)
2. Desktop Client запускает локальный HTTPS прокси
3. Браузер открывает: `https://127.0.0.1:61000/api/v1/proxy?token=xyz`
4. Desktop Client пересылает: `http://127.0.0.1:8000/api/v1/proxy?token=xyz`
5. Backend валидирует токен, устанавливает cookie `zenzefi_access_token`
6. Desktop Client переустанавливает cookie для локального домена
7. Все последующие запросы используют cookie автоматически

**Критические детали:**
- Cookie `path` ДОЛЖЕН быть `"/"` (не `/api/v1/proxy`)
- Desktop Client отправляет заголовок `X-Local-Url: https://127.0.0.1:61000`
- Backend использует этот заголовок для корректного переписывания URL

### 2. Two Token Types

**JWT Tokens (API Authentication):**
- Для API запросов (регистрация, логин, покупка токенов)
- Алгоритм: HS256
- Payload: `{"sub": user_id, "username": username}` (НЕ email)
- Срок: 60 минут
- Использование: `Authorization: Bearer {token}`

**Access Tokens (Proxy Access):**
- Для доступа к прокси Zenzefi
- Формат: 64-символьная случайная строка (НЕ JWT)
- Длительность: 1, 12, 24, 168, 720 часов
- Хранение: PostgreSQL + Redis кеширование
- Использование: `X-Access-Token` header ИЛИ `zenzefi_access_token` cookie

### 3. Two-Tier Token Validation

1. **Fast path (Redis):** ~1ms - проверка кеша активных токенов
2. **Slow path (PostgreSQL):** ~10ms - запрос к БД при cache miss
3. **Filters:** `is_active=True`, `revoked_at=None`, not expired
4. **Caching:** Только активированные токены кешируются (TTL = срок токена)

## Development Guidelines

### Before Starting Work

1. **Определите компонент:** Backend или Client?
2. **Прочитайте CLAUDE.md компонента** для детальной архитектуры
3. **Настройте окружение** для этого компонента
4. **Для интеграции:** убедитесь, что оба компонента запущены

### Component-Specific Documentation

**Backend работа:**
- Читайте корневой `CLAUDE.md` (этот файл - бекенд в текущей директории)
- Подробная архитектура, API endpoints, паттерны тестирования
- Development команды в `docs/claude/DEVELOPMENT.md`

**Client работа:**
- Читайте `zenzefi_client/CLAUDE.md` (когда доступно)
- Архитектура desktop приложения, прокси, Qt/PySide6 паттерны
- Build инструкции

### Critical Backend Details

**Тестирование:**
- 85+ тестов с реальными PostgreSQL и Redis (БЕЗ моков)
- Тестовая БД: `zenzefi_test`
- Все тесты должны проходить перед завершением работы

**Token System:**
- `expires_at` - computed property, НЕ колонка БД
- JWT payload: `{"sub": user_id, "username": username}` (НЕ email)
- Access tokens: `secrets.token_urlsafe(48)` = 64 символа

**Cookie Settings:**
- `path` ДОЛЖЕН быть `"/"` (критично для совместимости с браузером)
- `COOKIE_SECURE=False` для dev/HTTP, `True` для prod/HTTPS
- `COOKIE_SAMESITE="lax"` для dev, `"none"` для prod с HTTPS

**Timezone (КРИТИЧНО):**
- Всегда используйте `datetime.now(timezone.utc)` для timezone-aware datetime (НЕ `datetime.utcnow()`)
- При десериализации из Redis/ISO: `datetime.fromisoformat()` может вернуть timezone-naive datetime
- **ОБЯЗАТЕЛЬНО проверяйте timezone перед сравнением:** `if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)`
- Тесты JWT: `datetime.utcfromtimestamp()` (не `fromtimestamp`)

### Critical Desktop Client Details

**Proxy Architecture:**
- Desktop Client - упрощённый forwarding proxy
- ВСЯ бизнес-логика в Backend
- ContentRewriter и CacheManager НЕ существуют в Desktop Client

**Connection Pool:**
- 100 total connections
- 50 per host
- 60s keep-alive

**Performance Optimizations:**
- MainWindow lazy loading: экономия 20-30MB RAM
- Log debouncing (200ms): снижение GUI overhead на 80-90%
- Splash screen с async initialization

**Critical Settings:**
- Port 61000 hardcoded (изменение требует обновлений в нескольких местах)
- Self-signed SSL certificate (2048-bit RSA, 365 дней)
- Access token required перед запуском proxy

## Common Pitfalls to Avoid

### Backend

❌ **Использование моков в тестах** - используйте реальные PostgreSQL и Redis
❌ **Cookie path не "/"** - браузер не отправит cookie
❌ **Прямая запись в expires_at** - это computed property
❌ **email в JWT payload** - используйте username

### Desktop Client

❌ **Добавление бизнес-логики в Client** - вся логика в Backend
❌ **Вызов asyncio.run() при работающем proxy loop** - используйте run_coroutine_threadsafe()
❌ **Изменение port 61000 без обновления всех мест** - hardcoded значение
❌ **Попытка использовать ContentRewriter** - его нет в Client

### Integration

❌ **Запуск Client без Backend** - Client требует Backend
❌ **Отсутствие X-Local-Url header** - Backend не сможет корректно переписать URL
❌ **Неправильная пересылка cookies** - критично для аутентификации

## Testing Strategy

**Backend:**
- 85+ тестов, 85%+ покрытие
- Реальные сервисы (PostgreSQL, Redis)
- Тестовая БД: `zenzefi_test`
- Запуск: `cd zenzefi_backend && poetry run pytest tests/ -v`

**Desktop Client:**
- Ручное тестирование через GUI
- Проверка SSL сертификата при первом запуске
- Тестирование proxy start/stop, конфликтов портов
- Тестирование cookie authentication flow в браузере

## Deployment

**Backend:**
- Production: Docker Compose (рекомендуется)
- См. `docs/DEPLOYMENT_TAILSCALE.md` для Docker с Tailscale VPN
- См. `docs/DEPLOYMENT.md` для native установки
- Включает Nginx с SSL/TLS, автоматические бэкапы

**Desktop Client:**
- Build: `cd zenzefi_client && python build_optimized.py`
- PyInstaller с UPX compression
- Output: `dist/` directory
- Windows-only (использует Windows-specific APIs)

## Health Monitoring

**Endpoints:**
- `/health` - Быстрая проверка из Redis (~1ms)
- `/health/detailed` - Детальная информация с latency

**Background Checks:**
- PostgreSQL, Redis, Zenzefi сервер
- Интервал: каждые 50 секунд
- Кеширование в Redis (TTL: 120s)

**Status:**
- `healthy` - все сервисы работают
- `degraded` - Zenzefi недоступен
- `unhealthy` - PostgreSQL или Redis недоступны

## Next Development Phases

### Phase 2: Currency System (Planned)
- `currency_balance` в User model
- Transaction model для отслеживания покупок
- Token pricing (сейчас бесплатно в MVP)
- Система возвратов для неиспользованных токенов

### Phase 3: Monitoring (Planned)
- ProxySession model для отслеживания соединений
- Admin endpoints для управления пользователями/токенами
- Prometheus metrics
- Расширенное логирование и аналитика

### Phase 4: Production Hardening (Planned)
- Rate limiting middleware
- CORS настройка для конкретных origins
- CI/CD pipeline
- Load testing и оптимизация

## Resources

**API Documentation:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health

**Documentation:**
- Root: `docs/` - Architecture, Tech Stack, Configuration, Development
- Backend: Root `CLAUDE.md` (this file) + `docs/claude/`
- Client: `zenzefi_client/CLAUDE.md` (when available)

## Notes for Claude Code

**Project Structure:**
- Монорепозиторий - всегда уточняйте компонент
- Каждый компонент имеет comprehensive CLAUDE.md
- Используйте component-specific Poetry environments

**Backend Critical:**
- Тесты ДОЛЖНЫ проходить перед завершением работы
- Используйте реальные PostgreSQL и Redis (БЕЗ моков)
- JWT payload: `{"sub": user_id, "username": username}`
- Cookie `path="/"` - критично
- `expires_at` - computed property
- Access tokens: 48 bytes → 64 chars
- Двухуровневая валидация: Redis (~1ms) → PostgreSQL (~10ms)
- ContentRewriter ТОЛЬКО в Backend
- **Timezone-aware datetime:** Всегда `datetime.now(timezone.utc)` и проверка `dt.tzinfo` перед сравнением

**Desktop Client Critical:**
- Упрощённый forwarding proxy (БЕЗ бизнес-логики)
- ВСЯ логика в Backend
- ContentRewriter и CacheManager НЕ существуют в Client
- Connection pool: 100 total, 50/host, 60s keep-alive
- Access token required перед proxy start
- MainWindow lazy loading, log debouncing
- Port 61000 hardcoded

**Integration:**
- Backend ДОЛЖЕН работать для Desktop Client
- Cookie-based authentication - основной метод
- Client пересылает cookies и отправляет `X-Local-Url`
- Backend использует header для переписывания URL
- Тестирование интеграции только ручное (browser-based)

**Platform:**
- Разработка на Windows (команды могут требовать адаптации для Linux/Mac)
- Desktop Client использует Windows-specific APIs
- Backend deployment: Docker Compose рекомендуется

**Documentation Navigation:**
- Начните с этого файла (root CLAUDE.md)
- Затем читайте `docs/ARCHITECTURE.md` для понимания системы
- Затем component-specific CLAUDE.md для деталей
- Используйте `docs/DEVELOPMENT.md` для workflows
