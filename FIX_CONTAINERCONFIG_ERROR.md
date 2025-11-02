# Исправление ошибки 'ContainerConfig'

## Проблема

При попытке запустить `docker-compose -f docker-compose.prod.tailscale.yml up -d` на сервере возникает ошибка:

```
ERROR: for postgres  'ContainerConfig'
ERROR: for redis  'ContainerConfig'
ERROR: for certbot  'ContainerConfig'
ERROR: for tailscale  'ContainerConfig'
```

**Причина:** Старая версия Docker Compose (1.29.2) не может прочитать метаданные образов контейнеров, созданных более новой версией Docker.

## Решение 1: Полная Очистка и Переразвертывание (Рекомендуется)

### Шаг 1: Загрузите скрипт очистки

```bash
cd /opt/zenzefi
git pull origin main
chmod +x scripts/cleanup_and_redeploy.sh
```

### Шаг 2: Запустите скрипт

```bash
sudo bash scripts/cleanup_and_redeploy.sh
```

Скрипт выполнит следующие действия:
1. Остановит все контейнеры
2. Удалит все контейнеры Zenzefi
3. Удалит все образы (базовые и custom)
4. Очистит build cache Docker
5. Загрузит последний код из git
6. Скачает свежие образы
7. Соберет новые образы без кэша
8. Запустит все сервисы
9. Применит миграции базы данных

**Важно:** Данные в `./data/` директориях (PostgreSQL, Redis, SSL сертификаты) НЕ будут удалены.

## Решение 2: Ручная Очистка

Если автоматический скрипт не работает, выполните вручную:

### Шаг 1: Остановите и удалите контейнеры

```bash
cd /opt/zenzefi

# Остановить все контейнеры
docker-compose -f docker-compose.prod.tailscale.yml down || true

# Удалить контейнеры вручную
docker rm -f zenzefi-nginx zenzefi-certbot zenzefi-backend \
             zenzefi-tailscale zenzefi-redis zenzefi-postgres 2>/dev/null || true
```

### Шаг 2: Удалите образы

```bash
# Удалить собранный образ backend
docker rmi -f zenzefi_backend-backend 2>/dev/null || true
docker rmi -f zenzefi-backend-backend 2>/dev/null || true

# Удалить базовые образы (будут заново скачаны)
docker rmi -f postgres:15-alpine redis:7-alpine nginx:alpine \
             tailscale/tailscale:latest certbot/certbot:latest \
             python:3.13-slim 2>/dev/null || true
```

### Шаг 3: Очистите build cache

```bash
docker system prune -f
docker builder prune -f
```

### Шаг 4: Загрузите последний код

```bash
git pull origin main
```

### Шаг 5: Определите версию Docker Compose

```bash
# Проверьте Docker Compose V2
if docker compose version > /dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
    echo "Using Docker Compose V2"
# Если нет, используйте V1
elif docker-compose version > /dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
    echo "Using Docker Compose V1"
else
    echo "ERROR: Docker Compose not found"
    exit 1
fi
```

### Шаг 6: Скачайте свежие образы

```bash
docker pull postgres:15-alpine
docker pull redis:7-alpine
docker pull nginx:alpine
docker pull tailscale/tailscale:latest
docker pull certbot/certbot:latest
docker pull python:3.13-slim
```

### Шаг 7: Соберите backend без кэша

```bash
$DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml build --no-cache backend
```

### Шаг 8: Запустите сервисы поэтапно

```bash
# Запустить инфраструктуру
$DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml up -d postgres redis tailscale
sleep 40

# Запустить backend
$DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml up -d backend
sleep 30

# Применить миграции
docker exec zenzefi-backend alembic upgrade head

# Запустить Nginx и Certbot
$DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml up -d nginx certbot
```

### Шаг 9: Проверьте статус

```bash
$DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml ps
docker logs -f zenzefi-backend
```

## Решение 3: Обновление Docker Compose до V2 (Долгосрочное решение)

Если у вас установлен старый Docker Compose (V1), рекомендуется обновить до V2:

```bash
# Удалите старый Docker Compose V1
sudo apt remove docker-compose

# Установите Docker Compose V2 (плагин для Docker)
sudo apt update
sudo apt install docker-compose-plugin

# Проверьте версию
docker compose version
# Должно быть: Docker Compose version v2.x.x
```

После обновления используйте команду `docker compose` (с пробелом) вместо `docker-compose` (с дефисом).

## Проверка Успешности Деплоя

После выполнения любого из решений проверьте:

### 1. Статус контейнеров

```bash
docker ps -a | grep zenzefi
```

Должны быть запущены (Up):
- zenzefi-postgres
- zenzefi-redis
- zenzefi-tailscale
- zenzefi-backend
- zenzefi-nginx
- zenzefi-certbot

### 2. Health checks

```bash
# PostgreSQL
docker exec zenzefi-postgres pg_isready -U zenzefi_user -d zenzefi_prod

# Redis
docker exec zenzefi-redis redis-cli ping

# Tailscale
docker exec zenzefi-tailscale tailscale status

# Backend API
docker exec zenzefi-backend curl -f http://localhost:8000/health

# Nginx
docker exec zenzefi-nginx nginx -t
```

### 3. Логи

```bash
# Все сервисы
docker-compose -f docker-compose.prod.tailscale.yml logs -f

# Конкретный сервис
docker logs -f zenzefi-backend
docker logs -f zenzefi-nginx
docker logs -f zenzefi-tailscale
```

### 4. API endpoints

```bash
# Локально
curl http://localhost:8000/health
curl http://localhost:8000/docs

# Через Nginx (если SSL настроен)
curl https://melxiorylab.ru/health
curl https://melxiorylab.ru/docs
```

## Частые Проблемы

### Проблема: "cannot connect to postgres"

**Решение:** Подождите 30-60 секунд после запуска PostgreSQL, затем перезапустите backend:

```bash
docker-compose -f docker-compose.prod.tailscale.yml restart backend
```

### Проблема: "Tailscale not connected"

**Решение:** Проверьте Tailscale auth key в `.env` файле и перезапустите контейнер:

```bash
docker-compose -f docker-compose.prod.tailscale.yml restart tailscale
docker logs -f zenzefi-tailscale
```

### Проблема: "Backend healthcheck failing"

**Решение:** Проверьте логи backend и убедитесь, что миграции применены:

```bash
docker logs zenzefi-backend
docker exec zenzefi-backend alembic current
```

### Проблема: "Nginx configuration test failed"

**Решение:** Проверьте, что конфигурационные файлы существуют:

```bash
ls -la nginx/conf.d/
docker logs zenzefi-nginx
```

## Предотвращение Проблемы в Будущем

1. **Всегда используйте `--no-cache` при сборке:**
   ```bash
   docker-compose -f docker-compose.prod.tailscale.yml build --no-cache
   ```

2. **Обновите Docker Compose до V2** (см. Решение 3)

3. **При обновлении выполняйте полную пересборку:**
   ```bash
   cd /opt/zenzefi
   git pull origin main
   docker-compose -f docker-compose.prod.tailscale.yml down
   docker-compose -f docker-compose.prod.tailscale.yml build --no-cache
   docker-compose -f docker-compose.prod.tailscale.yml up -d
   ```

4. **Используйте скрипт автоматического деплоя** (`scripts/cleanup_and_redeploy.sh`)

## Дополнительная Помощь

Если проблема не решается, соберите диагностическую информацию:

```bash
# Версии
docker version
docker-compose version
docker compose version

# Статус контейнеров
docker ps -a

# Образы
docker images | grep -E "(zenzefi|postgres|redis|nginx|tailscale|certbot)"

# Логи
docker-compose -f docker-compose.prod.tailscale.yml logs > /tmp/zenzefi-logs.txt
```

И обратитесь к документации:
- `DEPLOYMENT_DOCKER.md` - Полное руководство по Docker деплою
- `DEPLOYMENT_TAILSCALE.md` - Настройка Tailscale VPN
- `NGINX_SSL_SETUP.md` - Настройка SSL сертификатов
