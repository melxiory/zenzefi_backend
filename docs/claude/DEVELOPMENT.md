# Development Guide

Comprehensive guide for development commands, tools, and workflows for zenzefi_backend.

## Prerequisites

```bash
# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Copy environment file
cp .env.example .env
# Edit .env with your settings (SECRET_KEY, POSTGRES_*, REDIS_*, ZENZEFI_TARGET_URL, BACKEND_URL)
```

## Development Server

### Starting the Development Environment

```bash
# Start PostgreSQL and Redis (required for development)
docker-compose -f docker-compose.dev.yml up -d

# Check services are running
docker-compose -f docker-compose.dev.yml ps

# Apply database migrations
poetry run alembic upgrade head

# Start dev server with hot reload (option 1: uvicorn directly)
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start dev server with hot reload (option 2: use run_dev.py for easier IDE debugging)
python run_dev.py
```

### Stopping Services

```bash
# Stop services
docker-compose -f docker-compose.dev.yml down

# Stop and remove volumes (clean slate)
docker-compose -f docker-compose.dev.yml down -v
```

## Database Management

### Migrations

```bash
# Create new migration (autogenerate from models)
poetry run alembic revision --autogenerate -m "Description"

# Apply all migrations
poetry run alembic upgrade head

# Rollback one migration
poetry run alembic downgrade -1

# View migration history
poetry run alembic history

# View current database version
poetry run alembic current
```

### Database Utilities

```bash
# Initialize database (create tables)
poetry run python scripts/init_db.py

# Create superuser
poetry run python scripts/create_superuser.py

# Reset database (drop and recreate all tables)
poetry run python scripts/reset_database.py

# Check database status
poetry run python scripts/check_database.py

# Clear database (delete all data but keep tables)
poetry run python scripts/clear_database.py

# Create test database
poetry run python scripts/create_test_database.py

# Test authentication flow (register, login, create token)
poetry run python scripts/test_create_token.py
```

**Note:** `test_create_token.py` registers a user, logs in, and creates a 24-hour access token saved to `test_token.txt` for use with the Desktop Client.

## Testing

### Running Tests

```bash
# Run all tests (requires docker-compose.dev.yml services running)
poetry run pytest tests/ -v

# Run specific test file
poetry run pytest tests/test_api_tokens.py -v

# Run single test
poetry run pytest tests/test_api_tokens.py::TestTokenPurchaseEndpoint::test_purchase_token_success -v

# Run with coverage
poetry run pytest tests/ --cov=app --cov-report=term

# Run with HTML coverage report
poetry run pytest tests/ --cov=app --cov-report=html

# Run tests in parallel (faster)
poetry run pytest tests/ -n auto
```

**Important:**
- Tests require PostgreSQL and Redis running via `docker-compose.dev.yml`
- Tests use **real services**, not mocks, for integration testing
- Tests use a separate `zenzefi_test` database (must be created manually)
- Create test database: `docker exec -it zenzefi-postgres-dev psql -U zenzefi -c "CREATE DATABASE zenzefi_test;"`

See [TESTING.md](./TESTING.md) for detailed testing guide.

## Code Quality

```bash
# Format code
poetry run black app/

# Sort imports
poetry run isort app/

# Lint
poetry run flake8 app/

# Type checking
poetry run mypy app/
```

## Docker Management

### Viewing Logs

```bash
# View all logs
docker-compose -f docker-compose.dev.yml logs -f

# View PostgreSQL logs only
docker-compose -f docker-compose.dev.yml logs -f postgres

# View Redis logs only
docker-compose -f docker-compose.dev.yml logs -f redis
```

### Container Operations

```bash
# Restart services
docker-compose -f docker-compose.dev.yml restart

# Restart specific service
docker-compose -f docker-compose.dev.yml restart postgres

# Check container status
docker-compose -f docker-compose.dev.yml ps

# View resource usage
docker stats
```

### Accessing Services

```bash
# Access PostgreSQL shell
docker exec -it zenzefi-postgres-dev psql -U zenzefi -d zenzefi_dev

# Access Redis CLI
docker exec -it zenzefi-redis-dev redis-cli

# Test Redis connection
docker exec -it zenzefi-redis-dev redis-cli ping
```

## Development Workflow

### Adding New Endpoint

1. Create/update schema in `app/schemas/`
2. Add endpoint to router in `app/api/v1/`
3. Implement business logic in `app/services/`
4. Write tests in `tests/test_api_*.py`
5. Run tests: `poetry run pytest tests/ -v`

### Adding Database Model

1. Create model in `app/models/`
2. Import in `app/models/__init__.py`
3. Create migration: `poetry run alembic revision --autogenerate -m "Add table"`
4. Review generated migration in `alembic/versions/`
5. Apply migration: `poetry run alembic upgrade head`
6. Update tests to use new model

### Modifying Existing Tests

When changing API behavior:
1. Run tests to see failures: `poetry run pytest tests/ -v`
2. Update test assertions to match new behavior
3. Check test documentation for expected status codes
4. Verify all related tests still pass

## Environment Setup

### Required Environment Variables

```bash
# JWT and Security
SECRET_KEY=your-secret-key-here

# PostgreSQL
POSTGRES_SERVER=localhost
POSTGRES_USER=zenzefi
POSTGRES_PASSWORD=your-password
POSTGRES_DB=zenzefi_dev

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Zenzefi Target
ZENZEFI_TARGET_URL=https://zenzefi.melxiory.ru

# Backend URL for content rewriter
BACKEND_URL=http://localhost:8000
```

### Optional Environment Variables

```bash
# Debug mode
DEBUG=False

# JWT expiration (minutes)
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Redis authentication
REDIS_PASSWORD=
REDIS_DB=0

# Cookie settings
COOKIE_SECURE=False  # True in production
COOKIE_SAMESITE=lax  # "none" in production with HTTPS

# Health checks
HEALTH_CHECK_INTERVAL=50
HEALTH_CHECK_TIMEOUT=10.0

# Token pricing (currently 0.0 for MVP)
TOKEN_PRICE_1H=0.0
TOKEN_PRICE_12H=0.0
TOKEN_PRICE_24H=0.0
TOKEN_PRICE_WEEK=0.0
TOKEN_PRICE_MONTH=0.0
```

## Helpful Resources

- **API Docs (when running):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health
- **Detailed Health:** http://localhost:8000/health/detailed

## Common Tasks

### Quick Start (Fresh Setup)

```bash
# 1. Start services
docker-compose -f docker-compose.dev.yml up -d

# 2. Create test database
docker exec -it zenzefi-postgres-dev psql -U zenzefi -c "CREATE DATABASE zenzefi_test;"

# 3. Run migrations
poetry run alembic upgrade head

# 4. Start dev server
python run_dev.py
```

### Daily Development

```bash
# Start services (if stopped)
docker-compose -f docker-compose.dev.yml up -d

# Start dev server
python run_dev.py

# Run tests before commit
poetry run pytest tests/ -v
```

### Clean Restart

```bash
# Stop everything
docker-compose -f docker-compose.dev.yml down -v

# Start fresh
docker-compose -f docker-compose.dev.yml up -d
poetry run alembic upgrade head
python run_dev.py
```

## Notes

- Development primarily on Windows; commands may need adjustment for Linux/Mac
- Always run tests before committing changes
- Use `python run_dev.py` for easier debugging with IDE breakpoints
- PostgreSQL data persists in Docker volumes; use `-v` flag to clear
