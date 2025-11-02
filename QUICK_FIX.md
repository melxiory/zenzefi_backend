# Быстрое Исправление Ошибки ContainerConfig

## Проблема
```
ERROR: for postgres  'ContainerConfig'
ERROR: for redis  'ContainerConfig'
```

## Быстрое Решение (5 минут)

### На сервере выполните:

```bash
# 1. Перейдите в директорию проекта
cd /opt/zenzefi

# 2. Остановите и удалите контейнеры
docker-compose -f docker-compose.prod.tailscale.yml down || true
docker rm -f zenzefi-nginx zenzefi-certbot zenzefi-backend zenzefi-tailscale zenzefi-redis zenzefi-postgres 2>/dev/null || true

# 3. Удалите образы
docker rmi -f $(docker images -q 'zenzefi*') 2>/dev/null || true
docker rmi -f postgres:15-alpine redis:7-alpine nginx:alpine tailscale/tailscale:latest certbot/certbot:latest python:3.13-slim 2>/dev/null || true

# 4. Очистите кэш
docker system prune -f
docker builder prune -f

# 5. Обновите код
git pull origin main

# 6. Определите версию Docker Compose
if docker compose version > /dev/null 2>&1; then
    DC="docker compose"
else
    DC="docker-compose"
fi

# 7. Скачайте образы
docker pull postgres:15-alpine
docker pull redis:7-alpine
docker pull nginx:alpine
docker pull tailscale/tailscale:latest
docker pull certbot/certbot:latest
docker pull python:3.13-slim

# 8. Соберите без кэша
$DC -f docker-compose.prod.tailscale.yml build --no-cache backend

# 9. Запустите сервисы
$DC -f docker-compose.prod.tailscale.yml up -d postgres redis tailscale
sleep 40
$DC -f docker-compose.prod.tailscale.yml up -d backend
sleep 30
docker exec zenzefi-backend alembic upgrade head
$DC -f docker-compose.prod.tailscale.yml up -d nginx certbot

# 10. Проверьте статус
$DC -f docker-compose.prod.tailscale.yml ps
```

## Автоматический Скрипт (Рекомендуется)

```bash
cd /opt/zenzefi
git pull origin main
sudo bash scripts/cleanup_and_redeploy.sh
```

## Проверка

```bash
# Все контейнеры должны быть Up
docker ps | grep zenzefi

# API должен отвечать
curl http://localhost:8000/health

# Логи не должны показывать ошибок
docker logs zenzefi-backend --tail 50
```

## Если Не Помогло

Смотрите подробное руководство: `FIX_CONTAINERCONFIG_ERROR.md`
