# Troubleshooting Guide

Common development issues and their solutions for zenzefi_backend.

## Database Connection Errors

### Issue: "could not connect to server" or "password authentication failed"

**Symptoms:**
- Cannot connect to PostgreSQL
- Authentication failures
- Connection timeout errors

**Solutions:**

```bash
# 1. Check if PostgreSQL is running
docker-compose -f docker-compose.dev.yml ps

# 2. Check PostgreSQL logs
docker-compose -f docker-compose.dev.yml logs postgres

# 3. Restart PostgreSQL
docker-compose -f docker-compose.dev.yml restart postgres

# 4. Verify connection manually
docker exec -it zenzefi-postgres-dev psql -U zenzefi -d zenzefi_dev

# 5. Check environment variables
cat .env | grep POSTGRES

# 6. If all else fails, recreate containers
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up -d
```

**Common causes:**
- PostgreSQL container not running
- Wrong credentials in `.env`
- Port 5432 already in use by another service
- Network issues between containers

---

## Redis Connection Errors

### Issue: "Error connecting to Redis"

**Symptoms:**
- Cannot connect to Redis
- Connection refused errors
- Token validation failures

**Solutions:**

```bash
# 1. Check if Redis is running
docker-compose -f docker-compose.dev.yml ps

# 2. Test Redis connection
docker exec -it zenzefi-redis-dev redis-cli ping

# 3. Check Redis logs
docker-compose -f docker-compose.dev.yml logs redis

# 4. Restart Redis
docker-compose -f docker-compose.dev.yml restart redis

# 5. Check Redis configuration
docker exec -it zenzefi-redis-dev redis-cli INFO

# 6. Verify Redis is accessible from host
redis-cli -h localhost -p 6379 ping
```

**Common causes:**
- Redis container not running
- Port 6379 already in use
- Redis password mismatch (if configured)
- Network issues

---

## Migration Errors

### Issue: Migration conflicts or "target database is not up to date"

**Symptoms:**
- Alembic migration failures
- "Target database is not up to date" error
- Conflicting migration versions
- Database schema mismatch

**Solutions:**

```bash
# 1. Check current migration version
poetry run alembic current

# 2. View migration history
poetry run alembic history

# 3. Check which migrations are pending
poetry run alembic heads

# 4. Downgrade to previous version (if needed)
poetry run alembic downgrade -1

# 5. Upgrade to latest
poetry run alembic upgrade head

# 6. If migrations are broken, reset database (CAUTION: deletes all data)
poetry run python scripts/reset_database.py
poetry run alembic upgrade head
```

**For conflicting migrations:**

```bash
# 1. Identify the conflict
poetry run alembic history

# 2. Merge conflicting branches
poetry run alembic merge <rev1> <rev2> -m "Merge migrations"

# 3. Apply the merge
poetry run alembic upgrade head
```

**Common causes:**
- Multiple developers creating migrations simultaneously
- Manual database changes without migration
- Deleted migration files
- Incorrect migration order

---

## Test Database Setup

### Issue: Tests fail with "database does not exist"

**Symptoms:**
- `pytest` fails with database errors
- "database zenzefi_test does not exist"
- Connection refused to test database

**Solutions:**

```bash
# 1. Create test database
docker exec -it zenzefi-postgres-dev psql -U zenzefi -c "CREATE DATABASE zenzefi_test;"

# 2. Or use the script
poetry run python scripts/create_test_database.py

# 3. Verify test database exists
docker exec -it zenzefi-postgres-dev psql -U zenzefi -c "\l"

# 4. Check test database connection
docker exec -it zenzefi-postgres-dev psql -U zenzefi -d zenzefi_test -c "SELECT version();"
```

**If test database is corrupted:**

```bash
# Drop and recreate test database
docker exec -it zenzefi-postgres-dev psql -U zenzefi -c "DROP DATABASE IF EXISTS zenzefi_test;"
docker exec -it zenzefi-postgres-dev psql -U zenzefi -c "CREATE DATABASE zenzefi_test;"
```

**Common causes:**
- Test database never created
- Test database dropped accidentally
- PostgreSQL container recreated without persistent volume

---

## Port Conflicts

### Issue: "Address already in use" errors

**Symptoms:**
- Cannot start development server
- Port 8000, 5432, or 6379 already in use
- "bind: address already in use"

**Solutions (Windows):**

```bash
# 1. Check what's using port 8000 (FastAPI)
netstat -ano | findstr :8000

# 2. Check what's using port 5432 (PostgreSQL)
netstat -ano | findstr :5432

# 3. Check what's using port 6379 (Redis)
netstat -ano | findstr :6379

# 4. Kill process by PID
taskkill /PID <pid> /F

# 5. Alternative: Change port in configuration
# For FastAPI: python run_dev.py (modify port in run_dev.py)
# For PostgreSQL: Edit docker-compose.dev.yml ports section
# For Redis: Edit docker-compose.dev.yml ports section
```

**Solutions (Linux/Mac):**

```bash
# 1. Find process using port
lsof -i :8000
lsof -i :5432
lsof -i :6379

# 2. Kill process
kill -9 <pid>

# 3. Or use fuser
fuser -k 8000/tcp
```

**Common causes:**
- Previous server instance still running
- Another application using the same port
- Docker container not properly stopped

---

## Import Errors

### Issue: ModuleNotFoundError or ImportError

**Symptoms:**
- "ModuleNotFoundError: No module named 'app'"
- "ImportError: cannot import name"
- Module not found errors

**Solutions:**

```bash
# 1. Verify Poetry environment is activated
poetry env info

# 2. Reinstall dependencies
poetry install

# 3. Clear Poetry cache
poetry cache clear . --all

# 4. Rebuild environment
poetry env remove python
poetry install

# 5. Check Python version
python --version  # Should be 3.13+

# 6. Verify you're in the correct directory
pwd  # Should be zenzefi_backend/
```

**Common causes:**
- Poetry environment not activated
- Dependencies not installed
- Wrong Python version
- Circular imports in code

---

## JWT Token Issues

### Issue: "Invalid token" or "Token has expired"

**Symptoms:**
- 401 Unauthorized errors
- "Could not validate credentials"
- Token validation failures

**Solutions:**

```bash
# 1. Check SECRET_KEY is set in .env
cat .env | grep SECRET_KEY

# 2. Verify token expiration time
cat .env | grep ACCESS_TOKEN_EXPIRE_MINUTES

# 3. Test token generation
poetry run python scripts/test_create_token.py

# 4. Decode JWT token (debugging)
# Use jwt.io to inspect token payload
```

**Common causes:**
- SECRET_KEY changed between token generation and validation
- Token expired (default: 60 minutes)
- Token format incorrect
- System clock mismatch

---

## Docker Volume Issues

### Issue: Data persistence or stale data

**Symptoms:**
- Database data lost after container restart
- Old data persisting after reset
- Migrations not applied

**Solutions:**

```bash
# 1. List Docker volumes
docker volume ls | grep zenzefi

# 2. Remove specific volume
docker volume rm zenzefi_backend_postgres_data

# 3. Clean restart with volume removal
docker-compose -f docker-compose.dev.yml down -v
docker-compose -f docker-compose.dev.yml up -d

# 4. Inspect volume
docker volume inspect zenzefi_backend_postgres_data

# 5. Backup volume before removal
docker run --rm -v zenzefi_backend_postgres_data:/data -v $(pwd):/backup ubuntu tar czf /backup/postgres_backup.tar.gz /data
```

**Common causes:**
- Docker volumes not mounted correctly
- Volume path misconfigured in docker-compose.yml
- Permission issues with volume directory

---

## Performance Issues

### Issue: Slow API responses or database queries

**Symptoms:**
- High latency on API endpoints
- Slow database queries
- Redis cache misses

**Solutions:**

```bash
# 1. Check Docker resource usage
docker stats

# 2. Monitor PostgreSQL slow queries
docker exec -it zenzefi-postgres-dev psql -U zenzefi -d zenzefi_dev -c "
  SELECT query, calls, total_time, mean_time
  FROM pg_stat_statements
  ORDER BY mean_time DESC
  LIMIT 10;"

# 3. Check Redis memory usage
docker exec -it zenzefi-redis-dev redis-cli INFO memory

# 4. Enable DEBUG mode for detailed logging
# Edit .env: DEBUG=True

# 5. Profile Python code
poetry run python -m cProfile -o profile.stats run_dev.py
```

**Common causes:**
- Insufficient Docker resources allocated
- Missing database indexes
- N+1 query problems
- Redis cache not configured correctly

---

## SSL/TLS Issues (Production)

### Issue: Certificate errors or HTTPS problems

**Symptoms:**
- SSL certificate validation failures
- "certificate verify failed"
- HTTPS connection errors

**Solutions:**

```bash
# 1. Check certificate validity
openssl s_client -connect localhost:443 -servername localhost

# 2. Verify certificate files exist
ls -la /etc/nginx/ssl/

# 3. Test with curl
curl -v https://localhost:8000/health

# 4. Disable SSL verification (development only)
# In httpx client: verify=False
```

**Common causes:**
- Expired certificates
- Self-signed certificates not trusted
- Certificate path misconfigured
- Certificate permissions incorrect

---

## General Debugging Tips

### Enable Verbose Logging

```bash
# 1. Set DEBUG=True in .env
echo "DEBUG=True" >> .env

# 2. View application logs
docker-compose -f docker-compose.dev.yml logs -f app

# 3. Increase log level in logging configuration
# Edit app/core/logging.py
```

### Check Service Health

```bash
# 1. Health check endpoint
curl http://localhost:8000/health/detailed

# 2. Check all services
docker-compose -f docker-compose.dev.yml ps
```

### Verify Configuration

```bash
# 1. Print current configuration (without secrets)
poetry run python -c "from app.config import settings; print(settings.dict())"

# 2. Check environment variables loaded
poetry run python -c "from app.config import settings; print(f'DB: {settings.POSTGRES_SERVER}:{settings.POSTGRES_DB}')"
```

---

## Getting Help

If none of these solutions work:

1. Check the error logs: `docker-compose -f docker-compose.dev.yml logs`
2. Search GitHub issues: https://github.com/your-repo/issues
3. Check FastAPI documentation: https://fastapi.tiangolo.com/
4. Check SQLAlchemy documentation: https://docs.sqlalchemy.org/
5. Ask in project chat or create an issue

## Preventive Measures

1. **Always run tests before committing:**
   ```bash
   poetry run pytest tests/ -v
   ```

2. **Keep dependencies updated:**
   ```bash
   poetry update
   ```

3. **Backup database before major changes:**
   ```bash
   docker exec -it zenzefi-postgres-dev pg_dump -U zenzefi zenzefi_dev > backup.sql
   ```

4. **Use version control:**
   - Commit frequently
   - Don't commit sensitive data (.env files)
   - Use meaningful commit messages
