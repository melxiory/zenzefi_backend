# Этап 4: Production Readiness

**Статус:** ⏳ ЧАСТИЧНО РЕАЛИЗОВАНО
**Зависимости:** Этапы 2-3 завершены
**Время:** 4-6 дней

---

## Цель

Подготовить систему к production deployment с полным набором инфраструктурных компонентов.

---

## ✅ УЖЕ РЕАЛИЗОВАНО (из Этапа 1)

- Docker Compose production (docker-compose.yml)
- Healthchecks для сервисов (PostgreSQL, Redis)
- OpenAPI/Swagger (/docs, /redoc)
- Deployment guide (docs/DEPLOYMENT_TAILSCALE.md)

---

## Задачи

### Задача 1: Rate Limiting (1-2 дня)

#### Rate Limiter Middleware

```python
# app/middleware/rate_limit.py
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.redis import get_redis_client
import time

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-based rate limiting with sliding window"""

    LIMITS = {
        "auth": {"requests": 5, "window": 3600},  # 5 attempts/hour (IP)
        "api": {"requests": 100, "window": 60},    # 100 req/min (user)
        "proxy": {"requests": 1000, "window": 60}  # 1000 req/min (token)
    }

    async def dispatch(self, request: Request, call_next):
        redis = get_redis_client()
        path = request.url.path

        # Determine rate limit type
        if path.startswith("/api/v1/auth"):
            limit_type = "auth"
            identifier = request.client.host  # IP-based
        elif path.startswith("/api/v1/proxy"):
            limit_type = "proxy"
            identifier = request.state.token_id if hasattr(request.state, "token_id") else None
        else:
            limit_type = "api"
            identifier = request.state.user_id if hasattr(request.state, "user_id") else None

        if identifier:
            limit_config = self.LIMITS[limit_type]
            key = f"rate_limit:{limit_type}:{identifier}"

            # Sliding window counter
            current_time = int(time.time())
            window_start = current_time - limit_config["window"]

            # Remove old entries
            redis.zremrangebyscore(key, 0, window_start)

            # Count current requests
            current_count = redis.zcard(key)

            if current_count >= limit_config["requests"]:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Max {limit_config['requests']} requests per {limit_config['window']}s"
                )

            # Add current request
            redis.zadd(key, {str(current_time): current_time})
            redis.expire(key, limit_config["window"])

        return await call_next(request)
```

#### Bypass для Superusers (опционально)

```python
# Добавить в middleware
if hasattr(request.state, "user") and request.state.user.is_superuser:
    return await call_next(request)  # Skip rate limiting
```

**Добавить в middleware:**
```python
# app/main.py
from app.middleware.rate_limit import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)
```

---

### Задача 2: CI/CD Pipeline (1 день)

#### GitHub Actions - Testing

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: zenzefi_test
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: zenzefi_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install Poetry
        run: pip install poetry

      - name: Install dependencies
        run: poetry install

      - name: Run tests
        env:
          POSTGRES_SERVER: localhost
          POSTGRES_USER: zenzefi_test
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: zenzefi_test
          REDIS_HOST: localhost
          SECRET_KEY: test-secret-key
        run: |
          poetry run alembic upgrade head
          poetry run pytest tests/ -v --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
```

#### GitHub Actions - Deployment

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
    tags:
      - 'v*'

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t zenzefi-backend:${{ github.sha }} -f docker/Dockerfile.backend .

      - name: Push to registry
        run: |
          echo "${{ secrets.DOCKER_PASSWORD }}" | docker login -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin
          docker tag zenzefi-backend:${{ github.sha }} ${{ secrets.DOCKER_USERNAME }}/zenzefi-backend:latest
          docker push ${{ secrets.DOCKER_USERNAME}}/zenzefi-backend:latest

      - name: Deploy to server
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/zenzefi-backend
            docker-compose pull
            docker-compose up -d --force-recreate
```

**Секреты в GitHub (Settings > Secrets):**
- `DOCKER_USERNAME`
- `DOCKER_PASSWORD`
- `SERVER_HOST`
- `SERVER_USER`
- `SSH_PRIVATE_KEY`

---

### Задача 3: Backup Automation (1 день)

#### PostgreSQL Backup Script

```bash
# scripts/backup_database.sh
#!/bin/bash

set -e

BACKUP_DIR="/var/backups/zenzefi"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/zenzefi_backup_${TIMESTAMP}.sql.gz"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Backup PostgreSQL
pg_dump -h localhost -U zenzefi -d zenzefi_db | gzip > "${BACKUP_FILE}"

# Upload to S3/Backblaze (optional)
# aws s3 cp "${BACKUP_FILE}" s3://zenzefi-backups/

# Keep only last 30 days
find "${BACKUP_DIR}" -name "zenzefi_backup_*.sql.gz" -mtime +30 -delete

echo "Backup completed: ${BACKUP_FILE}"
```

#### Cron Job

```bash
# /etc/cron.d/zenzefi-backup
0 3 * * * root /opt/zenzefi-backend/scripts/backup_database.sh >> /var/log/zenzefi-backup.log 2>&1
```

#### Restore Script

```bash
# scripts/restore_backup.sh
#!/bin/bash

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    exit 1
fi

# Stop backend
docker-compose stop backend

# Restore
gunzip -c "$BACKUP_FILE" | psql -h localhost -U zenzefi -d zenzefi_db

# Start backend
docker-compose start backend

echo "Restore completed from: $BACKUP_FILE"
```

**Сделать скрипты исполняемыми:**
```bash
chmod +x scripts/backup_database.sh
chmod +x scripts/restore_backup.sh
```

---

### Задача 4: Load Testing (1-2 дня)

#### Locust Test Suite

```python
# tests/load/locustfile.py
from locust import HttpUser, task, between
import secrets

class ZenzefiUser(HttpUser):
    wait_time = between(1, 3)
    host = "http://localhost:8000"

    def on_start(self):
        """Register and login"""
        username = f"loadtest_{secrets.token_hex(8)}"
        email = f"{username}@example.com"
        password = "LoadTest123!"

        # Register
        response = self.client.post("/api/v1/auth/register", json={
            "email": email,
            "username": username,
            "password": password
        })

        # Login
        response = self.client.post("/api/v1/auth/login", json={
            "email": email,
            "password": password
        })

        self.jwt_token = response.json()["access_token"]

        # Purchase token (need to top up balance first)
        # For load testing, assume balance is topped up externally

    @task(5)
    def get_balance(self):
        """Get currency balance"""
        self.client.get(
            "/api/v1/currency/balance",
            headers={"Authorization": f"Bearer {self.jwt_token}"}
        )

    @task(10)
    def list_tokens(self):
        """List my tokens"""
        self.client.get(
            "/api/v1/tokens/my-tokens",
            headers={"Authorization": f"Bearer {self.jwt_token}"}
        )

    @task(2)
    def health_check(self):
        """Health check endpoint"""
        self.client.get("/health")
```

#### Run Load Test

```bash
# Install Locust
poetry add --group dev locust

# Run load test (100 concurrent users, 10 users/second spawn rate)
locust -f tests/load/locustfile.py --users 100 --spawn-rate 10 --host http://localhost:8000

# Headless mode (no web UI)
locust -f tests/load/locustfile.py --users 100 --spawn-rate 10 --headless --run-time 5m
```

#### Performance Benchmarks

**Target metrics:**
- 1000 requests/second (sustained)
- p50 latency < 50ms
- p95 latency < 200ms
- p99 latency < 500ms
- 0% error rate under normal load

**Optimization tips:**
- Увеличить connection pool для PostgreSQL (max 50 connections)
- Redis пулы для быстрого доступа
- Async endpoints для всех I/O операций
- Database query optimization (индексы, EXPLAIN ANALYZE)

---

### Задача 5: SSL/TLS Configuration (опционально)

**Note:** Проект использует Tailscale VPN для безопасности, но можно добавить Nginx с Let's Encrypt для публичного доступа.

#### Nginx Configuration

```nginx
# docker/nginx.conf
server {
    listen 443 ssl http2;
    server_name api.zenzefi.ru;

    ssl_certificate /etc/letsencrypt/live/api.zenzefi.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.zenzefi.ru/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;

    location / {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Certbot Setup

```bash
# Install certbot
apt-get install certbot python3-certbot-nginx

# Obtain certificate
certbot --nginx -d api.zenzefi.ru --email admin@zenzefi.ru --agree-tos

# Auto-renewal (cron)
0 0 1 * * certbot renew --quiet
```

---

### Задача 6: Monitoring Integration (1 день)

#### Grafana Dashboard (опционально)

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - backend

  grafana:
    image: grafana/grafana:latest
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    networks:
      - backend

volumes:
  prometheus_data:
  grafana_data:

networks:
  backend:
    external: true
```

#### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'zenzefi-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
```

**Запуск:**
```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

**Доступ:**
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

**Grafana Dashboards:**
- Импортировать готовый dashboard для FastAPI/Prometheus
- Или создать свой с метриками из `/metrics` endpoint

---

## Roadmap Этапа 4

| День | Задача | Описание |
|------|--------|----------|
| 1 | Rate Limiting | Redis sliding window middleware |
| 2 | CI/CD Pipeline | GitHub Actions (test, deploy) |
| 3 | Backup Automation | Cron job, S3 upload, restore script |
| 4-5 | Load Testing | Locust suite, performance benchmarks |
| 6 | Monitoring | Prometheus + Grafana dashboards |

**Результат:** Production-ready система с CI/CD, backups, load testing, monitoring.

---

## Testing

**Test Coverage:**
```python
# tests/test_rate_limit.py
test_rate_limit_auth_endpoint()
test_rate_limit_proxy_endpoint()
test_rate_limit_bypass_superuser()

# tests/load/
locustfile.py - Load testing suite
```

**Запуск:**
```bash
poetry run pytest tests/test_rate_limit.py -v
locust -f tests/load/locustfile.py --users 100 --spawn-rate 10
```

---

## Deployment Checklist

### Pre-Production

- [ ] Все тесты проходят (104/104)
- [ ] Load testing выполнен, метрики в норме
- [ ] Rate limiting настроен
- [ ] Backup automation настроен
- [ ] CI/CD pipeline работает
- [ ] SSL/TLS сертификаты получены (если не Tailscale)
- [ ] Environment variables проверены
- [ ] Database миграции применены

### Production Deployment

```bash
# 1. Clone repository
git clone https://github.com/yourorg/zenzefi-backend.git
cd zenzefi-backend

# 2. Create .env file
cp .env.example .env
# Edit .env with production values

# 3. Start services
docker-compose up -d

# 4. Run migrations
docker-compose exec backend poetry run alembic upgrade head

# 5. Create superuser
docker-compose exec backend poetry run python scripts/create_superuser.py

# 6. Check health
curl https://api.zenzefi.ru/health
```

### Post-Deployment

- [ ] Health checks работают
- [ ] Prometheus metrics доступны
- [ ] Grafana dashboards настроены
- [ ] Backup cronjob добавлен
- [ ] Logs monitoring настроен
- [ ] Alerts настроены (email/Slack)

---

**Следующие этапы:** [Future Features](./PHASE_FUTURE.md) - Token Bundles, Referrals, Analytics, Notifications

---

**См. также:**
- [PHASE_1_MVP.md](./PHASE_1_MVP.md) - MVP (завершён)
- [PHASE_2_CURRENCY.md](./PHASE_2_CURRENCY.md) - Система валюты
- [PHASE_3_MONITORING.md](./PHASE_3_MONITORING.md) - Мониторинг (предыдущий этап)
- [DEPLOYMENT_TAILSCALE.md](../DEPLOYMENT_TAILSCALE.md) - Docker deployment guide
- [BACKEND.md](../BACKEND.md) - Overview
