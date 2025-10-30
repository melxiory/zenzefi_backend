# Zenzefi Backend - Production Deployment Guide

Полная инструкция по развертыванию Zenzefi Backend на production сервере.

## Требования к серверу

- **OS**: Ubuntu 22.04 LTS (или Debian 11+)
- **RAM**: Минимум 2GB (рекомендуется 4GB+)
- **CPU**: 2+ cores
- **Disk**: 20GB+ свободного места
- **Domain**: Доменное имя с настроенными DNS A-записями

## Содержание

1. [Подготовка сервера](#1-подготовка-сервера)
2. [Установка зависимостей](#2-установка-зависимостей)
3. [PostgreSQL](#3-postgresql)
4. [Redis](#4-redis)
5. [Клонирование и настройка приложения](#5-клонирование-и-настройка-приложения)
6. [Systemd Service](#6-systemd-service)
7. [Nginx + SSL/TLS](#7-nginx--ssltls)
8. [Миграции базы данных](#8-миграции-базы-данных)
9. [Запуск и проверка](#9-запуск-и-проверка)
10. [Мониторинг и логи](#10-мониторинг-и-логи)
11. [Обновление приложения](#11-обновление-приложения)

---

## 1. Подготовка сервера

### 1.1 Подключение к серверу

```bash
ssh root@your-server-ip
```

### 1.2 Обновление системы

```bash
apt update && apt upgrade -y
```

### 1.3 Создание пользователя для приложения

```bash
# Создать пользователя zenzefi
adduser zenzefi --disabled-password --gecos ""

# Добавить в группу sudo (опционально)
usermod -aG sudo zenzefi

# Переключиться на пользователя
su - zenzefi
```

### 1.4 Настройка файрвола (UFW)

```bash
# Вернуться к root
exit

# Установить UFW (если не установлен)
apt install ufw -y

# Разрешить SSH, HTTP, HTTPS
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp

# Включить файрвол
ufw enable
ufw status
```

---

## 2. Установка зависимостей

### 2.1 Python 3.13+

```bash
# Установить Python 3.13
apt install software-properties-common -y
add-apt-repository ppa:deadsnakes/ppa -y
apt update
apt install python3.13 python3.13-venv python3.13-dev -y

# Установить pip
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.13
```

### 2.2 Poetry (менеджер зависимостей)

```bash
# Установить Poetry как zenzefi пользователь
su - zenzefi
curl -sSL https://install.python-poetry.org | python3.13 -

# Добавить Poetry в PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Проверить установку
poetry --version
```

### 2.3 Git

```bash
# Вернуться к root
exit

# Установить Git
apt install git -y
```

---

## 3. PostgreSQL

### 3.1 Установка PostgreSQL 15

```bash
# Добавить репозиторий PostgreSQL
sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -

# Установить PostgreSQL
apt update
apt install postgresql-15 postgresql-contrib-15 -y

# Запустить и включить автозапуск
systemctl start postgresql
systemctl enable postgresql
```

### 3.2 Создание базы данных и пользователя

```bash
# Переключиться на пользователя postgres
sudo -u postgres psql

# В psql консоли выполнить:
```

```sql
-- Создать пользователя
CREATE USER zenzefi_user WITH PASSWORD 'your_secure_password_here';

-- Создать базу данных
CREATE DATABASE zenzefi_prod OWNER zenzefi_user;

-- Выдать все права
GRANT ALL PRIVILEGES ON DATABASE zenzefi_prod TO zenzefi_user;

-- Выйти
\q
```

### 3.3 Настройка PostgreSQL для удаленного доступа (опционально)

Если база данных на другом сервере, редактируем:

```bash
nano /etc/postgresql/15/main/postgresql.conf
```

Найти и изменить:
```
listen_addresses = 'localhost'  # или '*' для всех интерфейсов
```

Редактируем `pg_hba.conf`:
```bash
nano /etc/postgresql/15/main/pg_hba.conf
```

Добавить:
```
# Разрешить подключения с локальной сети
host    all             all             10.0.0.0/8              md5
```

Перезапустить PostgreSQL:
```bash
systemctl restart postgresql
```

---

## 4. Redis

### 4.1 Установка Redis

```bash
apt install redis-server -y

# Запустить и включить автозапуск
systemctl start redis-server
systemctl enable redis-server
```

### 4.2 Настройка Redis

```bash
nano /etc/redis/redis.conf
```

Рекомендуемые настройки:
```conf
# Bind на localhost (если Redis и Backend на одном сервере)
bind 127.0.0.1

# Установить пароль (опционально, но рекомендуется)
requirepass your_redis_password_here

# Настройки памяти
maxmemory 256mb
maxmemory-policy allkeys-lru

# Persistence (сохранение на диск)
save 900 1
save 300 10
save 60 10000
```

Перезапустить Redis:
```bash
systemctl restart redis-server
```

Проверить подключение:
```bash
redis-cli
# Если установлен пароль:
AUTH your_redis_password_here
PING  # Должен вернуть PONG
exit
```

---

## 5. Клонирование и настройка приложения

### 5.1 Клонирование репозитория

```bash
# Переключиться на пользователя zenzefi
su - zenzefi

# Создать директорию для приложений
mkdir -p ~/apps
cd ~/apps

# Клонировать репозиторий
git clone https://github.com/yourusername/zenzefi_backend.git
cd zenzefi_backend
```

### 5.2 Установка зависимостей через Poetry

```bash
# Настроить Poetry для создания виртуального окружения в папке проекта
poetry config virtualenvs.in-project true

# Установить зависимости (только production)
poetry install --no-dev --no-root
```

### 5.3 Создание .env файла

```bash
nano .env
```

Содержимое `.env`:
```bash
# Application
DEBUG=False
SECRET_KEY=generate_secure_random_key_here_min_32_chars

# Database
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=zenzefi_user
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=zenzefi_prod

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password_here
REDIS_DB=0

# JWT Token Settings
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Zenzefi Target Server (via VPN)
ZENZEFI_TARGET_URL=https://zenzefi.melxiory.ru

# Backend URL (for ContentRewriter)
# This is the URL where your backend is accessible to clients
BACKEND_URL=https://api.yourdomain.com

# Cookie Settings (Production - HTTPS required)
# IMPORTANT: Set COOKIE_SECURE=True in production (requires HTTPS)
# COOKIE_SAMESITE options: "strict", "lax", "none" (none requires HTTPS)
COOKIE_SECURE=True
COOKIE_SAMESITE=none

# Token Pricing (MVP - все бесплатно)
TOKEN_PRICE_1H=0.0
TOKEN_PRICE_12H=0.0
TOKEN_PRICE_24H=0.0
TOKEN_PRICE_7D=0.0
TOKEN_PRICE_30D=0.0
```

**Важно**: Сгенерируйте надежный `SECRET_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 5.4 Установка правильных прав доступа

```bash
chmod 600 .env
```

---

## 6. Systemd Service

Создаем systemd service для автоматического запуска приложения.

### 6.1 Создание service файла

```bash
# Вернуться к root
exit

# Создать service файл
nano /etc/systemd/system/zenzefi-backend.service
```

Содержимое файла:
```ini
[Unit]
Description=Zenzefi Backend FastAPI Application
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=notify
User=zenzefi
Group=zenzefi
WorkingDirectory=/home/zenzefi/apps/zenzefi_backend
Environment="PATH=/home/zenzefi/apps/zenzefi_backend/.venv/bin"
ExecStart=/home/zenzefi/apps/zenzefi_backend/.venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4 \
    --log-level info \
    --access-log \
    --proxy-headers \
    --forwarded-allow-ips '*'

# Restart policy
Restart=always
RestartSec=5

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=zenzefi-backend

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/home/zenzefi/apps/zenzefi_backend

[Install]
WantedBy=multi-user.target
```

### 6.2 Запуск service

```bash
# Перезагрузить systemd
systemctl daemon-reload

# Запустить сервис
systemctl start zenzefi-backend

# Включить автозапуск
systemctl enable zenzefi-backend

# Проверить статус
systemctl status zenzefi-backend
```

### 6.3 Проверка работы приложения

```bash
# Проверить, что приложение слушает на порту 8000
ss -tlnp | grep 8000

# Проверить логи
journalctl -u zenzefi-backend -f
```

---

## 7. Nginx + SSL/TLS

### 7.1 Установка Nginx

```bash
apt install nginx -y

# Запустить и включить автозапуск
systemctl start nginx
systemctl enable nginx
```

### 7.2 Создание конфигурации Nginx (HTTP - временно)

```bash
nano /etc/nginx/sites-available/zenzefi-backend
```

Содержимое (временная HTTP конфигурация для получения SSL):
```nginx
# HTTP конфигурация (временная, для Certbot)
server {
    listen 80;
    listen [::]:80;
    server_name api.yourdomain.com;

    # Let's Encrypt validation
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # Redirect all other HTTP to HTTPS (после получения сертификата)
    # location / {
    #     return 301 https://$server_name$request_uri;
    # }
}
```

Активируем конфигурацию:
```bash
ln -s /etc/nginx/sites-available/zenzefi-backend /etc/nginx/sites-enabled/

# Тестируем конфигурацию
nginx -t

# Перезагружаем Nginx
systemctl reload nginx
```

### 7.3 Установка Certbot (Let's Encrypt)

```bash
# Установить Certbot
apt install certbot python3-certbot-nginx -y

# Получить SSL сертификат
certbot --nginx -d api.yourdomain.com

# Следовать инструкциям:
# - Ввести email
# - Согласиться с условиями
# - Выбрать: Redirect HTTP to HTTPS (рекомендуется)
```

Certbot автоматически настроит Nginx для HTTPS и создаст cron job для автоматического обновления сертификатов.

### 7.4 Финальная конфигурация Nginx (HTTPS + Proxy)

После получения SSL сертификата, обновляем конфигурацию:

```bash
nano /etc/nginx/sites-available/zenzefi-backend
```

Содержимое:
```nginx
# Rate limiting
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/s;

# Upstream backend
upstream zenzefi_backend {
    server 127.0.0.1:8000 fail_timeout=0;
}

# HTTP - redirect to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name api.yourdomain.com;

    # Let's Encrypt validation
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # Redirect to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.yourdomain.com;

    # SSL Configuration (managed by Certbot)
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Logging
    access_log /var/log/nginx/zenzefi-backend-access.log;
    error_log /var/log/nginx/zenzefi-backend-error.log;

    # Client settings
    client_max_body_size 10M;
    client_body_timeout 60s;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1000;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss;

    # Proxy to FastAPI backend
    location / {
        # Rate limiting
        limit_req zone=api_limit burst=20 nodelay;

        # Proxy settings
        proxy_pass http://zenzefi_backend;
        proxy_redirect off;
        proxy_buffering off;

        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # WebSocket support (для /api/v1/proxy WebSocket endpoints)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Rate limiting для auth endpoints
    location ~ ^/api/v1/auth/(register|login) {
        limit_req zone=auth_limit burst=5 nodelay;

        proxy_pass http://zenzefi_backend;
        proxy_redirect off;
        proxy_buffering off;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint (без rate limiting)
    location /health {
        access_log off;
        proxy_pass http://zenzefi_backend;
        proxy_set_header Host $host;
    }
}
```

Тестируем и перезагружаем Nginx:
```bash
nginx -t
systemctl reload nginx
```

### 7.5 Автоматическое обновление SSL сертификатов

Certbot автоматически настраивает cron job. Проверить:
```bash
systemctl list-timers | grep certbot
```

Тестовое обновление (не обновляет реально):
```bash
certbot renew --dry-run
```

---

## 8. Миграции базы данных

### 8.1 Применение миграций

```bash
# Переключиться на пользователя zenzefi
su - zenzefi
cd ~/apps/zenzefi_backend

# Активировать виртуальное окружение
source .venv/bin/activate

# Применить миграции
poetry run alembic upgrade head

# Проверить текущую версию
poetry run alembic current
```

### 8.2 Создание первого пользователя (опционально)

Можно создать через API или напрямую в базе:

```bash
# Через API (используя curl)
curl -X POST https://api.yourdomain.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@yourdomain.com",
    "username": "admin",
    "password": "secure_password_here",
    "full_name": "Admin User"
  }'
```

---

## 9. Запуск и проверка

### 9.1 Проверка всех сервисов

```bash
# PostgreSQL
systemctl status postgresql

# Redis
systemctl status redis-server

# Backend
systemctl status zenzefi-backend

# Nginx
systemctl status nginx
```

### 9.2 Проверка логов

```bash
# Backend логи
journalctl -u zenzefi-backend -f

# Nginx логи
tail -f /var/log/nginx/zenzefi-backend-access.log
tail -f /var/log/nginx/zenzefi-backend-error.log
```

### 9.3 Тестирование API

```bash
# Health check
curl https://api.yourdomain.com/health

# API docs
curl https://api.yourdomain.com/docs

# Register user
curl -X POST https://api.yourdomain.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "testpassword123",
    "full_name": "Test User"
  }'
```

---

## 10. Мониторинг и логи

### 10.1 Мониторинг с помощью systemd

```bash
# Статус сервиса
systemctl status zenzefi-backend

# Последние 100 строк логов
journalctl -u zenzefi-backend -n 100

# Follow логи в реальном времени
journalctl -u zenzefi-backend -f

# Логи за последний час
journalctl -u zenzefi-backend --since "1 hour ago"

# Логи за определенную дату
journalctl -u zenzefi-backend --since "2024-01-27 10:00:00"
```

### 10.2 Мониторинг ресурсов

```bash
# CPU и память процесса
ps aux | grep uvicorn

# Статистика сервиса
systemctl show zenzefi-backend --property=CPUUsageNSec,MemoryCurrent

# Общая нагрузка сервера
htop  # или top
```

### 10.3 Мониторинг PostgreSQL

```bash
# Подключиться к базе
sudo -u postgres psql zenzefi_prod

# Проверить количество записей
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM access_tokens;

# Размер базы данных
SELECT pg_size_pretty(pg_database_size('zenzefi_prod'));
```

### 10.4 Мониторинг Redis

```bash
redis-cli
AUTH your_redis_password_here

# Информация о Redis
INFO

# Количество ключей
DBSIZE

# Использование памяти
INFO memory

# Выйти
exit
```

### 10.5 Настройка logrotate для Nginx

```bash
nano /etc/logrotate.d/nginx
```

Содержимое:
```
/var/log/nginx/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        if [ -f /var/run/nginx.pid ]; then
            kill -USR1 `cat /var/run/nginx.pid`
        fi
    endscript
}
```

---

## 11. Обновление приложения

### 11.1 Процедура обновления

```bash
# Переключиться на пользователя zenzefi
su - zenzefi
cd ~/apps/zenzefi_backend

# Сохранить текущую версию (backup)
git branch backup-$(date +%Y%m%d-%H%M%S)

# Получить обновления
git fetch origin
git pull origin main

# Обновить зависимости (если изменились)
poetry install --no-dev --no-root

# Применить новые миграции (если есть)
poetry run alembic upgrade head

# Вернуться к root
exit

# Перезапустить сервис
systemctl restart zenzefi-backend

# Проверить статус
systemctl status zenzefi-backend

# Проверить логи на ошибки
journalctl -u zenzefi-backend -f
```

### 11.2 Откат при проблемах

```bash
su - zenzefi
cd ~/apps/zenzefi_backend

# Посмотреть список веток
git branch

# Откатиться на backup версию
git checkout backup-20240127-120000

# Откатить миграции (если нужно)
poetry run alembic downgrade -1

exit

# Перезапустить сервис
systemctl restart zenzefi-backend
```

---

## 12. Резервное копирование

### 12.1 Backup базы данных

Создать скрипт для backup:
```bash
nano /home/zenzefi/backup_db.sh
```

Содержимое:
```bash
#!/bin/bash

# Настройки
BACKUP_DIR="/home/zenzefi/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="zenzefi_prod"
DB_USER="zenzefi_user"
DB_PASSWORD="your_secure_password_here"

# Создать директорию для backup
mkdir -p $BACKUP_DIR

# Backup базы данных
PGPASSWORD=$DB_PASSWORD pg_dump -U $DB_USER -h localhost $DB_NAME | gzip > $BACKUP_DIR/zenzefi_prod_$DATE.sql.gz

# Удалить старые backup (старше 7 дней)
find $BACKUP_DIR -name "zenzefi_prod_*.sql.gz" -mtime +7 -delete

echo "Backup completed: zenzefi_prod_$DATE.sql.gz"
```

Сделать скрипт исполняемым:
```bash
chmod +x /home/zenzefi/backup_db.sh
```

Настроить cron для автоматического backup:
```bash
crontab -e
```

Добавить:
```
# Backup базы данных каждый день в 3:00
0 3 * * * /home/zenzefi/backup_db.sh >> /home/zenzefi/backup.log 2>&1
```

### 12.2 Восстановление из backup

```bash
# Распаковать и восстановить
gunzip < /home/zenzefi/backups/zenzefi_prod_20240127_030000.sql.gz | sudo -u postgres psql zenzefi_prod
```

---

## 13. Troubleshooting

### 13.1 Backend не запускается

```bash
# Проверить логи
journalctl -u zenzefi-backend -n 50

# Проверить .env файл
cat /home/zenzefi/apps/zenzefi_backend/.env

# Проверить подключение к PostgreSQL
sudo -u zenzefi psql -h localhost -U zenzefi_user -d zenzefi_prod

# Проверить подключение к Redis
redis-cli ping
```

### 13.2 502 Bad Gateway от Nginx

```bash
# Проверить, запущен ли backend
systemctl status zenzefi-backend

# Проверить, слушает ли backend на порту 8000
ss -tlnp | grep 8000

# Проверить SELinux (если включен)
getenforce
# Если Enforcing, временно отключить:
setenforce 0
```

### 13.3 Ошибки SSL сертификата

```bash
# Проверить срок действия сертификата
certbot certificates

# Принудительное обновление
certbot renew --force-renewal

# Проверить конфигурацию Nginx
nginx -t
```

### 13.4 Высокая нагрузка

```bash
# Увеличить количество workers в systemd service
nano /etc/systemd/system/zenzefi-backend.service

# Изменить --workers 4 на --workers 8 (или больше)

# Перезагрузить конфигурацию
systemctl daemon-reload
systemctl restart zenzefi-backend
```

---

## 14. Checklist перед запуском

- [ ] DNS A-запись настроена и указывает на IP сервера
- [ ] Файрвол настроен (порты 22, 80, 443)
- [ ] PostgreSQL установлен и база данных создана
- [ ] Redis установлен и запущен
- [ ] `.env` файл создан с корректными настройками
- [ ] `SECRET_KEY` сгенерирован (минимум 32 символа)
- [ ] Миграции применены (`alembic upgrade head`)
- [ ] Systemd service создан и запущен
- [ ] Nginx установлен и настроен
- [ ] SSL сертификат получен через Certbot
- [ ] Backend доступен через HTTPS
- [ ] API endpoints отвечают корректно
- [ ] Логи не содержат критических ошибок
- [ ] Backup скрипт настроен и протестирован

---

## 15. Полезные команды

```bash
# Перезапуск всех сервисов
systemctl restart postgresql redis-server zenzefi-backend nginx

# Просмотр всех портов
ss -tlnp

# Проверка дискового пространства
df -h

# Проверка использования памяти
free -h

# Проверка логов systemd
journalctl -xe

# Очистка старых логов journald
journalctl --vacuum-time=7d

# Тест производительности API
ab -n 1000 -c 10 https://api.yourdomain.com/health
```

---

## 16. Контакты и поддержка

При возникновении проблем проверьте:
- Логи backend: `journalctl -u zenzefi-backend -f`
- Логи Nginx: `/var/log/nginx/zenzefi-backend-error.log`
- Подключение к БД: `psql -h localhost -U zenzefi_user -d zenzefi_prod`
- API документация: `https://api.yourdomain.com/docs`

---

**Готово!** Ваш Zenzefi Backend развернут и готов к работе в production.