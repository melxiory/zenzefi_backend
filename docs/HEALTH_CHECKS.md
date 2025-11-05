# Health Checks Documentation

## Overview

Zenzefi Backend включает систему мониторинга состояния (health checks), которая автоматически проверяет работоспособность всех критичных компонентов системы.

## Architecture

```
┌─────────────────────────────────────────┐
│  APScheduler (Background)               │
│  Every 50 seconds:                      │
│  1. Check PostgreSQL                    │
│  2. Check Redis                         │
│  3. Check Zenzefi Server                │
│  4. Aggregate results → Redis           │
└─────────────────────────────────────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │  Redis Cache         │
         │  Key: "health:status"│
         │  TTL: 120 seconds    │
         │  (Full HealthResponse)│
         └──────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌──────────────────┐    ┌──────────────────────┐
│  GET /health     │    │  GET /health/detailed│
│  Minimal (61B)   │    │  Full (348B)         │
│  status+timestamp│    │  All service details │
│  ~1ms response   │    │  ~1ms response       │
└──────────────────┘    └──────────────────────┘
```

## Components

### 1. HealthCheckService

**Location:** `app/services/health_service.py`

Выполняет проверки всех компонентов системы:
- **PostgreSQL** - простой `SELECT 1` запрос
- **Redis** - `PING` команда
- **Zenzefi Server** - `HEAD` запрос на `ZENZEFI_TARGET_URL`

### 2. HealthCheckScheduler

**Location:** `app/core/health_scheduler.py`

APScheduler интеграция для периодических проверок:
- Интервал: 50 секунд (настраивается через `HEALTH_CHECK_INTERVAL`)
- Первая проверка: сразу при старте приложения
- Результаты кэшируются в Redis с TTL 120 секунд

### 3. Health Schemas

**Location:** `app/schemas/health.py`

Pydantic модели для типизации ответов:
- `ServiceStatus` - статус отдельного сервиса (up/down/unknown)
- `OverallStatus` - общий статус системы (healthy/degraded/unhealthy)
- `HealthResponse` - полный ответ с детальной информацией (для `/health/detailed`)
- `SimpleHealthResponse` - минимальный ответ (для `/health`)

## API Endpoints

### GET /health

Возвращает **минимальный** статус здоровья системы (только status и timestamp).

**Назначение:** Быстрая проверка для мониторинговых систем, балансировщиков нагрузки и health probes.

**Response (61 bytes):**

```json
{
  "status": "healthy",
  "timestamp": "2025-11-05T12:15:24.273626"
}
```

**Status Codes:**

- `200 OK` - Health check executed successfully (check `status` field for actual health)

**Status Field Values:**

- `healthy` - All services are up (3/3)
- `degraded` - Zenzefi is down, but DB + Redis are up (2/3) - non-critical
- `unhealthy` - DB or Redis is down (critical services)

**Performance:**
- Response time: ~1ms (cached from Redis)
- Response size: 61 bytes
- No detailed service information (lightweight)

---

### GET /health/detailed

Возвращает **полный** статус здоровья системы со всеми деталями по каждому сервису.

**Назначение:** Детальная диагностика, debugging, внутренний мониторинг с метриками.

**Response (348 bytes):**

```json
{
  "status": "healthy",
  "timestamp": "2025-11-05T01:53:05.921000",
  "checks": {
    "database": {
      "status": "up",
      "latency_ms": 5.73,
      "error": null,
      "url": null
    },
    "redis": {
      "status": "up",
      "latency_ms": 1.18,
      "error": null,
      "url": null
    },
    "zenzefi": {
      "status": "up",
      "latency_ms": 1651.53,
      "error": null,
      "url": "https://zenzefi-win11-server"
    }
  },
  "overall": {
    "healthy_count": 3,
    "total_count": 3
  }
}
```

**Status Codes:**

- `200 OK` - Health check executed successfully

**Performance:**
- Response time: ~1ms (cached from Redis)
- Response size: 348 bytes
- Includes latency metrics for each service
- Includes error messages if service is down

---

### When to Use Which Endpoint?

| Use Case | Endpoint | Reason |
|----------|----------|--------|
| Kubernetes liveness/readiness probes | `/health` | Minimal overhead, fast response |
| Load balancer health checks | `/health` | Lightweight, only needs status |
| Monitoring dashboards (Prometheus, Grafana) | `/health/detailed` | Need metrics (latency, errors) |
| Manual debugging/diagnostics | `/health/detailed` | Full visibility into each service |
| High-frequency polling (>1 req/sec) | `/health` | Reduces network bandwidth |
| CI/CD pipeline validation | `/health` | Fast, simple status check |
| Alerting with detailed context | `/health/detailed` | Error messages for notifications |

**Recommendation:** Use `/health` by default, switch to `/health/detailed` only when you need diagnostics or metrics.

## Configuration

**Environment Variables (.env):**

```bash
# Health Check Settings
HEALTH_CHECK_INTERVAL=50  # Check interval in seconds (default: 50)
HEALTH_CHECK_TIMEOUT=10.0  # Timeout for each check in seconds (default: 10.0)
```

## Usage Examples

### cURL

```bash
# Minimal health check (recommended for monitoring)
curl http://localhost:8000/health

# Detailed health check (for debugging)
curl http://localhost:8000/health/detailed

# Pretty-printed detailed JSON
curl -s http://localhost:8000/health/detailed | python -m json.tool

# Check only status field (minimal endpoint)
curl -s http://localhost:8000/health | jq '.status'

# Check database latency (detailed endpoint)
curl -s http://localhost:8000/health/detailed | jq '.checks.database.latency_ms'
```

### Python (httpx)

```python
import httpx

# Minimal health check (fast, lightweight)
response = httpx.get("http://localhost:8000/health")
health = response.json()

if health["status"] == "healthy":
    print("✓ All services are healthy!")
elif health["status"] == "degraded":
    print("⚠ Warning: System is degraded")
else:
    print("✗ Critical: System is unhealthy!")

# Detailed health check (with diagnostics)
response = httpx.get("http://localhost:8000/health/detailed")
health = response.json()

if health["status"] != "healthy":
    print(f"Services up: {health['overall']['healthy_count']}/3")
    # Check individual service errors
    for service, check in health["checks"].items():
        if check["status"] != "up":
            print(f"  {service}: {check['error']}")
        else:
            print(f"  {service}: OK (latency: {check['latency_ms']}ms)")
```

### Monitoring Integration

**Prometheus:**

Можно использовать Prometheus для scraping `/health` endpoint и создания alerting rules:

```yaml
scrape_configs:
  - job_name: 'zenzefi_health'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/health'
    scrape_interval: 60s
```

**Grafana:**

Создать dashboard с панелями:
- Overall Status (gauge: healthy/degraded/unhealthy)
- Service Latencies (graph: database_latency, redis_latency, zenzefi_latency)
- Uptime Percentage (stat: healthy_count / total_count)

## Troubleshooting

### Health Check Shows "degraded" or "unhealthy"

1. Проверить логи сервера:
   ```bash
   # В логах будут детальные ошибки
   tail -f logs/app.log | grep health
   ```

2. Проверить статус сервисов вручную:
   ```bash
   # PostgreSQL
   docker exec -it zenzefi-postgres-dev psql -U zenzefi -c "SELECT 1"

   # Redis
   docker exec -it zenzefi-redis-dev redis-cli PING

   # Zenzefi Server
   curl -I https://zenzefi-win11-server
   ```

3. Проверить конфигурацию:
   ```bash
   # Убедиться что ZENZEFI_TARGET_URL установлен правильно
   grep ZENZEFI_TARGET_URL .env
   ```

### Scheduler не запускается

Проверить логи при старте приложения:
```bash
poetry run uvicorn app.main:app --reload
# Должна быть строка: "Health check scheduler started (interval: 50s)"
```

### Кэш в Redis не обновляется

Проверить Redis вручную:
```bash
docker exec -it zenzefi-redis-dev redis-cli
> GET health:status
> TTL health:status
```

## Performance

- **Health Check Execution:** ~2-5 секунд (зависит от latency Zenzefi)
- **Cached Response:** ~1ms (чтение из Redis)
- **Memory Overhead:** ~500KB (APScheduler + cached data)
- **CPU Usage:** Negligible (<0.1% average)

## Future Improvements

- [ ] Добавить проверку дополнительных сервисов (например, Celery worker)
- [ ] Prometheus metrics endpoint (`/metrics`)
- [ ] Alerting через email/Slack при degraded/unhealthy статусе
- [ ] Detailed health check для каждого компонента (`/health/database`, `/health/redis`, etc.)
- [ ] Health check dashboard (HTML страница с live updates)
