# Обновление Production Деплоя

Этот документ описывает процедуру обновления Zenzefi Backend на production сервере с использованием Docker Compose и Tailscale VPN.

## Обзор

**Стратегия:** Обновление с коротким downtime (~1-2 минуты)

**Docker Compose файл:** `docker-compose.prod.tailscale.yml` (версия 3.8)

**Компоненты:**
- Backend (FastAPI) - custom build (Python 3.13-slim)
- PostgreSQL 15
- Redis 7
- Tailscale (VPN клиент)
- Nginx (reverse proxy)
- Certbot (SSL certificates)

### Временная диаграмма

```
Подготовка (2-3 мин) → Downtime (1-2 мин) → Проверка (2-3 мин) → Готово
    ↓                       ↓                    ↓
Git pull             Остановка             Health checks
Проверка .env        Пересборка            Логи
                     Запуск                API тесты
                     Миграции БД           Метрики
```

**Рекомендуемое время:** В часы минимальной нагрузки (ночь/раннее утро).

---

## Предварительные требования

### 1. Проверка Docker и Docker Compose

```bash
# Версия Docker (минимум 20.10+)
docker --version
# Docker version 20.10.24 или выше

# Версия Docker Compose (минимум 1.29+ для Compose v3.8)
docker compose --version
# Docker Compose version v2.x.x или выше
```

**Если Docker Compose устарел:**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker compose-plugin

# Или установите standalone версию
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker compose
sudo chmod +x /usr/local/bin/docker compose
```

### 2. Проверка доступного места

```bash
# Проверка свободного места (минимум 5GB рекомендуется)
df -h /opt/zenzefi_backend

# Проверка места для Docker
df -h /var/lib/docker

# Очистка старых Docker образов (опционально)
docker system prune -a --volumes
```

### 3. Доступ к серверу

```bash
# SSH доступ с правами sudo
ssh user@your-server.com

# Переход в директорию проекта
cd /opt/zenzefi_backend

# Проверка прав на запись
ls -la
```

---

## Проверка текущих версий

### 1. Версия приложения

```bash
# Текущая версия из Git
git describe --tags --always
# Пример вывода: v0.5.0-beta

# Текущая ветка
git branch --show-current
# Должно быть: main (или production)

# Последний коммит
git log -1 --oneline
```

### 2. Версии Docker образов

```bash
# Проверка запущенных контейнеров
docker compose -f docker-compose.prod.tailscale.yml ps

# Проверка версий образов
docker images | grep -E "zenzefi|postgres|redis|tailscale|nginx|certbot"

# Пример вывода:
# zenzefi_backend-backend    latest    abc123    2 days ago    500MB
# postgres                   15-alpine def456    1 week ago    230MB
# redis                      7-alpine  ghi789    1 week ago    40MB
# tailscale/tailscale        latest    jkl012    2 weeks ago   50MB
# nginx                      alpine    mno345    3 weeks ago   40MB
# certbot/certbot            latest    pqr678    1 month ago   150MB
```

### 3. Текущие миграции БД

```bash
# Проверка текущей ревизии базы данных
docker exec zenzefi-backend alembic current

# Проверка всех миграций
docker exec zenzefi-backend alembic history

# Проверка pending миграций (на локальной машине после git pull)
# docker exec zenzefi-backend alembic current
# Сравните с: ls alembic/versions/
```

### 4. Текущий статус сервисов

```bash
# Health checks
curl http://localhost:8000/health
# Должно вернуть: {"status": "healthy", ...}

# Проверка Tailscale VPN
docker exec zenzefi-tailscale tailscale status

# Проверка PostgreSQL
docker exec zenzefi-postgres pg_isready -U zenzefi_user -d zenzefi_prod

# Проверка Redis
docker exec zenzefi-redis redis-cli --pass "${REDIS_PASSWORD}" ping
```

---

## Процедура обновления (с downtime ~1-2 мин)

### Шаг 1: Получение новой версии (без downtime)

```bash
# Переход в директорию проекта
cd /opt/zenzefi_backend

# Сохранение локальных изменений (если есть)
git stash

# Получение обновлений
git fetch --all --tags

# Просмотр изменений (опционально)
git log HEAD..origin/main --oneline

# Обновление до последней версии
git pull origin main

# Или обновление до конкретного тега
# git checkout v0.6.0-beta

# Восстановление локальных изменений (если были)
# git stash pop
```

**Проверка changelog:**
```bash
# Просмотр последних изменений
git log -5 --pretty=format:"%h - %s (%cr)" --abbrev-commit

# Проверка изменений в docker compose файле
git diff HEAD~1 docker-compose.prod.tailscale.yml

# Проверка изменений в Dockerfile
git diff HEAD~1 Dockerfile
```

### Шаг 2: Проверка изменений в .env (без downtime)

```bash
# Проверка новых переменных окружения
# Сравните .env.example с вашим .env
diff .env.example .env

# Или посмотрите изменения в .env.example
git diff HEAD~1 .env.example
```

**Если есть новые переменные:**
```bash
# Отредактируйте .env
nano .env

# Добавьте новые обязательные переменные из .env.example
# Сохраните: Ctrl+O, Enter, Ctrl+X
```

### Шаг 3: Остановка сервисов (НАЧАЛО DOWNTIME)

```bash
# Остановка всех сервисов
docker compose -f docker-compose.prod.tailscale.yml down

# НЕ используйте -v флаг, чтобы сохранить данные!
# docker compose down -v  <-- НЕ ДЕЛАЙТЕ ТАК!

# Проверка что всё остановлено
docker compose -f docker-compose.prod.tailscale.yml ps
# Должно быть пусто
```

### Шаг 4: Обновление базовых образов (во время downtime)

```bash
# Загрузка последних версий базовых образов
docker pull postgres:15-alpine
docker pull redis:7-alpine
docker pull tailscale/tailscale:latest
docker pull nginx:alpine
docker pull certbot/certbot

# Просмотр загруженных образов
docker images | grep -E "postgres|redis|tailscale|nginx|certbot"
```

### Шаг 5: Пересборка backend образа (во время downtime)

```bash
# Пересборка backend с новым кодом
# --no-cache флаг заставляет пересобрать всё заново (медленнее, но надёжнее)
docker compose -f docker-compose.prod.tailscale.yml build --no-cache backend

# Или быстрая сборка (использует кеш слоёв)
# docker compose -f docker-compose.prod.tailscale.yml build backend

# Проверка нового образа
docker images | grep zenzefi_backend
```

### Шаг 6: Запуск сервисов (во время downtime)

```bash
# Запуск всех сервисов в фоновом режиме
docker compose -f docker-compose.prod.tailscale.yml up -d

# Проверка статуса запуска
docker compose -f docker-compose.prod.tailscale.yml ps

# Пример вывода:
# NAME                  STATUS        PORTS
# zenzefi-backend       Up (healthy)
# zenzefi-postgres      Up (healthy)
# zenzefi-redis         Up (healthy)
# zenzefi-tailscale     Up (healthy)
# zenzefi-nginx         Up            0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
# zenzefi-certbot       Up
```

**Мониторинг запуска (в реальном времени):**
```bash
# Следить за логами всех сервисов
docker compose -f docker-compose.prod.tailscale.yml logs -f

# Только backend
docker logs -f zenzefi-backend

# Прервать просмотр: Ctrl+C
```

### Шаг 7: Применение миграций БД (автоматически)

Миграции применяются **автоматически** при запуске backend контейнера (см. CMD в Dockerfile):

```dockerfile
CMD poetry run alembic upgrade head && \
    poetry run uvicorn app.main:app ...
```

**Проверка применения миграций:**
```bash
# Просмотр логов backend при старте
docker logs zenzefi-backend | grep -A 5 "alembic upgrade"

# Пример успешного вывода:
# INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
# INFO  [alembic.runtime.migration] Will assume transactional DDL.
# INFO  [alembic.runtime.migration] Running upgrade abc123 -> def456, add device_id to proxy_session

# Проверка текущей ревизии
docker exec zenzefi-backend alembic current
```

**Если миграции не применились:**
```bash
# Применить вручную
docker exec zenzefi-backend alembic upgrade head

# Проверка ошибок
docker logs zenzefi-backend | grep -i error
```

### ⏱ КОНЕЦ DOWNTIME (~1-2 минуты)

---

## Мониторинг и проверка после обновления

### 1. Health Checks всех сервисов

```bash
# Проверка health статуса контейнеров
docker compose -f docker-compose.prod.tailscale.yml ps

# Все контейнеры должны иметь статус "Up (healthy)"
# Подождите 30-60 секунд для прохождения health checks

# Проверка health endpoint backend
curl http://localhost:8000/health
# Ожидается: {"status": "healthy", "checks": {...}}

# Детальная проверка с latency
curl http://localhost:8000/health/detailed
```

### 2. Проверка логов

```bash
# Проверка логов backend (последние 50 строк)
docker logs --tail 50 zenzefi-backend

# Поиск ошибок в логах backend
docker logs zenzefi-backend | grep -i error

# Проверка логов PostgreSQL
docker logs --tail 30 zenzefi-postgres

# Проверка логов Tailscale VPN
docker logs --tail 30 zenzefi-tailscale

# Проверка логов Nginx
docker logs --tail 30 zenzefi-nginx
```

### 3. Проверка работы API endpoints

```bash
# Health check (без аутентификации)
curl https://yourdomain.com/health
# Ожидается: 200 OK, {"status": "healthy"}

# API docs (должен быть доступен)
curl -I https://yourdomain.com/docs
# Ожидается: 200 OK

# Тестовый запрос к API (с JWT токеном)
curl -X POST https://yourdomain.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass"}'
# Ожидается: 200 OK с access_token

# Proxy status endpoint (с access токеном)
curl https://yourdomain.com/api/v1/proxy/status \
  -H "X-Access-Token: your-test-token" \
  -H "X-Device-ID: test-device-12345"
# Ожидается: 200 OK с user данными
```

### 4. Проверка подключения к Zenzefi через Tailscale

```bash
# Проверка статуса Tailscale VPN
docker exec zenzefi-tailscale tailscale status
# Должно показать подключение к 100.75.169.33

# Проверка IP адреса в Tailscale сети
docker exec zenzefi-tailscale tailscale ip -4
# Пример: 100.x.x.x

# Ping Zenzefi сервера из Tailscale контейнера
docker exec zenzefi-tailscale ping -c 3 100.75.169.33

# Проверка HTTP доступа к Zenzefi из backend
docker exec zenzefi-backend curl -k -I https://100.75.169.33:61000
# Ожидается: HTTP/2 200 OK (или другой код от Zenzefi сервера)
```

### 5. Мониторинг ресурсов

```bash
# Использование CPU и RAM всеми контейнерами
docker stats --no-stream

# Пример вывода:
# CONTAINER           CPU %   MEM USAGE / LIMIT     MEM %
# zenzefi-backend     5%      300MB / 2GB          15%
# zenzefi-postgres    2%      150MB / 1GB          15%
# zenzefi-redis       1%      50MB / 256MB         19.5%
# zenzefi-tailscale   0.5%    30MB / 1GB           3%
# zenzefi-nginx       0.3%    20MB / 512MB         4%

# Использование диска (volumes)
docker system df -v | grep zenzefi

# Проверка логов на диске
du -sh /opt/zenzefi_backend/logs
du -sh /opt/zenzefi_backend/data
```

### 6. Функциональная проверка (опционально)

**Используйте Desktop Client или curl для тестирования основных сценариев:**

1. **Регистрация нового пользователя**
2. **Логин и получение JWT**
3. **Покупка access токена**
4. **Использование access токена для proxy запроса**
5. **Проверка balance и transactions**

---

## Устранение распространённых проблем

### Проблема 1: Контейнер не запускается

**Симптомы:**
```bash
docker compose ps
# zenzefi-backend   Restarting
```

**Диагностика:**
```bash
# Проверка логов
docker logs zenzefi-backend

# Проверка health check
docker inspect zenzefi-backend | grep -A 10 Health
```

**Решения:**

1. **Ошибка подключения к PostgreSQL:**
   ```bash
   # Проверьте что PostgreSQL запущен
   docker compose ps postgres

   # Проверьте переменные окружения
   docker exec zenzefi-backend env | grep POSTGRES

   # Проверьте сетевое подключение
   docker exec zenzefi-backend ping postgres
   ```

2. **Ошибка подключения к Redis:**
   ```bash
   # Проверьте Redis
   docker compose ps redis

   # Проверьте пароль Redis
   docker exec zenzefi-backend env | grep REDIS_PASSWORD

   # Тест подключения
   docker exec zenzefi-redis redis-cli --pass "${REDIS_PASSWORD}" ping
   ```

3. **Порт уже занят:**
   ```bash
   # Проверка занятых портов
   sudo netstat -tulpn | grep -E '80|443|8000'

   # Остановите конфликтующий процесс
   sudo systemctl stop apache2  # пример
   ```

### Проблема 2: Миграции БД не применились

**Симптомы:**
```bash
docker logs zenzefi-backend | grep alembic
# ERROR: Target database is not up to date
```

**Решение:**
```bash
# 1. Проверка текущей ревизии
docker exec zenzefi-backend alembic current

# 2. Проверка pending миграций
docker exec zenzefi-backend alembic history

# 3. Применить миграции вручную
docker exec zenzefi-backend alembic upgrade head

# 4. Если есть ошибка, проверьте БД
docker exec -it zenzefi-postgres psql -U zenzefi_user -d zenzefi_prod

# 5. В psql проверьте таблицу миграций
# SELECT * FROM alembic_version;
# \q для выхода

# 6. Если миграция застряла, можно откатить на одну назад
docker exec zenzefi-backend alembic downgrade -1
docker exec zenzefi-backend alembic upgrade head
```

### Проблема 3: Tailscale не подключается к VPN

**Симптомы:**
```bash
docker logs zenzefi-tailscale
# authentication failed
```

**Решение:**

1. **Проверка auth key:**
   ```bash
   # Проверьте переменную окружения
   docker exec zenzefi-tailscale env | grep TS_AUTHKEY

   # Если ключ истёк, создайте новый на:
   # https://login.tailscale.com/admin/settings/keys

   # Обновите .env
   nano .env
   # TAILSCALE_AUTH_KEY=tskey-auth-NEW-KEY

   # Пересоздайте контейнер
   docker compose -f docker-compose.prod.tailscale.yml up -d --force-recreate tailscale
   ```

2. **Проверка privileged режима:**
   ```bash
   docker inspect zenzefi-tailscale | grep Privileged
   # Должно быть: "Privileged": true
   ```

3. **Проверка /dev/net/tun:**
   ```bash
   # На хосте
   ls -la /dev/net/tun

   # Если нет, создайте
   sudo mkdir -p /dev/net
   sudo mknod /dev/net/tun c 10 200
   sudo chmod 600 /dev/net/tun
   ```

### Проблема 4: Nginx не может подключиться к Backend

**Симптомы:**
```bash
docker logs zenzefi-nginx
# connect() failed (111: Connection refused) while connecting to upstream
```

**Решение:**

Backend использует `network_mode: service:tailscale`, поэтому Nginx должен подключаться к `tailscale:8000` (а не `backend:8000`).

```bash
# Проверьте конфигурацию Nginx
cat nginx/conf.d/zenzefi.conf | grep upstream
# Должно быть: server tailscale:8000

# Проверьте доступность backend через tailscale хост
docker exec zenzefi-nginx wget -O- http://tailscale:8000/health

# Если нужно, обновите конфигурацию
nano nginx/conf.d/zenzefi.conf
# upstream backend_upstream {
#     server tailscale:8000 max_fails=3 fail_timeout=30s;
# }

# Перезапустите Nginx
docker compose -f docker-compose.prod.tailscale.yml restart nginx
```

### Проблема 5: SSL сертификат не работает

**Симптомы:**
```bash
curl https://yourdomain.com
# SSL certificate problem
```

**Решение:**
```bash
# Проверка сертификата
docker exec zenzefi-certbot certbot certificates

# Обновление сертификата вручную
docker compose -f docker-compose.prod.tailscale.yml run --rm certbot renew

# Или полная пересоздание
docker compose -f docker-compose.prod.tailscale.yml stop nginx
docker compose -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
  --standalone \
  --email your-email@example.com \
  --agree-tos \
  -d yourdomain.com

docker compose -f docker-compose.prod.tailscale.yml start nginx
```

---

## Откат к предыдущей версии (Rollback)

Если обновление привело к проблемам, можно быстро откатиться к предыдущей версии.

### Вариант 1: Откат кода (быстрый)

```bash
# Остановить сервисы
docker compose -f docker-compose.prod.tailscale.yml down

# Откатить код к предыдущему коммиту
git log --oneline -5  # найдите нужный коммит
git reset --hard abc123  # замените abc123 на хеш коммита

# Или откатить к предыдущему тегу
git checkout v0.4.0-beta

# Пересобрать образ
docker compose -f docker-compose.prod.tailscale.yml build --no-cache backend

# Запустить сервисы
docker compose -f docker-compose.prod.tailscale.yml up -d

# Проверка
curl http://localhost:8000/health
```

### Вариант 2: Использование предыдущего Docker образа

```bash
# Посмотреть доступные образы
docker images | grep zenzefi_backend-backend

# Пример:
# zenzefi_backend-backend   latest    abc123   1 hour ago
# zenzefi_backend-backend   <none>    def456   2 days ago  <-- предыдущий

# Тегировать предыдущий образ как latest
docker tag def456 zenzefi_backend-backend:latest

# Перезапустить backend
docker compose -f docker-compose.prod.tailscale.yml up -d --force-recreate backend
```

### Вариант 3: Откат миграций БД (опасно!)

**Внимание:** Откат миграций может привести к потере данных!

```bash
# Проверка текущей ревизии
docker exec zenzefi-backend alembic current

# Откат на одну миграцию назад
docker exec zenzefi-backend alembic downgrade -1

# Или откат до конкретной ревизии
docker exec zenzefi-backend alembic downgrade abc123

# Перезапуск backend
docker compose -f docker-compose.prod.tailscale.yml restart backend
```

---

## Быстрые команды (Cheat Sheet)

### Стандартное обновление (одна команда)

```bash
cd /opt/zenzefi_backend && \
git pull origin main && \
docker compose -f docker-compose.prod.tailscale.yml down && \
docker compose -f docker-compose.prod.tailscale.yml build --no-cache backend && \
docker compose -f docker-compose.prod.tailscale.yml up -d && \
docker compose -f docker-compose.prod.tailscale.yml logs -f backend
```

### Проверка статуса

```bash
# Короткий статус
docker compose -f docker-compose.prod.tailscale.yml ps && \
curl -s http://localhost:8000/health | python3 -m json.tool

# Детальная проверка
echo "=== Контейнеры ===" && \
docker compose -f docker-compose.prod.tailscale.yml ps && \
echo -e "\n=== Health Check ===" && \
curl -s http://localhost:8000/health | python3 -m json.tool && \
echo -e "\n=== Ресурсы ===" && \
docker stats --no-stream
```

### Просмотр логов

```bash
# Все сервисы (последние 50 строк)
docker compose -f docker-compose.prod.tailscale.yml logs --tail 50

# Только backend (в реальном времени)
docker logs -f zenzefi-backend

# Только ошибки backend
docker logs zenzefi-backend 2>&1 | grep -i error

# Последние 100 строк всех сервисов
docker compose -f docker-compose.prod.tailscale.yml logs --tail 100 -f
```

### Перезапуск сервисов

```bash
# Перезапуск всех сервисов (без пересборки)
docker compose -f docker-compose.prod.tailscale.yml restart

# Перезапуск только backend
docker compose -f docker-compose.prod.tailscale.yml restart backend

# Остановка → Пересборка → Запуск backend
docker compose -f docker-compose.prod.tailscale.yml stop backend && \
docker compose -f docker-compose.prod.tailscale.yml build --no-cache backend && \
docker compose -f docker-compose.prod.tailscale.yml up -d backend
```

### Очистка старых данных

```bash
# Удаление неиспользуемых образов
docker image prune -a

# Удаление неиспользуемых volumes (ОСТОРОЖНО!)
# docker volume prune  # НЕ ЗАПУСКАЙТЕ БЕЗ БЭКАПА!

# Полная очистка Docker (ОПАСНО!)
# docker system prune -a --volumes  # УДАЛИТ ВСЕ ДАННЫЕ!

# Безопасная очистка (только stopped контейнеры и build cache)
docker system prune
```

### Проверка версий

```bash
# Версия приложения
git describe --tags --always

# Версии образов
docker images | grep -E "zenzefi|postgres|redis|tailscale|nginx"

# Версия БД миграций
docker exec zenzefi-backend alembic current

# Версии зависимостей Python
docker exec zenzefi-backend poetry show --tree
```

---

## Автоматизация обновления (опционально)

Для автоматизации можно создать скрипт обновления:

**Создание скрипта:**
```bash
nano /opt/zenzefi_backend/scripts/update_deployment.sh
```

**Содержимое скрипта:**
```bash
#!/bin/bash
set -e

echo "=== Zenzefi Backend Update Script ==="
echo "Starting update at $(date)"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Переход в директорию проекта
cd /opt/zenzefi_backend

# Шаг 1: Git pull
echo -e "\n${YELLOW}[1/6] Fetching latest code...${NC}"
git fetch --all --tags
git pull origin main

# Шаг 2: Проверка .env
echo -e "\n${YELLOW}[2/6] Checking .env changes...${NC}"
if git diff HEAD~1 .env.example | grep -q "^+"; then
    echo -e "${RED}WARNING: .env.example has new variables. Please review:${NC}"
    git diff HEAD~1 .env.example
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Шаг 3: Остановка сервисов
echo -e "\n${YELLOW}[3/6] Stopping services...${NC}"
docker compose -f docker-compose.prod.tailscale.yml down

# Шаг 4: Пересборка backend
echo -e "\n${YELLOW}[4/6] Rebuilding backend image...${NC}"
docker compose -f docker-compose.prod.tailscale.yml build --no-cache backend

# Шаг 5: Запуск сервисов
echo -e "\n${YELLOW}[5/6] Starting services...${NC}"
docker compose -f docker-compose.prod.tailscale.yml up -d

# Шаг 6: Проверка health
echo -e "\n${YELLOW}[6/6] Waiting for health checks...${NC}"
sleep 10

for i in {1..30}; do
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        echo -e "\n${GREEN}✓ Update completed successfully!${NC}"
        echo -e "${GREEN}✓ Version: $(git describe --tags --always)${NC}"
        docker compose -f docker-compose.prod.tailscale.yml ps
        exit 0
    fi
    echo -n "."
    sleep 2
done

echo -e "\n${RED}✗ Health check failed. Please check logs:${NC}"
docker compose -f docker-compose.prod.tailscale.yml logs --tail 50
exit 1
```

**Сделать скрипт исполняемым:**
```bash
chmod +x /opt/zenzefi_backend/scripts/update_deployment.sh
```

**Использование:**
```bash
# Запуск обновления
sudo /opt/zenzefi_backend/scripts/update_deployment.sh

# Или через cron (каждое воскресенье в 3:00)
# sudo crontab -e
# 0 3 * * 0 /opt/zenzefi_backend/scripts/update_deployment.sh >> /var/log/zenzefi_update.log 2>&1
```

---

## Мониторинг после обновления

### Рекомендуется отслеживать в течение 24 часов:

1. **Health checks каждые 5 минут:**
   ```bash
   watch -n 300 'curl -s http://localhost:8000/health | python3 -m json.tool'
   ```

2. **Логи на наличие ошибок:**
   ```bash
   docker logs -f zenzefi-backend | grep -i error
   ```

3. **Использование ресурсов:**
   ```bash
   watch -n 60 'docker stats --no-stream'
   ```

4. **Проверка БД соединений:**
   ```bash
   docker exec -it zenzefi-postgres psql -U zenzefi_user -d zenzefi_prod -c \
     "SELECT count(*) as connections FROM pg_stat_activity;"
   ```

5. **Мониторинг Redis памяти:**
   ```bash
   docker exec zenzefi-redis redis-cli --pass "${REDIS_PASSWORD}" INFO memory
   ```

---

## Связанная документация

- [DEPLOYMENT_TAILSCALE.md](./DEPLOYMENT_TAILSCALE.md) - Первоначальное развертывание с Tailscale
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Архитектура системы
- [HEALTH_CHECKS.md](./HEALTH_CHECKS.md) - Система мониторинга здоровья
- [claude/TROUBLESHOOTING.md](./claude/TROUBLESHOOTING.md) - Устранение неполадок
- [claude/DEVELOPMENT.md](./claude/DEVELOPMENT.md) - Команды разработки

---

## Контрольный список обновления

Используйте этот чеклист для каждого обновления:

- [ ] Проверены версии Docker и Docker Compose
- [ ] Проверено свободное место на диске (минимум 5GB)
- [ ] Выполнен git pull и проверен changelog
- [ ] Проверены изменения в .env.example, обновлен .env
- [ ] Созданы бэкапы БД и конфигураций (опционально для критичных обновлений)
- [ ] Остановлены все сервисы (`docker compose down`)
- [ ] Загружены новые базовые образы (`docker pull`)
- [ ] Пересобран backend образ (`build --no-cache`)
- [ ] Запущены все сервисы (`up -d`)
- [ ] Все контейнеры имеют статус "Up (healthy)"
- [ ] Health check возвращает "healthy" (http://localhost:8000/health)
- [ ] Проверены логи на наличие ошибок
- [ ] Проверена работа API endpoints
- [ ] Проверено подключение к Zenzefi через Tailscale
- [ ] Мониторинг ресурсов в норме
- [ ] Уведомлены пользователи об обновлении (если применимо)

---

**Последнее обновление документации:** 2025-11-16
**Версия:** 1.0
**Протестировано на:** Docker 24.0+, Docker Compose v2.20+, Ubuntu 22.04 LTS
