# 🚀 План интеграции Claude Code для Zenzefi

**Дата создания:** 29 октября 2025  
**Версия:** 1.0  
**Проекты:** zenzefi_backend + zenzefi_client

---

## 📋 Содержание

- [Обзор](#обзор)
- [Backend: MCP серверы и агенты](#backend-mcp-серверы-и-агенты)
- [Client: MCP серверы и агенты](#client-mcp-серверы-и-агенты)
- [Общие инструменты](#общие-инструменты)
- [Поэтапный план внедрения](#поэтапный-план-внедрения)
- [Конфигурационные файлы](#конфигурационные-файлы)
- [Примеры использования](#примеры-использования)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Обзор

### Цели интеграции

1. **Ускорить разработку** через автоматизацию рутинных задач
2. **Улучшить качество кода** через специализированных агентов
3. **Упростить работу с БД** через прямой доступ к PostgreSQL
4. **Автоматизировать тестирование** и деплой
5. **Синхронизировать workflow** между backend и client

### Приоритеты

```
🔴 Критично (Неделя 1):
   - PostgreSQL MCP (backend)
   - Docker MCP (оба проекта)
   - GitHub MCP (оба проекта)

🟡 Важно (Неделя 2):
   - Python агенты (оба проекта)
   - Database архитектор (backend)
   - Security аудит (backend)

🟢 Полезно (Неделя 3-4):
   - Кастомные плагины
   - Automation hooks
   - Team configuration
```

---

## 🔧 Backend: MCP серверы и агенты

### MCP Серверы для Backend

#### 1. PostgreSQL MCP Server ⭐⭐⭐ (Критично)

**Назначение:**
- Прямой доступ к базе данных
- Генерация и оптимизация SQL запросов
- Анализ схемы БД
- Помощь с миграциями Alembic

**Установка:**
```bash
cd ~/zenzefi-backend

claude mcp add postgres --scope project \
  -e DATABASE_URL="postgresql://zenzefi:devpassword@localhost:5432/zenzefi_dev" \
  -- npx @modelcontextprotocol/server-postgres
```

**Возможности:**
- `SELECT * FROM users WHERE email = '...'` — прямые запросы
- Анализ индексов и производительности
- Валидация миграций перед применением
- Генерация SQL для сложных JOIN-ов

**Пример использования:**
```bash
claude "Покажи всех пользователей с активными токенами, которые истекают в течение 24 часов"
claude "Проанализируй индексы таблицы access_tokens и предложи оптимизации"
claude "Создай миграцию для добавления поля last_login в User"
```

---

#### 2. Docker MCP Server ⭐⭐⭐ (Критично)

**Назначение:**
- Управление контейнерами (PostgreSQL, Redis)
- Мониторинг логов и статуса
- Автоматизация docker-compose операций

**Установка:**
```bash
claude mcp add docker --scope project \
  -- npx @modelcontextprotocol/server-docker
```

**Возможности:**
- Проверка статуса контейнеров
- Чтение логов в реальном времени
- Перезапуск сервисов
- Очистка volumes и images

**Пример использования:**
```bash
claude "Покажи логи redis контейнера за последние 10 минут"
claude "Перезапусти postgres контейнер и проверь подключение"
claude "Очисти неиспользуемые docker volumes"
```

---

#### 3. GitHub MCP Server ⭐⭐⭐ (Критично)

**Назначение:**
- Управление issues и pull requests
- Анализ истории коммитов
- Автоматизация code review

**Установка:**
```bash
# Создайте GitHub Personal Access Token:
# https://github.com/settings/tokens
# Scope: repo, read:user

claude mcp add github --scope user \
  -e GITHUB_PERSONAL_ACCESS_TOKEN="ghp_your_token_here" \
  -- npx @modelcontextprotocol/server-github
```

**Возможности:**
- Создание issues с шаблонами
- Автоматический PR review
- Поиск по коду и истории
- Управление labels и milestones

**Пример использования:**
```bash
claude "Создай issue для Этапа 2: Currency System с детальным описанием"
claude "Проанализируй последние 10 коммитов и найди потенциальные баги"
claude "Создай PR с описанием изменений в token_service.py"
```

---

#### 4. Redis MCP Server ⭐⭐ (Важно)

**Назначение:**
- Мониторинг кэша
- Управление ключами
- Анализ производительности

**Установка:**
```bash
# Использовать custom MCP сервер или создать свой
# Пока нет официального Redis MCP, можно использовать bash через filesystem

claude mcp add redis-cli --scope project \
  -- bash -c "redis-cli -h localhost -p 6379"
```

**Альтернатива - кастомный MCP:**
```python
# scripts/redis_mcp.py
from fastmcp import FastMCP
import redis

mcp = FastMCP("Redis Tools")

@mcp.tool()
def get_redis_key(key: str) -> dict:
    """Получить значение из Redis"""
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    value = r.get(key)
    ttl = r.ttl(key)
    return {"key": key, "value": value, "ttl": ttl}

@mcp.tool()
def flush_redis_pattern(pattern: str) -> dict:
    """Удалить ключи по паттерну"""
    r = redis.Redis(host='localhost', port=6379)
    keys = r.keys(pattern)
    if keys:
        r.delete(*keys)
    return {"deleted": len(keys), "pattern": pattern}

if __name__ == "__main__":
    mcp.run()
```

```bash
# Установка кастомного
cd ~/zenzefi-backend
poetry add fastmcp redis

claude mcp add redis-tools --scope project \
  -- poetry run python scripts/redis_mcp.py
```

---

#### 5. FastAPI MCP Server ⭐⭐ (Важно)

**Назначение:**
- Тестирование API endpoints
- Генерация OpenAPI документации
- Валидация Pydantic схем

**Установка (через FastMCP):**
```bash
cd ~/zenzefi-backend

# Создайте файл mcp_server.py
cat > mcp_server.py << 'EOF'
from fastmcp import FastMCP
from app.main import app

# Генерация MCP сервера из FastAPI
mcp = FastMCP.from_fastapi(app=app)

if __name__ == "__main__":
    mcp.run()
EOF

# Добавьте зависимость
poetry add fastmcp

# Настройте MCP
claude mcp add zenzefi-api --scope project \
  -- poetry run python mcp_server.py
```

**Возможности:**
- Прямой вызов API endpoints
- Тестирование с различными payloads
- Проверка валидации
- Генерация примеров запросов

---

#### 6. Sequential Thinking Server ⭐⭐ (Важно)

**Назначение:**
- Планирование сложных задач
- Декомпозиция на шаги
- Систематический подход

**Установка:**
```bash
claude mcp add sequential-thinking --scope user \
  -- npx @modelcontextprotocol/server-sequential-thinking
```

**Пример использования:**
```bash
claude "Используя sequential thinking, спланируй реализацию Этапа 2: Currency System"
```

---

### Агенты для Backend

#### Marketplace установка

```bash
# Основной marketplace с агентами
/plugin marketplace add wshobson/agents

# Community marketplace
/plugin marketplace add Dev-GOM/claude-code-marketplace

# Проверка
/plugin marketplace list
```

---

#### 1. Python Development Agent ⭐⭐⭐ (Критично)

**Специализация:**
- FastAPI best practices
- Async/await паттерны
- Type hints и mypy
- Poetry dependency management

**Установка:**
```bash
/plugin install python-development@wshobson/agents
```

**Использование:**
```bash
claude "@python-developer создай async endpoint для /api/v1/currency/balance"
claude "@python-developer оптимизируй async операции в proxy_service.py"
```

**Встроенные команды:**
```bash
/python-development:python-scaffold fastapi-microservice
/python-development:async-optimize
```

---

#### 2. Database Architect Agent ⭐⭐⭐ (Критично)

**Специализация:**
- PostgreSQL схемы
- SQLAlchemy ORM
- Индексы и производительность
- Alembic миграции

**Установка:**
```bash
/plugin install database-architect@wshobson/agents
```

**Использование:**
```bash
claude "@database-architect спроектируй схему для Transaction model"
claude "@database-architect проанализируй индексы и предложи оптимизации"
claude "@database-architect создай миграцию для добавления composite index"
```

---

#### 3. Security Auditor Agent ⭐⭐⭐ (Критично)

**Специализация:**
- JWT security
- SQL injection prevention
- OWASP Top 10
- Dependency scanning

**Установка:**
```bash
/plugin install security-auditor@wshobson/agents
```

**Использование:**
```bash
claude "@security-auditor проверь auth_service.py на уязвимости"
claude "@security-auditor audit JWT implementation"
claude "@security-auditor scan dependencies for CVEs"
```

---

#### 4. Test Automation Agent ⭐⭐ (Важно)

**Специализация:**
- pytest tests
- Coverage optimization
- Integration testing
- Fixtures и mocks

**Установка:**
```bash
/plugin install test-automator@wshobson/agents
```

**Использование:**
```bash
claude "@test-automator создай тесты для token_service.py"
claude "@test-automator улучши coverage до 90%"
```

---

#### 5. Backend Architect Agent ⭐⭐ (Важно)

**Специализация:**
- Архитектурные решения
- Design patterns
- Scalability planning
- API design

**Установка:**
```bash
/plugin install backend-architect@wshobson/agents
```

**Использование:**
```bash
claude "@backend-architect спроектируй rate limiting middleware"
claude "@backend-architect review архитектуры для Этапа 3: Monitoring"
```

---

#### 6. Deployment Engineer Agent ⭐ (Полезно)

**Специализация:**
- Docker optimization
- CI/CD pipelines
- Production setup
- Nginx configuration

**Установка:**
```bash
/plugin install deployment-engineer@wshobson/agents
```

**Использование:**
```bash
claude "@deployment-engineer настрой production docker-compose.yml"
claude "@deployment-engineer создай GitHub Actions workflow"
```

---

## 🖥️ Client: MCP серверы и агенты

### MCP Серверы для Client

#### 1. Filesystem MCP Server ⭐⭐⭐ (Критично)

**Назначение:**
- Чтение конфигов (app_data/)
- Анализ логов
- Работа с SSL сертификатами

**Установка:**
```bash
cd ~/zenzefi-client

claude mcp add filesystem --scope project \
  -e ALLOWED_DIRECTORIES="/home/user/zenzefi-client" \
  -- npx @modelcontextprotocol/server-filesystem
```

**Возможности:**
- Анализ структуры проекта
- Чтение конфигов и логов
- Работа с ресурсами (icons, UI файлы)

---

#### 2. Docker MCP Server ⭐⭐⭐ (Критично)

**Назначение:**
- Управление dev окружением
- Тестирование proxy с контейнерами

**Установка:**
```bash
claude mcp add docker --scope project \
  -- npx @modelcontextprotocol/server-docker
```

---

#### 3. GitHub MCP Server ⭐⭐⭐ (Критично)

**Установка:**
```bash
claude mcp add github --scope user \
  -e GITHUB_PERSONAL_ACCESS_TOKEN="ghp_your_token_here" \
  -- npx @modelcontextprotocol/server-github
```

---

#### 4. Browser Automation MCP (Puppeteer) ⭐⭐ (Важно)

**Назначение:**
- Тестирование proxy в браузере
- E2E тесты
- Screenshot testing

**Установка:**
```bash
claude mcp add puppeteer --scope project \
  -- npx @modelcontextprotocol/server-puppeteer
```

**Использование:**
```bash
claude "Открой браузер через proxy https://localhost:8443 и сделай screenshot главной страницы"
```

---

### Агенты для Client

#### 1. Python Desktop Developer Agent ⭐⭐⭐ (Критично)

**Специализация:**
- PySide6/Qt development
- Async GUI patterns
- Threading и QTimer
- PyInstaller bundling

**Установка:**
```bash
/plugin install python-development@wshobson/agents
```

**Использование:**
```bash
claude "@python-developer оптимизируй startup_thread в main.py"
claude "@python-developer создай новый QWidget для настроек proxy"
```

---

#### 2. UI/UX Designer Agent ⭐⭐ (Важно)

**Специализация:**
- Qt styling
- Theme management
- Icon design
- Layout optimization

**Установка:**
```bash
/plugin install ui-designer@wshobson/agents
```

**Использование:**
```bash
claude "@ui-designer улучши dark theme в theme_manager.py"
claude "@ui-designer создай новую цветовую схему для tray icon"
```

---

#### 3. Network Protocol Engineer ⭐⭐ (Важно)

**Специализация:**
- HTTP/HTTPS proxy
- WebSocket handling
- SSL/TLS certificates
- Network debugging

**Установка:**
```bash
# Создать кастомного агента (см. раздел Custom Agents)
```

---

#### 4. Performance Optimizer Agent ⭐⭐ (Важно)

**Специализация:**
- Memory profiling
- Cache optimization
- Async performance
- Resource management

**Установка:**
```bash
/plugin install performance-optimizer@wshobson/agents
```

**Использование:**
```bash
claude "@performance-optimizer проанализируй memory usage в ProxyManager"
claude "@performance-optimizer оптимизируй LRU cache implementation"
```

---

#### 5. Test Automation Agent ⭐⭐ (Важно)

**Установка:**
```bash
/plugin install test-automator@wshobson/agents
```

**Использование:**
```bash
claude "@test-automator создай unit tests для ZenzefiProxy"
claude "@test-automator добавь integration tests для proxy_manager"
```

---

## 🌐 Общие инструменты

### 1. Brave Search MCP ⭐⭐ (Важно)

**Назначение:**
- Поиск актуальной документации
- Troubleshooting ошибок
- Поиск best practices

**Установка:**
```bash
# Получите API ключ: https://brave.com/search/api/

claude mcp add brave-search --scope user \
  -e BRAVE_API_KEY="your_brave_api_key" \
  -- npx @modelcontextprotocol/server-brave-search
```

**Использование:**
```bash
claude "Найди последнюю документацию по FastAPI 0.119+ streaming responses"
claude "Поищи решения для PySide6 QSystemTrayIcon не отображается на Ubuntu"
```

---

### 2. Git Operations MCP ⭐⭐ (Важно)

**Назначение:**
- Анализ истории
- Управление ветками
- Cherry-pick и rebase

**Установка:**
```bash
claude mcp add git --scope user \
  -- npx @modelcontextprotocol/server-git
```

---

### 3. Documentation Generator Agent ⭐ (Полезно)

**Установка:**
```bash
/plugin install documentation-generator@wshobson/agents
```

---

## 📅 Поэтапный план внедрения

### 🔴 Фаза 1: Критичные инструменты (Неделя 1)

**Срок:** 29 октября - 5 ноября 2025

#### Backend

```bash
# День 1-2: MCP серверы
cd ~/zenzefi-backend

# PostgreSQL
claude mcp add postgres --scope project \
  -e DATABASE_URL="postgresql://zenzefi:devpassword@localhost:5432/zenzefi_dev" \
  -- npx @modelcontextprotocol/server-postgres

# Docker
claude mcp add docker --scope project \
  -- npx @modelcontextprotocol/server-docker

# GitHub
claude mcp add github --scope user \
  -e GITHUB_PERSONAL_ACCESS_TOKEN="ghp_xxx" \
  -- npx @modelcontextprotocol/server-github

# Проверка
claude mcp list

# День 3-4: Базовые агенты
/plugin marketplace add wshobson/agents
/plugin install python-development
/plugin install database-architect

# День 5-7: Тестирование и адаптация
# Выполните тестовые задачи с новыми инструментами
```

#### Client

```bash
# День 1-2: MCP серверы
cd ~/zenzefi-client

# Filesystem
claude mcp add filesystem --scope project \
  -e ALLOWED_DIRECTORIES="/home/user/zenzefi-client" \
  -- npx @modelcontextprotocol/server-filesystem

# Docker
claude mcp add docker --scope project \
  -- npx @modelcontextprotocol/server-docker

# GitHub (используем user scope, уже настроен)

# День 3-4: Агенты
/plugin install python-development

# День 5-7: Тестирование
```

**Критерии успеха:**
- ✅ Все MCP серверы в статусе "connected" (`/mcp`)
- ✅ Агенты видны в `/help`
- ✅ Выполнена хотя бы 1 задача с каждым инструментом

---

### 🟡 Фаза 2: Важные инструменты (Неделя 2)

**Срок:** 5 ноября - 12 ноября 2025

#### Backend

```bash
# День 1-2: Дополнительные MCP
# FastAPI MCP
poetry add fastmcp
# Создать mcp_server.py (см. выше)
claude mcp add zenzefi-api --scope project \
  -- poetry run python mcp_server.py

# Redis MCP (кастомный)
# Создать scripts/redis_mcp.py (см. выше)
poetry add fastmcp redis
claude mcp add redis-tools --scope project \
  -- poetry run python scripts/redis_mcp.py

# Sequential Thinking
claude mcp add sequential-thinking --scope user \
  -- npx @modelcontextprotocol/server-sequential-thinking

# День 3-5: Агенты для качества
/plugin install security-auditor
/plugin install test-automator
/plugin install backend-architect

# День 6-7: Интеграция в workflow
# Создать задачи с использованием новых агентов
```

#### Client

```bash
# День 1-2: Дополнительные MCP
# Puppeteer для E2E тестов
claude mcp add puppeteer --scope project \
  -- npx @modelcontextprotocol/server-puppeteer

# День 3-5: Специализированные агенты
/plugin install performance-optimizer
/plugin install test-automator

# День 6-7: UI/UX агент (если доступен)
/plugin install ui-designer
```

**Критерии успеха:**
- ✅ Redis кэш анализируется через MCP
- ✅ Security audit выполнен для backend
- ✅ Coverage тестов увеличен на 10%+

---

### 🟢 Фаза 3: Автоматизация (Неделя 3-4)

**Срок:** 12 ноября - 26 ноября 2025

#### Создание кастомных плагинов

**Backend Plugin: `zenzefi-backend-dev`**

```bash
cd ~/zenzefi-backend
mkdir -p .claude-plugin/zenzefi-backend-dev/{commands,agents,hooks,skills}

cat > .claude-plugin/zenzefi-backend-dev/.claude-plugin/plugin.json << 'EOF'
{
  "name": "zenzefi-backend-dev",
  "description": "Zenzefi Backend development toolkit",
  "version": "1.0.0",
  "author": {
    "name": "Zenzefi Team"
  }
}
EOF
```

**Команды:**

```markdown
# commands/migrate.md
---
description: Create and apply Alembic migration
---
# Alembic Migration Helper

1. Ask user for migration description
2. Generate migration: `poetry run alembic revision --autogenerate -m "description"`
3. Show generated SQL for review
4. Ask for confirmation
5. Apply: `poetry run alembic upgrade head`
6. Verify in database
```

```markdown
# commands/test-endpoint.md
---
description: Test API endpoint with coverage
---
# Endpoint Testing

1. Ask user which endpoint to test (e.g., /api/v1/auth/login)
2. Find corresponding test file (e.g., tests/test_api_auth.py)
3. Run specific test with coverage
4. Show results and coverage report
5. Suggest improvements if coverage < 80%
```

```markdown
# commands/deploy-check.md
---
description: Pre-deployment checklist
---
# Deployment Readiness Check

1. Run all tests: `poetry run pytest tests/ --cov=app`
2. Check migrations: `poetry run alembic current`
3. Lint code: `poetry run black app/ && poetry run isort app/`
4. Security scan: Check for known vulnerabilities
5. Docker health: Verify all containers running
6. Generate deployment report
```

**Агент:**

```markdown
# agents/zenzefi-architect.md
---
description: Zenzefi Backend architecture specialist
---
You are a Zenzefi Backend architecture expert with deep knowledge of:

## Technical Stack
- FastAPI 0.119+ with async patterns
- PostgreSQL 15+ with SQLAlchemy 2.0
- Redis 7+ for caching and sessions
- Alembic for database migrations
- PyJWT for authentication
- Docker Compose for containerization

## Project Structure
- Follows BACKEND.md and CLAUDE.md guidelines
- Layered architecture: API → Services → Models → DB
- Two token types: JWT (API auth) + Access Tokens (proxy)

## Best Practices
- Always use async/await for I/O operations
- Cache token validation in Redis (fast path)
- Write tests for new features (target 80%+ coverage)
- Use Pydantic v2 for validation
- Follow security best practices from security-auditor

## Development Workflow
1. Read BACKEND.md for context
2. Check current implementation phase
3. Follow established patterns
4. Test thoroughly before suggesting changes
5. Document architectural decisions

When asked about architecture:
- Consider scalability and performance
- Suggest production-ready solutions
- Reference existing patterns from codebase
- Warn about potential issues early
```

**Hooks:**

```json
// hooks/hooks.json
{
  "PostToolUse": [
    {
      "name": "auto-test-after-edit",
      "description": "Run tests after editing Python files",
      "config": {
        "tools": ["Edit", "Write"],
        "filePattern": "app/**/*.py",
        "command": "poetry run pytest tests/ -v --tb=short",
        "suppressOutput": false
      }
    }
  ],
  "Stop": [
    {
      "name": "generate-coverage-report",
      "description": "Generate coverage report on session end",
      "command": "poetry run pytest tests/ --cov=app --cov-report=html",
      "suppressOutput": true
    }
  ]
}
```

**Skills:**

```markdown
# skills/alembic-migrations/SKILL.md
# Alembic Migrations Skill

## Trigger Phrases
- "create migration"
- "database schema"
- "add column"
- "modify table"
- "alembic"

## Capabilities
This skill helps with Alembic database migrations for Zenzefi Backend.

### Creating Migrations
1. Analyze model changes in app/models/
2. Generate migration with descriptive name
3. Review generated SQL for correctness
4. Check for potential data loss operations
5. Apply migration with user confirmation

### Best Practices
- Always use --autogenerate for model-driven migrations
- Review SQL before applying
- Test on development database first
- Never skip migrations in sequence
- Document breaking changes

### Commands
```bash
# Generate migration
poetry run alembic revision --autogenerate -m "Add currency_balance to users"

# Apply migrations
poetry run alembic upgrade head

# Rollback
poetry run alembic downgrade -1

# Check current version
poetry run alembic current
```

### Common Patterns
- Adding columns: Check for NOT NULL constraints
- Creating indexes: Use concurrent creation for production
- Renaming columns: May require data migration
- Dropping columns: Ensure no code references remain
```

**Client Plugin: `zenzefi-client-dev`**

```bash
cd ~/zenzefi-client
mkdir -p .claude-plugin/zenzefi-client-dev/{commands,agents,hooks}

cat > .claude-plugin/zenzefi-client-dev/.claude-plugin/plugin.json << 'EOF'
{
  "name": "zenzefi-client-dev",
  "description": "Zenzefi Client development toolkit",
  "version": "1.0.0",
  "author": {
    "name": "Zenzefi Team"
  }
}
EOF
```

**Команды:**

```markdown
# commands/build-exe.md
---
description: Build Windows executable with PyInstaller
---
# Build Executable

1. Verify all dependencies installed: `poetry install`
2. Clean previous builds: `rm -rf build/ dist/`
3. Run PyInstaller: `pyinstaller ZenzefiClient.spec`
4. Check build logs for errors
5. Test executable: `./dist/ZenzefiClient/ZenzefiClient.exe`
6. Verify resources bundled correctly
7. Generate build report with file sizes
```

```markdown
# commands/test-proxy.md
---
description: Test proxy functionality locally
---
# Proxy Testing

1. Start development server (if backend available)
2. Start client proxy
3. Configure browser to use proxy (127.0.0.1:8443)
4. Test HTTP requests
5. Test HTTPS requests (check SSL)
6. Test WebSocket connections
7. Check logs for errors
8. Generate test report
```

**Агент:**

```markdown
# agents/pyside6-expert.md
---
description: PySide6/Qt expert for Zenzefi Client
---
You are a PySide6/Qt expert specializing in desktop applications.

## Expertise Areas
- PySide6 (Qt6) GUI development
- Async operations with QThread
- System tray applications
- Theme management (dark/light)
- Signal/slot patterns
- Cross-platform compatibility

## Zenzefi Client Specifics
- Singleton pattern for managers (use getters, never direct instantiation)
- Lazy loading: MainWindow created only when shown
- Async proxy runs in separate thread/event loop
- QTimer.singleShot(0) for deferred theme application
- Log rotation: 5MB max, 5 backups

## Common Patterns
```python
# Correct singleton usage
from core.config_manager import get_config
config = get_config()  # NOT ConfigManager()

# Async operations
from core.proxy_manager import get_proxy_manager
proxy = get_proxy_manager()
proxy.start()  # Runs in separate thread

# Theme application (deferred)
QTimer.singleShot(0, lambda: apply_theme(window))
```

## Best Practices
- Never block main GUI thread
- Use signals for cross-thread communication
- Lazy load heavy UI components
- Test on both Windows and Linux (WSL)
- Handle SSL certificate generation gracefully
```

---

#### Automation Plugins

```bash
# Backend автоматизация
/plugin install auto-committer@Dev-GOM/claude-code-marketplace
/plugin install complexity-monitor@Dev-GOM/claude-code-marketplace
/plugin install todo-collector@Dev-GOM/claude-code-marketplace

# Client автоматизация
/plugin install project-documenter@Dev-GOM/claude-code-marketplace
```

**Критерии успеха:**
- ✅ Кастомные плагины работают
- ✅ Hooks автоматически выполняются
- ✅ Team configuration настроен

---

## 📄 Конфигурационные файлы

### Backend: `~/.claude.json`

```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "DATABASE_URL": "postgresql://zenzefi:devpassword@localhost:5432/zenzefi_dev"
      }
    },
    "docker": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-docker"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_token_here"
      }
    },
    "redis-tools": {
      "command": "poetry",
      "args": ["run", "python", "scripts/redis_mcp.py"],
      "cwd": "/home/user/zenzefi-backend"
    },
    "zenzefi-api": {
      "command": "poetry",
      "args": ["run", "python", "mcp_server.py"],
      "cwd": "/home/user/zenzefi-backend"
    },
    "sequential-thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "your_brave_api_key"
      }
    }
  }
}
```

### Client: `~/.claude.json` (добавить)

```json
{
  "mcpServers": {
    "filesystem-client": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "env": {
        "ALLOWED_DIRECTORIES": "/home/user/zenzefi-client"
      }
    },
    "puppeteer": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
    }
  }
}
```

### Backend: `.claude/settings.json` (team config)

```json
{
  "marketplaces": [
    {
      "source": "wshobson/agents",
      "enabled": true
    },
    {
      "source": "Dev-GOM/claude-code-marketplace",
      "enabled": true
    },
    {
      "source": "./.claude-plugin",
      "name": "zenzefi-local",
      "enabled": true
    }
  ],
  "plugins": [
    {
      "name": "python-development",
      "marketplace": "wshobson/agents",
      "enabled": true
    },
    {
      "name": "database-architect",
      "marketplace": "wshobson/agents",
      "enabled": true
    },
    {
      "name": "security-auditor",
      "marketplace": "wshobson/agents",
      "enabled": true
    },
    {
      "name": "zenzefi-backend-dev",
      "marketplace": "zenzefi-local",
      "enabled": true
    }
  ]
}
```

---

## 💡 Примеры использования

### Backend Development Scenarios

#### Сценарий 1: Добавление нового endpoint

```bash
claude "
Используя @backend-architect и @python-developer:

1. Создай новый endpoint GET /api/v1/currency/balance
2. Добавь в app/api/v1/currency.py
3. Создай Pydantic схему CurrencyBalance
4. Реализуй через CurrencyService
5. Добавь тесты в tests/test_api_currency.py
6. Проверь через FastAPI MCP сервер
"
```

#### Сценарий 2: Оптимизация базы данных

```bash
# Шаг 1: Анализ через PostgreSQL MCP
claude "Подключись к postgres и покажи все таблицы с их размером"

# Шаг 2: Консультация с агентом
claude "@database-architect проанализируй схему access_tokens и предложи индексы"

# Шаг 3: Создание миграции
claude "/migrate add composite index on access_tokens(user_id, is_active, expires_at)"

# Шаг 4: Проверка
claude "Выполни EXPLAIN для запроса выборки активных токенов пользователя"
```

#### Сценарий 3: Security audit

```bash
# Полный аудит
claude "@security-auditor 
Проведи полный security audit:
1. Проверь JWT implementation в core/security.py
2. Проверь SQL injection в services
3. Проверь password hashing
4. Scan dependencies для CVEs
5. Проверь rate limiting (когда будет реализован)
6. Создай отчет с приоритетами
"
```

#### Сценарий 4: Реализация Currency System (Этап 2)

```bash
# Используем sequential thinking для планирования
claude "
Используя sequential-thinking и @backend-architect:

Спланируй и начни реализацию Этапа 2: Currency System

Требования из BACKEND.md:
- Transaction model для трекинга покупок
- currency_balance в User
- Списание при покупке токенов
- Endpoints: GET/POST /currency/balance, /currency/purchase
- Refund система

Распиши пошаговый план с учетом:
1. Database schema changes
2. Alembic migrations
3. Service layer implementation
4. API endpoints
5. Tests
6. Integration с существующим token system
"
```

---

### Client Development Scenarios

#### Сценарий 1: Оптимизация startup

```bash
claude "
Используя @python-developer и @performance-optimizer:

Проанализируй startup_thread в main.py:
1. Найди bottlenecks в инициализации
2. Оптимизируй загрузку SSL сертификатов
3. Улучши прогресс индикатор
4. Проверь memory usage
5. Предложи async improvements
"
```

#### Сценарий 2: Добавление новой темы

```bash
claude "
Используя @pyside6-expert:

Добавь новую тему 'midnight' в ui/theme_manager.py:
1. Создай цветовую палитру
2. Обнови COLORS dict
3. Добавь в theme selector
4. Примени к MainWindow и TrayIcon
5. Сохрани в config
"
```

#### Сценарий 3: Улучшение proxy performance

```bash
claude "
@performance-optimizer и @python-developer:

Оптимизируй ProxyManager:
1. Проанализируй LRU cache hit rate
2. Улучши connection pooling
3. Оптимизируй fix_content() caching
4. Проверь memory leaks
5. Benchmark до и после
"
```

#### Сценарий 4: E2E тестирование

```bash
# Используем Puppeteer MCP
claude "
Через puppeteer MCP:

Создай E2E тест:
1. Запусти client proxy
2. Открой браузер с proxy
3. Перейди на тестовую страницу
4. Проверь URL rewriting
5. Проверь WebSocket connection
6. Сделай screenshots
7. Проверь console errors
8. Сгенерируй отчет
"
```

---

### Cross-Project Scenarios

#### Сценарий 1: Синхронизация token flow

```bash
claude "
Работая с обоими проектами:

Backend (через postgres MCP):
- Покажи структуру AccessToken model

Client (через filesystem MCP):
- Покажи как токен хранится в config

Проверь синхронизацию:
1. Формат токена одинаковый?
2. Expiration handling консистентный?
3. Нужны ли изменения в протоколе?
"
```

#### Сценарий 2: Deployment preparation

```bash
# Backend
cd ~/zenzefi-backend
claude "/deploy-check"

# Client
cd ~/zenzefi-client
claude "/build-exe"

# Review
claude "
Сгенерируй deployment checklist:
- Backend: Все миграции применены?
- Backend: Tests passing?
- Backend: Docker images обновлены?
- Client: Executable собран?
- Client: SSL certs included?
- Оба: Версии синхронизированы?
"
```

---

## 🔧 Troubleshooting

### MCP Server Issues

#### Проблема: MCP сервер не подключается

```bash
# Проверка статуса
/mcp

# Debug mode (в новом терминале)
claude --debug

# Проверка конфигурации
cat ~/.claude.json | jq '.mcpServers'

# Тест вручную (для npx серверов)
echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05"},"id":1}' | npx @modelcontextprotocol/server-postgres
```

#### Проблема: PostgreSQL MCP connection failed

```bash
# Проверка подключения
psql -h localhost -U zenzefi -d zenzefi_dev

# Проверка переменной окружения
echo $DATABASE_URL

# Исправление в ~/.claude.json
{
  "mcpServers": {
    "postgres": {
      "env": {
        "DATABASE_URL": "postgresql://zenzefi:devpassword@localhost:5432/zenzefi_dev"
      }
    }
  }
}

# Перезапуск Claude Code
```

#### Проблема: GitHub MCP unauthorized

```bash
# Проверка токена
curl -H "Authorization: token ghp_xxx" https://api.github.com/user

# Создание нового токена
# https://github.com/settings/tokens
# Scope: repo, read:user

# Обновление в ~/.claude.json
```

---

### Agent Issues

#### Проблема: Агент не доступен

```bash
# Проверка установленных плагинов
/plugin list

# Переустановка
/plugin uninstall python-development
/plugin install python-development@wshobson/agents

# Restart Claude Code (важно!)
```

#### Проблема: Marketplace не найден

```bash
# Проверка
/plugin marketplace list

# Добавление
/plugin marketplace add wshobson/agents

# Обновление
/plugin marketplace update wshobson/agents
```

---

### Custom Plugin Issues

#### Проблема: Кастомный плагин не загружается

```bash
# Валидация plugin.json
cat .claude-plugin/zenzefi-backend-dev/.claude-plugin/plugin.json | jq .

# Проверка структуры
tree .claude-plugin/zenzefi-backend-dev/

# Ожидаемая структура:
# .claude-plugin/zenzefi-backend-dev/
# ├── .claude-plugin/
# │   └── plugin.json
# ├── commands/
# ├── agents/
# └── hooks/

# Reload
/plugin reload zenzefi-backend-dev
```

---

### Performance Issues

#### Проблема: Claude Code медленный

```bash
# Проверка контекста
/context

# Много MCP серверов загружают контекст
# Решение: disable ненужные
/mcp disable redis-tools

# Или используйте project scope вместо user
claude mcp remove postgres --scope user
claude mcp add postgres --scope project ...
```

---

## 📊 Метрики успеха

### KPIs после интеграции

**Backend:**
- ⏱️ Время на создание endpoint: **-50%** (30 мин → 15 мин)
- 🧪 Code coverage: **+15%** (текущий 84% → цель 90%+)
- 🐛 Bugs найденных security auditor: **5+ за неделю**
- 📦 Миграций создано через MCP: **10+ за месяц**

**Client:**
- ⏱️ Время на UI feature: **-40%**
- 🎨 Theme consistency: **100%**
- 🔧 Build успешность: **95%+**
- 📝 Documentation coverage: **80%+**

**Общее:**
- 💬 Вопросов в документации: **-60%**
- 🚀 Deployment time: **-30%**
- 😊 Developer satisfaction: **+40%**

---

## 📚 Дополнительные ресурсы

### Документация

- [Claude Code Official Docs](https://docs.claude.com/en/docs/claude-code)
- [MCP Specification](https://github.com/anthropics/mcp)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Plugin Development Guide](https://docs.claude.com/en/docs/claude-code/plugins)

### Community

- [Discord: Claude Code Channel](https://discord.gg/anthropic)
- [GitHub: wshobson/agents](https://github.com/wshobson/agents)
- [GitHub: Dev-GOM/claude-code-marketplace](https://github.com/Dev-GOM/claude-code-marketplace)

### Видео туториалы

- [YouTube: Claude Code Basics](https://youtube.com/@anthropic)
- [YouTube: MCP Server Setup](https://youtube.com/mcp-tutorial)

---

## 🎓 Обучение команды

### Неделя 1: Основы

**День 1-2: MCP серверы**
- Что такое MCP
- Установка базовых серверов
- Первые команды

**День 3-4: Агенты**
- Концепция агентов
- Установка из marketplace
- Примеры использования

**День 5: Практика**
- Решение реальных задач
- Q&A сессия

### Неделя 2: Продвинутое

**День 1-2: Кастомизация**
- Создание custom MCP
- Разработка плагинов

**День 3-4: Hooks и автоматизация**
- PostToolUse hooks
- Workflow automation

**День 5: Team setup**
- Настройка team config
- Best practices

---

## ✅ Чеклист готовности

### Backend

```markdown
- [ ] PostgreSQL MCP установлен и протестирован
- [ ] Docker MCP работает
- [ ] GitHub MCP настроен
- [ ] Redis custom MCP создан
- [ ] FastAPI MCP интегрирован
- [ ] Python-development agent установлен
- [ ] Database-architect agent установлен
- [ ] Security-auditor agent установлен
- [ ] BACKEND.md обновлен с инструкциями по MCP
- [ ] Team settings.json создан
- [ ] Кастомный plugin zenzefi-backend-dev создан
```

### Client

```markdown
- [ ] Filesystem MCP установлен
- [ ] Docker MCP работает
- [ ] GitHub MCP настроен
- [ ] Puppeteer MCP установлен
- [ ] Python-development agent установлен
- [ ] Performance-optimizer agent установлен
- [ ] CLAUDE.md обновлен с инструкциями по MCP
- [ ] Кастомный plugin zenzefi-client-dev создан
```

### Общее

```markdown
- [ ] Sequential-thinking установлен
- [ ] Brave Search настроен
- [ ] Git MCP работает
- [ ] ~/.claude.json полностью настроен
- [ ] Команда обучена базовым командам
- [ ] Документация обновлена
- [ ] Метрики успеха определены
```

---

## 🎯 Следующие шаги

После завершения интеграции:

1. **Измерение метрик** (еженедельно)
   - Отслеживайте KPIs
   - Собирайте feedback от команды

2. **Итерация** (ежемесячно)
   - Добавляйте новые агенты по необходимости
   - Обновляйте кастомные плагины
   - Оптимизируйте workflow

3. **Масштабирование**
   - Расширяйте на другие проекты
   - Создавайте shared marketplace
   - Документируйте best practices

4. **Обучение**
   - Регулярные knowledge sharing сессии
   - Обновление документации
   - Онбординг новых разработчиков

---

**Версия документа:** 1.0  
**Последнее обновление:** 29 октября 2025  
**Авторы:** Zenzefi Development Team

---

## 🤝 Contribution

Этот документ - живой артефакт. Обновляйте его по мере:
- Добавления новых инструментов
- Обнаружения лучших практик
- Изменения workflow
- Feedback от команды

**Как обновить:**
```bash
# Backend
git checkout -b docs/update-integration-plan
# Edit INTEGRATION_PLAN.md
git commit -m "docs: update integration plan with X"
git push origin docs/update-integration-plan
# Create PR
```

---

## 📞 Поддержка

**Вопросы по интеграции:**
- Создайте issue в GitHub
- Спросите в team channel
- Консультация с @backend-architect или @python-developer

**Проблемы с инструментами:**
- Проверьте [Troubleshooting](#troubleshooting)
- Обратитесь к официальной документации
- Discord community

---

**Happy coding with Claude! 🚀**
