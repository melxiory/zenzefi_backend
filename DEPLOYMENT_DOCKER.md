# Zenzefi Backend - Docker Production Deployment

Упрощенное развертывание с использованием Docker для всех компонентов.

## Преимущества Docker-подхода

✅ **Простота**: Один docker-compose.yml файл вместо ручной установки PostgreSQL/Redis
✅ **Портативность**: Легко переносить между серверами
✅ **Изоляция**: Все сервисы изолированы
✅ **Версионирование**: Легко откатиться к предыдущей версии
✅ **Быстрое развертывание**: ~5 минут вместо 30+

---

## Требования к серверу

- **OS**: Ubuntu 22.04 LTS (или любой Linux с Docker)
- **RAM**: Минимум 2GB (рекомендуется 4GB+)
- **CPU**: 2+ cores
- **Disk**: 20GB+ свободного места
- **Domain**: Доменное имя с настроенными DNS A-записями

---

## Содержание

1. [Быстрая установка (Auto)](#1-быстрая-установка-auto)
2. [Ручная установка](#2-ручная-установка)
3. [Управление контейнерами](#3-управление-контейнерами)
4. [Backup и восстановление](#4-backup-и-восстановление)
5. [Мониторинг](#5-мониторинг)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Быстрая установка (Auto)

### Скачать и запустить скрипт

```bash
# Скачать автоматический скрипт
wget https://raw.githubusercontent.com/yourusername/zenzefi_backend/main/scripts/deploy_docker.sh

# Сделать исполняемым
chmod +x deploy_docker.sh

# Запустить (требуется root или sudo)
sudo ./deploy_docker.sh
```

Скрипт автоматически:
- Установит Docker и Docker Compose
- Создаст необходимые директории и конфигурации
- Настроит PostgreSQL, Redis, Backend и Nginx в контейнерах
- Получит SSL сертификат через Certbot
- Запустит все сервисы
- Настроит автоматические backup

---

## 2. Ручная установка

### 2.1 Подготовка сервера

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить необходимые пакеты
sudo apt install -y curl git ufw
```

### 2.2 Установка Docker

```bash
# Удалить старые версии Docker (если есть)
sudo apt remove docker docker-engine docker.io containerd runc

# Установить зависимости
sudo apt install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Добавить GPG ключ Docker
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Добавить репозиторий Docker
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установить Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Проверить установку
docker --version
docker compose version
```

### 2.3 Настройка пользователя

```bash
# Добавить текущего пользователя в группу docker (опционально)
sudo usermod -aG docker $USER

# Применить изменения (или перелогиниться)
newgrp docker
```

### 2.4 Настройка файрвола

```bash
# Разрешить SSH, HTTP, HTTPS
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Включить файрвол
sudo ufw enable
sudo ufw status
```

### 2.5 Клонирование проекта

```bash
# Создать директорию для проекта
sudo mkdir -p /opt/zenzefi
cd /opt/zenzefi

# Клонировать репозиторий
sudo git clone https://github.com/yourusername/zenzefi_backend.git .

# Создать директории для данных
sudo mkdir -p data/postgres data/redis backups logs
```

### 2.6 Создание конфигурации

#### docker-compose.prod.yml

```bash
sudo nano docker-compose.prod.yml
```

Содержимое:

```yaml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: zenzefi-postgres
    restart: always
    environment:
      POSTGRES_DB: zenzefi_prod
      POSTGRES_USER: zenzefi_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    networks:
      - zenzefi-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U zenzefi_user -d zenzefi_prod"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis Cache
  redis:
    image: redis:7-alpine
    container_name: zenzefi-redis
    restart: always
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - ./data/redis:/data
    networks:
      - zenzefi-network
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Backend API
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: zenzefi-backend
    restart: always
    env_file:
      - .env.prod
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - zenzefi-network
    volumes:
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # Nginx Reverse Proxy
  nginx:
    image: nginx:alpine
    container_name: zenzefi-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./data/certbot/conf:/etc/letsencrypt:ro
      - ./data/certbot/www:/var/www/certbot:ro
    depends_on:
      - backend
    networks:
      - zenzefi-network
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Certbot for SSL
  certbot:
    image: certbot/certbot
    container_name: zenzefi-certbot
    volumes:
      - ./data/certbot/conf:/etc/letsencrypt
      - ./data/certbot/www:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"

networks:
  zenzefi-network:
    driver: bridge

volumes:
  postgres-data:
  redis-data:
```

#### Dockerfile

```bash
sudo nano Dockerfile
```

Содержимое:

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.7.1

# Copy project files
COPY pyproject.toml poetry.lock ./

# Configure Poetry and install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-root --no-interaction --no-ansi

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create logs directory
RUN mkdir -p /app/logs

# Run migrations and start application
CMD poetry run alembic upgrade head && \
    poetry run uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info \
    --access-log \
    --proxy-headers
```

#### .env.prod

```bash
sudo nano .env.prod
```

Содержимое:

```bash
# Application
DEBUG=False
SECRET_KEY=your_generated_secret_key_here
BACKEND_URL=https://api.yourdomain.com

# Database (container names as hostnames)
POSTGRES_SERVER=postgres
POSTGRES_PORT=5432
POSTGRES_USER=zenzefi_user
POSTGRES_PASSWORD=your_postgres_password_here
POSTGRES_DB=zenzefi_prod

# Redis (container name as hostname)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password_here
REDIS_DB=0

# JWT
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Zenzefi Target Server
ZENZEFI_TARGET_URL=https://zenzefi.melxiory.ru
ZENZEFI_BASIC_AUTH_USER=
ZENZEFI_BASIC_AUTH_PASSWORD=

# Token Pricing (MVP)
TOKEN_PRICE_1H=0.0
TOKEN_PRICE_12H=0.0
TOKEN_PRICE_24H=0.0
TOKEN_PRICE_WEEK=0.0
TOKEN_PRICE_MONTH=0.0

# Cookie Settings
COOKIE_SECURE=True
COOKIE_SAMESITE=none
```

**Сгенерировать SECRET_KEY:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### Nginx Configuration

```bash
sudo mkdir -p nginx/conf.d
sudo nano nginx/conf.d/zenzefi.conf
```

Содержимое (временная HTTP конфигурация для получения SSL):

```nginx
upstream backend {
    server backend:8000;
}

server {
    listen 80;
    server_name api.yourdomain.com;

    # Let's Encrypt validation
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Temporary: proxy to backend (will redirect to HTTPS after SSL)
    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 2.7 Получение SSL сертификата

```bash
# Запустить Nginx для валидации Let's Encrypt
sudo docker compose -f docker-compose.prod.yml up -d nginx

# Получить SSL сертификат
sudo docker compose -f docker-compose.prod.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@example.com \
    --agree-tos \
    --no-eff-email \
    -d api.yourdomain.com

# Остановить Nginx
sudo docker compose -f docker-compose.prod.yml down
```

### 2.8 Обновление Nginx конфигурации для HTTPS

```bash
sudo nano nginx/conf.d/zenzefi.conf
```

Замените содержимое:

```nginx
# Rate limiting
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/s;

upstream backend {
    server backend:8000;
}

# HTTP - redirect to HTTPS
server {
    listen 80;
    server_name api.yourdomain.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    # SSL Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers off;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    # Client settings
    client_max_body_size 10M;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    # Proxy to backend
    location / {
        limit_req zone=api_limit burst=20 nodelay;

        proxy_pass http://backend;
        proxy_redirect off;
        proxy_buffering off;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Auth endpoints with stricter rate limiting
    location ~ ^/api/v1/auth/(register|login) {
        limit_req zone=auth_limit burst=5 nodelay;

        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check
    location /health {
        access_log off;
        proxy_pass http://backend;
    }
}
```

### 2.9 Запуск всех сервисов

```bash
cd /opt/zenzefi

# Собрать образы
sudo docker compose -f docker-compose.prod.yml build

# Запустить все сервисы
sudo docker compose -f docker-compose.prod.yml up -d

# Проверить статус
sudo docker compose -f docker-compose.prod.yml ps

# Проверить логи
sudo docker compose -f docker-compose.prod.yml logs -f
```

---

## 3. Управление контейнерами

### Основные команды

```bash
cd /opt/zenzefi

# Запустить все сервисы
sudo docker compose -f docker-compose.prod.yml up -d

# Остановить все сервисы
sudo docker compose -f docker-compose.prod.yml down

# Перезапустить все сервисы
sudo docker compose -f docker-compose.prod.yml restart

# Перезапустить конкретный сервис
sudo docker compose -f docker-compose.prod.yml restart backend

# Просмотр логов всех сервисов
sudo docker compose -f docker-compose.prod.yml logs -f

# Просмотр логов конкретного сервиса
sudo docker compose -f docker-compose.prod.yml logs -f backend

# Статус всех контейнеров
sudo docker compose -f docker-compose.prod.yml ps

# Удалить все контейнеры (данные сохранятся в volumes)
sudo docker compose -f docker-compose.prod.yml down

# Удалить контейнеры И volumes (ОСТОРОЖНО!)
sudo docker compose -f docker-compose.prod.yml down -v
```

### Выполнение команд внутри контейнеров

```bash
# Зайти в контейнер backend
sudo docker exec -it zenzefi-backend sh

# Выполнить команду в контейнере backend
sudo docker exec -it zenzefi-backend poetry run alembic current

# Зайти в PostgreSQL
sudo docker exec -it zenzefi-postgres psql -U zenzefi_user -d zenzefi_prod

# Выполнить команду в Redis
sudo docker exec -it zenzefi-redis redis-cli -a your_redis_password
```

### Миграции базы данных

```bash
# Применить миграции
sudo docker exec -it zenzefi-backend poetry run alembic upgrade head

# Создать новую миграцию
sudo docker exec -it zenzefi-backend poetry run alembic revision --autogenerate -m "Description"

# Откатить миграцию
sudo docker exec -it zenzefi-backend poetry run alembic downgrade -1
```

### Обновление приложения

```bash
cd /opt/zenzefi

# Получить обновления из Git
sudo git pull origin main

# Пересобрать образ backend
sudo docker compose -f docker-compose.prod.yml build backend

# Перезапустить backend
sudo docker compose -f docker-compose.prod.yml up -d backend

# Проверить логи
sudo docker compose -f docker-compose.prod.yml logs -f backend
```

---

## 4. Backup и восстановление

### 4.1 Автоматический backup PostgreSQL

Создать скрипт:

```bash
sudo nano /opt/zenzefi/backup.sh
```

Содержимое:

```bash
#!/bin/bash

BACKUP_DIR="/opt/zenzefi/backups"
DATE=$(date +%Y%m%d_%H%M%S)
POSTGRES_PASSWORD="your_postgres_password_here"

mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker exec -e PGPASSWORD=$POSTGRES_PASSWORD zenzefi-postgres \
    pg_dump -U zenzefi_user zenzefi_prod | \
    gzip > $BACKUP_DIR/postgres_$DATE.sql.gz

# Удалить старые backup (старше 7 дней)
find $BACKUP_DIR -name "postgres_*.sql.gz" -mtime +7 -delete

echo "Backup completed: postgres_$DATE.sql.gz"
```

Сделать исполняемым:

```bash
sudo chmod +x /opt/zenzefi/backup.sh
```

Настроить cron:

```bash
sudo crontab -e
```

Добавить:

```
# Backup каждый день в 3:00
0 3 * * * /opt/zenzefi/backup.sh >> /opt/zenzefi/backup.log 2>&1
```

### 4.2 Ручной backup

```bash
# PostgreSQL
sudo docker exec -e PGPASSWORD=your_password zenzefi-postgres \
    pg_dump -U zenzefi_user zenzefi_prod | \
    gzip > /opt/zenzefi/backups/manual_backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Redis (snapshot)
sudo docker exec zenzefi-redis redis-cli -a your_redis_password SAVE
sudo cp /opt/zenzefi/data/redis/dump.rdb /opt/zenzefi/backups/redis_$(date +%Y%m%d_%H%M%S).rdb
```

### 4.3 Восстановление из backup

```bash
# PostgreSQL
gunzip < /opt/zenzefi/backups/postgres_20240127_030000.sql.gz | \
    sudo docker exec -i -e PGPASSWORD=your_password zenzefi-postgres \
    psql -U zenzefi_user zenzefi_prod

# Redis
sudo docker compose -f docker-compose.prod.yml stop redis
sudo cp /opt/zenzefi/backups/redis_20240127_030000.rdb /opt/zenzefi/data/redis/dump.rdb
sudo docker compose -f docker-compose.prod.yml start redis
```

---

## 5. Мониторинг

### Проверка состояния сервисов

```bash
# Статус контейнеров
sudo docker compose -f docker-compose.prod.yml ps

# Использование ресурсов
sudo docker stats

# Логи backend
sudo docker compose -f docker-compose.prod.yml logs -f backend

# Логи PostgreSQL
sudo docker compose -f docker-compose.prod.yml logs -f postgres

# Логи Nginx
sudo docker compose -f docker-compose.prod.yml logs -f nginx
```

### Health checks

```bash
# API health
curl https://api.yourdomain.com/health

# PostgreSQL
sudo docker exec zenzefi-postgres pg_isready -U zenzefi_user

# Redis
sudo docker exec zenzefi-redis redis-cli -a your_redis_password PING
```

---

## 6. Troubleshooting

### Backend не запускается

```bash
# Проверить логи
sudo docker compose -f docker-compose.prod.yml logs backend

# Проверить health check
sudo docker inspect zenzefi-backend | grep -A 10 Health

# Перезапустить
sudo docker compose -f docker-compose.prod.yml restart backend
```

### PostgreSQL проблемы

```bash
# Проверить логи
sudo docker compose -f docker-compose.prod.yml logs postgres

# Проверить подключение
sudo docker exec zenzefi-postgres psql -U zenzefi_user -d zenzefi_prod -c "SELECT 1;"

# Проверить volume
sudo ls -la /opt/zenzefi/data/postgres/
```

### 502 Bad Gateway

```bash
# Проверить, что backend запущен
sudo docker ps | grep backend

# Проверить логи Nginx
sudo docker compose -f docker-compose.prod.yml logs nginx

# Проверить сеть
sudo docker network inspect zenzefi_zenzefi-network
```

### Очистка Docker

```bash
# Удалить неиспользуемые образы
sudo docker image prune -a

# Удалить неиспользуемые volumes
sudo docker volume prune

# Удалить все stopped контейнеры
sudo docker container prune

# Полная очистка (ОСТОРОЖНО!)
sudo docker system prune -a --volumes
```

---

## Преимущества vs Native Installation

| Критерий | Docker | Native |
|----------|--------|--------|
| **Установка** | 5-10 минут | 30+ минут |
| **Сложность** | Низкая | Средняя |
| **Изоляция** | Отличная | Средняя |
| **Производительность** | 95-98% | 100% |
| **Портативность** | Отличная | Низкая |
| **Обновления** | Очень простые | Средней сложности |
| **Backup** | Просто (volumes) | Средней сложности |
| **Масштабирование** | Легко | Сложнее |

---

## Полезные команды

```bash
# Просмотр всех контейнеров
sudo docker ps -a

# Просмотр всех images
sudo docker images

# Просмотр всех volumes
sudo docker volume ls

# Просмотр всех networks
sudo docker network ls

# Использование дискового пространства
sudo docker system df

# Детальная информация о контейнере
sudo docker inspect zenzefi-backend

# Просмотр логов с фильтром
sudo docker compose -f docker-compose.prod.yml logs backend | grep ERROR
```

---

## Рекомендации для production

1. **Используйте Docker Secrets** для паролей вместо .env файлов
2. **Настройте log rotation** для Docker логов
3. **Мониторинг**: Установите Prometheus + Grafana
4. **Резервирование**: Настройте репликацию PostgreSQL
5. **Обновления**: Используйте automated updates для образов
6. **Security**: Регулярно обновляйте образы Docker

---

**Готово!** Ваш Zenzefi Backend развернут в Docker контейнерах и готов к работе! 🐳