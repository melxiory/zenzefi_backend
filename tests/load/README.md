# Load Testing Suite

Locust-based load testing for Zenzefi Backend performance validation.

## Quick Start

### 1. Install Dependencies

```bash
# Already installed via Poetry
poetry install  # includes locust ^2.31.8
```

### 2. Start Backend

```bash
# Terminal 1: Start development environment
docker-compose -f docker-compose.dev.yml up -d
poetry run alembic upgrade head
python run_dev.py
```

### 3. Run Load Test

**Interactive Mode (Web UI):**
```bash
# Terminal 2: Start Locust with Web UI
locust -f tests/load/locustfile.py --host http://localhost:8000

# Open browser: http://localhost:8089
# Set users (e.g., 100) and spawn rate (e.g., 10 users/second)
# Click "Start swarming"
```

**Headless Mode (Automated):**
```bash
# Run for 5 minutes with 100 concurrent users
locust -f tests/load/locustfile.py \
    --host http://localhost:8000 \
    --users 100 \
    --spawn-rate 10 \
    --run-time 5m \
    --headless \
    --html report.html
```

## Test Scenarios

### ZenzefiUser (Default)

Simulates realistic user workflow:
1. **Registration** - Create new account
2. **Login** - Get JWT token
3. **Balance Top-up** - Mock ZNC purchase (500 ZNC)
4. **Token Purchase** - Buy access tokens (1h, 12h, or 24h)
5. **Balance Check** - Get current ZNC balance (most frequent)
6. **Transaction History** - List recent transactions
7. **Health Check** - Monitor availability

**Task Distribution:**
- `get_balance()` - 10 (most frequent)
- `list_tokens()` - 8
- `get_transactions()` - 5
- `purchase_token()` - 3
- `health_check()` - 2
- `metrics_check()` - 1

### ProxyUser (Optional)

Simulates proxy endpoint usage:
- Requires pre-created access token (pass via `--access-token`)
- Tests device conflict detection (`X-Device-ID` header)
- High-frequency proxy requests

**Usage:**
```bash
# First, create an access token manually
# Then run with token:
locust -f tests/load/locustfile.py \
    --host http://localhost:8000 \
    --access-token "your-access-token-here" \
    --users 50 \
    --spawn-rate 5
```

## Performance Targets

Target metrics for production readiness:

| Metric | Target | Acceptable | Critical |
|--------|--------|------------|----------|
| **Throughput** | 1000 req/s | 500 req/s | < 200 req/s |
| **p50 Latency** | < 50ms | < 100ms | > 200ms |
| **p95 Latency** | < 200ms | < 500ms | > 1000ms |
| **p99 Latency** | < 500ms | < 1000ms | > 2000ms |
| **Error Rate** | < 0.1% | < 1% | > 5% |

## Interpreting Results

### Good Performance
```
Requests/second: 1200 req/s
Median response time: 45ms
95th percentile: 180ms
Failures: 0 (0%)
```

### Degraded Performance
```
Requests/second: 400 req/s
Median response time: 120ms
95th percentile: 600ms
Failures: 12 (0.5%)
```

### Poor Performance (Needs Optimization)
```
Requests/second: 150 req/s
Median response time: 350ms
95th percentile: 1500ms
Failures: 89 (3.2%)
```

## Common Issues & Solutions

### 1. High Latency (> 200ms p95)

**Possible Causes:**
- Database connection pool exhausted
- Redis bottleneck
- Slow queries (missing indexes)

**Solutions:**
```python
# Increase PostgreSQL connection pool (app/core/database.py)
engine = create_engine(
    DATABASE_URL,
    pool_size=50,  # Increase from default 10
    max_overflow=100,
)

# Optimize Redis pipelining (app/core/redis.py)
# Use Redis pipelining for bulk operations
```

### 2. 429 Rate Limit Errors

**Expected behavior** - Rate limiting middleware is working.

**Adjust limits** (if testing with higher load):
```python
# app/middleware/rate_limit.py
LIMITS = {
    "auth": {"requests": 10, "window": 3600},     # Increased from 5
    "api": {"requests": 200, "window": 60},       # Increased from 100
    "proxy": {"requests": 2000, "window": 60},    # Increased from 1000
}
```

### 3. 402 Payment Required (Insufficient Balance)

**Expected behavior** - Users run out of ZNC during load test.

**Solution:** Load test automatically tops up balance when this occurs.

### 4. Database Connection Errors

**Cause:** Too many concurrent connections.

**Solution:**
```bash
# Increase PostgreSQL max_connections
# docker-compose.dev.yml
environment:
  - POSTGRES_MAX_CONNECTIONS=200  # Default: 100
```

## Advanced Usage

### Custom Load Profile

```python
# Create custom_load.py in tests/load/
from locust import LoadTestShape

class CustomShape(LoadTestShape):
    """
    Gradual ramp-up load profile
    - 0-2 min: 0 → 50 users
    - 2-5 min: 50 users (steady)
    - 5-7 min: 50 → 100 users
    - 7-10 min: 100 users (steady)
    """
    def tick(self):
        run_time = self.get_run_time()

        if run_time < 120:
            # Ramp up to 50 users
            return (int(run_time / 2.4), 1)
        elif run_time < 300:
            # Steady 50 users
            return (50, 1)
        elif run_time < 420:
            # Ramp up to 100 users
            return (50 + int((run_time - 300) / 2.4), 1)
        elif run_time < 600:
            # Steady 100 users
            return (100, 1)
        else:
            return None  # Stop test
```

Run with custom shape:
```bash
locust -f tests/load/locustfile.py \
    -f tests/load/custom_load.py \
    --host http://localhost:8000 \
    --headless
```

### Distributed Load Testing

Run Locust across multiple machines for higher load:

**Master node:**
```bash
locust -f tests/load/locustfile.py \
    --master \
    --host http://localhost:8000
```

**Worker nodes (on other machines):**
```bash
locust -f tests/load/locustfile.py \
    --worker \
    --master-host <master-ip>
```

## Continuous Performance Testing

Integrate load testing into CI/CD pipeline:

```yaml
# .github/workflows/performance.yml
name: Performance Tests

on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday 2 AM
  workflow_dispatch:

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Start services
        run: docker-compose -f docker-compose.dev.yml up -d

      - name: Run load test
        run: |
          poetry install
          poetry run locust -f tests/load/locustfile.py \
            --host http://localhost:8000 \
            --users 100 \
            --spawn-rate 10 \
            --run-time 5m \
            --headless \
            --html report.html

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: performance-report
          path: report.html
```

## Resources

- [Locust Documentation](https://docs.locust.io/)
- [Performance Testing Best Practices](https://docs.locust.io/en/stable/writing-a-locustfile.html)
- [Distributed Load Testing](https://docs.locust.io/en/stable/running-distributed.html)

---

**Last updated:** 2025-11-17
