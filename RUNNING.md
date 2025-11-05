# Running Zenzefi Backend

Quick reference guide for starting the development server.

## Quick Start

### Option 1: Auto-Detect Poetry Environment (Recommended)

Simply run the script - it will automatically find and use the correct Poetry environment:

```bash
python run_dev.py
```

**What happens:**
- Script checks if dependencies are available
- If not, automatically finds Poetry virtual environment
- Restarts with correct Python interpreter
- Starts development server on http://0.0.0.0:8000

### Option 2: Using Poetry Directly

```bash
poetry run python run_dev.py
```

### Option 3: Using Uvicorn Directly

```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## IDE Configuration

### PyCharm

1. **Settings** → **Project: zenzefi_backend** → **Python Interpreter**
2. Click **Add Interpreter** → **Poetry Environment**
3. Select existing Poetry environment (PyCharm will auto-detect)
4. Apply settings
5. Run `run_dev.py` directly from IDE (right-click → Run)

### Visual Studio Code

1. Open Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Type "Python: Select Interpreter"
3. Choose the Poetry virtualenv (starts with `zenzefi-backend-...`)
4. Run `run_dev.py` in integrated terminal or use debugger

### Cursor / Other IDEs

Configure Python interpreter to use Poetry virtual environment:

```bash
# Get Poetry virtualenv path
poetry env info --path

# Example output (Windows):
# C:\Users\YourUser\AppData\Local\pypoetry\Cache\virtualenvs\zenzefi-backend-XXXXX-py3.13

# Set this as your project interpreter
```

## Verification

After starting the server, verify it's running:

```bash
# Check basic endpoint
curl http://localhost:8000/

# Check health status
curl http://localhost:8000/health

# Open interactive docs
# http://localhost:8000/docs
```

Expected health check response:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-05T...",
  "checks": {
    "database": {"status": "up", "latency_ms": 5.73},
    "redis": {"status": "up", "latency_ms": 1.18},
    "zenzefi": {"status": "up", "latency_ms": 178.18}
  },
  "overall": {
    "healthy_count": 3,
    "total_count": 3
  }
}
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'apscheduler'"

**Problem:** Running Python without Poetry environment

**Solutions:**
1. Use `python run_dev.py` (auto-detects Poetry environment)
2. Use `poetry run python run_dev.py`
3. Install dependencies: `poetry install`
4. Configure IDE to use Poetry interpreter (see above)

### "Dependencies not found in current Python environment"

**Problem:** Script detected wrong Python environment

**What happens automatically:**
- Script finds Poetry virtualenv
- Restarts with correct Python
- Shows which Python interpreters are being used

**If auto-detection fails:**
```bash
# Install dependencies first
poetry install

# Then run again
python run_dev.py
```

### Port 8000 Already in Use

```bash
# Windows: Find process using port
netstat -ano | findstr :8000

# Kill process by PID
taskkill /PID <pid> /F

# Linux/Mac: Kill process on port 8000
lsof -ti:8000 | xargs kill -9
```

### Database Connection Errors

```bash
# Start PostgreSQL and Redis
docker-compose -f docker-compose.dev.yml up -d

# Check services are running
docker-compose -f docker-compose.dev.yml ps

# Apply migrations
poetry run alembic upgrade head
```

### Redis Connection Errors

```bash
# Check Redis is running
docker-compose -f docker-compose.dev.yml ps redis

# Restart Redis
docker-compose -f docker-compose.dev.yml restart redis

# View Redis logs
docker-compose -f docker-compose.dev.yml logs redis
```

## Development Workflow

### Full Development Setup

```bash
# 1. Install dependencies
poetry install

# 2. Start services (PostgreSQL + Redis)
docker-compose -f docker-compose.dev.yml up -d

# 3. Apply database migrations
poetry run alembic upgrade head

# 4. Start development server
python run_dev.py
```

### Hot Reload

The development server uses `--reload` flag, which means:
- Code changes are automatically detected
- Server restarts automatically when files change
- No need to manually restart

**Note:** Changes to `.env` file require manual restart

### Stopping the Server

```bash
# Press Ctrl+C in terminal
# Or close terminal window
```

## Environment Variables

Required variables in `.env`:

```bash
# Security
SECRET_KEY=your-secret-key-here

# Database
POSTGRES_SERVER=localhost
POSTGRES_USER=zenzefi
POSTGRES_PASSWORD=your-password
POSTGRES_DB=zenzefi_dev

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Zenzefi Target
ZENZEFI_TARGET_URL=https://zenzefi-win11-server

# Backend URL (for content rewriter)
BACKEND_URL=http://localhost:8000
```

See `.env.example` for complete list of configuration options.

## API Endpoints

After starting server:

- **Root:** http://localhost:8000/
- **API Docs (Swagger):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI Schema:** http://localhost:8000/openapi.json
- **Health Check:** http://localhost:8000/health

## Logs

Logs are output to console by default. To configure logging, see `app/core/logging.py`.

**Log Levels:**
- DEBUG: Detailed information (database queries, Redis operations)
- INFO: General information (startup, health checks)
- WARNING: Warning messages (non-critical issues)
- ERROR: Error messages (failed health checks, exceptions)

## Additional Resources

- **Main Documentation:** `CLAUDE.md`
- **Deployment Guide:** `docs/DEPLOYMENT.md`
- **Docker Deployment:** `docs/DEPLOYMENT_TAILSCALE.md`
- **Health Checks:** `docs/HEALTH_CHECKS.md`
- **Backend Architecture:** `docs/BACKEND.md`
