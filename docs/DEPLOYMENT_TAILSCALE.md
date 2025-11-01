# Деплой с Tailscale VPN

Этот документ описывает развёртывание Zenzefi Backend с использованием Tailscale VPN для доступа к Zenzefi серверу.

## Общая архитектура

```
[Internet] → [Nginx + SSL] → [FastAPI Backend] → [Tailscale VPN] → [Zenzefi Server (100.75.169.33:61000)]
                                                         ↓
                                                  [PostgreSQL + Redis]
```

## Предварительные требования

### 1. Установка Tailscale на хосте (опционально)

Если вы хотите использовать Tailscale установленный на хосте:

```bash
# Ubuntu/Debian
curl -fsSL https://tailscale.com/install.sh | sh

# Авторизация
sudo tailscale up

# Проверка подключения
tailscale status
ping 100.75.169.33
```

### 2. Получение Tailscale Auth Key (для Docker)

Если используете `docker-compose.prod.tailscale.yml`:

1. Откройте https://login.tailscale.com/admin/settings/keys
2. Создайте новый auth key:
   - **Reusable**: Yes (для пересоздания контейнеров)
   - **Ephemeral**: Yes (автоматическое удаление при остановке)
   - **Tags**: `tag:zenzefi` (опционально)
3. Скопируйте сгенерированный ключ

## Варианты развёртывания

### Вариант 1: Tailscale в Docker контейнере (рекомендуется)

**Преимущества:**
- Полная изоляция VPN внутри Docker
- Легко управлять и перезапускать
- Не требует установки Tailscale на хост

**Недостатки:**
- Требует privileged режим для контейнера
- Немного больше накладных расходов

#### Шаг 1: Подготовка окружения

```bash
cd /opt/zenzefi_backend

# Создать .env файл
cp .env.example .env
nano .env
```

Обязательные переменные в `.env`:

```bash
# Application
DEBUG=False
SECRET_KEY=your-very-long-secret-key-min-32-chars-change-this

# Database
POSTGRES_PASSWORD=strong-postgres-password
POSTGRES_SERVER=postgres
POSTGRES_USER=zenzefi_user
POSTGRES_DB=zenzefi_prod

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=strong-redis-password

# Tailscale
TAILSCALE_AUTH_KEY=tskey-auth-xxxxxxxxxxxxx-yyyyyyyyyyyyyyyyyyy

# Zenzefi Target Server (через Tailscale VPN)
ZENZEFI_TARGET_URL=https://100.75.169.33:61000

# Backend URL (замените на ваш домен)
BACKEND_URL=https://api.zenzefi.yourdomain.com

# Cookie Settings (HTTPS обязательно для production)
COOKIE_SECURE=True
COOKIE_SAMESITE=none
```

#### Шаг 2: Создание директорий для данных

```bash
mkdir -p data/postgres data/redis data/tailscale data/certbot/conf data/certbot/www
mkdir -p logs nginx/conf.d
chmod 755 data/tailscale
```

#### Шаг 3: Запуск сервисов

```bash
# Запуск всех сервисов (включая Tailscale)
docker-compose -f docker-compose.prod.tailscale.yml up -d

# Проверка статуса
docker-compose -f docker-compose.prod.tailscale.yml ps

# Проверка логов Tailscale
docker logs zenzefi-tailscale

# Проверка VPN подключения из backend контейнера
docker exec zenzefi-backend curl -k https://100.75.169.33:61000 -I
```

#### Шаг 4: Применение миграций

```bash
# Применить миграции БД
docker exec zenzefi-backend alembic upgrade head

# Создать суперпользователя (опционально)
docker exec -it zenzefi-backend python scripts/create_superuser.py
```

#### Шаг 5: Настройка Nginx и SSL

**Важно:** При использовании Tailscale в Docker, Nginx должен подключаться к `tailscale:8000` вместо `backend:8000`.

Полная инструкция по настройке Nginx с SSL: [NGINX_SSL_SETUP.md](../NGINX_SSL_SETUP.md)

**Быстрый старт:**

1. **Первоначальный запуск без SSL:**
   ```bash
   cd nginx/conf.d
   mv zenzefi.conf zenzefi.conf.disabled
   mv zenzefi-init.conf.disabled zenzefi-init.conf
   docker-compose -f docker-compose.prod.tailscale.yml up -d
   ```

2. **Получить SSL сертификат:**
   ```bash
   docker-compose -f docker-compose.prod.tailscale.yml stop nginx
   docker-compose -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
     --standalone --email your-email@example.com --agree-tos \
     -d zenzefi.melxiory.ru
   ```

3. **Переключиться на HTTPS:**
   ```bash
   cd nginx/conf.d
   mv zenzefi-init.conf zenzefi-init.conf.disabled
   mv zenzefi.conf.disabled zenzefi.conf
   docker-compose -f docker-compose.prod.tailscale.yml restart nginx
   ```

4. **Проверить:**
   ```bash
   curl https://zenzefi.melxiory.ru/health
   ```

---

### Вариант 2: Tailscale на хосте

**Преимущества:**
- Проще в настройке
- Меньше накладных расходов
- Один VPN для всех сервисов на хосте

**Недостатки:**
- Tailscale должен быть установлен на хосте
- Меньше изоляции

#### Шаг 1: Установка Tailscale на хост

```bash
# Ubuntu/Debian
curl -fsSL https://tailscale.com/install.sh | sh

# Авторизация
sudo tailscale up

# Проверка
tailscale status
ping 100.75.169.33
```

#### Шаг 2: Настройка .env

```bash
cd /opt/zenzefi_backend
cp .env.example .env
nano .env
```

Установите:
```bash
ZENZEFI_TARGET_URL=https://100.75.169.33:61000
```

#### Шаг 3: Запуск через docker-compose.prod.yml

```bash
# Запуск (БЕЗ Tailscale контейнера)
docker-compose -f docker-compose.prod.yml up -d

# Backend автоматически получит доступ к хост-сети через bridge
# Проверка доступности Zenzefi сервера
docker exec zenzefi-backend curl -k https://100.75.169.33:61000 -I
```

**Примечание:** Docker bridge network по умолчанию имеет доступ к хост-сети, включая Tailscale интерфейс.

#### Если нужен прямой доступ к хост-сети

Если bridge не работает, можно использовать `network_mode: host` для backend:

```yaml
# docker-compose.prod.yml
services:
  backend:
    network_mode: "host"
    # Остальные настройки...
```

**Внимание:** В режиме `host` контейнер теряет изоляцию сети и открывает порты напрямую на хосте.

---

## Проверка работы VPN

### Из backend контейнера

```bash
# Проверка DNS (если используется Tailscale DNS)
docker exec zenzefi-backend nslookup zenzefi-win11-server

# Проверка HTTP доступа
docker exec zenzefi-backend curl -k https://100.75.169.33:61000 -I

# Проверка из Python
docker exec zenzefi-backend python -c "
import httpx
response = httpx.get('https://100.75.169.33:61000', verify=False)
print(f'Status: {response.status_code}')
"
```

### Из Tailscale контейнера

```bash
# Проверка статуса Tailscale
docker exec zenzefi-tailscale tailscale status

# Проверка IP адресов
docker exec zenzefi-tailscale tailscale ip -4

# Ping Zenzefi сервера
docker exec zenzefi-tailscale ping -c 3 100.75.169.33
```

---

## Мониторинг и логи

```bash
# Логи всех сервисов
docker-compose -f docker-compose.prod.tailscale.yml logs -f

# Только Tailscale
docker logs -f zenzefi-tailscale

# Только Backend
docker logs -f zenzefi-backend

# Проверка health checks
docker inspect zenzefi-tailscale | grep -A 10 Health
docker inspect zenzefi-backend | grep -A 10 Health
```

---

## Устранение неполадок

### Backend не может подключиться к Zenzefi серверу

1. **Проверьте Tailscale статус:**
   ```bash
   docker exec zenzefi-tailscale tailscale status
   ```

2. **Проверьте network namespace:**
   ```bash
   # Backend должен использовать network от Tailscale
   docker inspect zenzefi-backend | grep NetworkMode
   # Должно быть: "NetworkMode": "container:zenzefi-tailscale"
   ```

3. **Проверьте переменную окружения:**
   ```bash
   docker exec zenzefi-backend env | grep ZENZEFI_TARGET_URL
   # Должно быть: ZENZEFI_TARGET_URL=https://100.75.169.33:61000
   ```

4. **Проверьте сетевой доступ:**
   ```bash
   docker exec zenzefi-backend ping 100.75.169.33
   ```

### Tailscale контейнер не запускается

1. **Проверьте auth key:**
   ```bash
   docker logs zenzefi-tailscale | grep -i auth
   ```

2. **Проверьте privileged режим:**
   ```bash
   docker inspect zenzefi-tailscale | grep Privileged
   # Должно быть: "Privileged": true
   ```

3. **Проверьте /dev/net/tun:**
   ```bash
   docker inspect zenzefi-tailscale | grep /dev/net/tun
   ```

### Nginx не может достучаться до Backend

**Проблема:** Если используете `network_mode: service:tailscale`, Nginx НЕ сможет подключиться к Backend через обычный Docker network (`backend:8000`).

**Причина:** Backend использует сетевой namespace Tailscale контейнера (`network_mode: service:tailscale`), поэтому он не имеет собственного хоста в Docker сети.

**Решение:** Nginx должен подключаться к `tailscale:8000` вместо `backend:8000`.

Конфигурация Nginx upstream должна быть:
```nginx
upstream backend_upstream {
    # Backend использует network_mode: service:tailscale
    # поэтому доступен через tailscale хост
    server tailscale:8000 max_fails=3 fail_timeout=30s;
}
```

**Проверка:**
```bash
# Nginx должен видеть tailscale хост
docker exec zenzefi-nginx nslookup tailscale

# Backend доступен на порту 8000 через tailscale
docker exec zenzefi-nginx wget -O- http://tailscale:8000/health
```

Подробнее см. [NGINX_SSL_SETUP.md](../NGINX_SSL_SETUP.md)

---

## Обновление и обслуживание

### Перезапуск сервисов

```bash
# Перезапуск всех сервисов
docker-compose -f docker-compose.prod.tailscale.yml restart

# Перезапуск только Tailscale
docker-compose -f docker-compose.prod.tailscale.yml restart tailscale

# Перезапуск только Backend
docker-compose -f docker-compose.prod.tailscale.yml restart backend
```

### Обновление Tailscale

```bash
# Остановить контейнер
docker-compose -f docker-compose.prod.tailscale.yml stop tailscale

# Удалить контейнер (данные сохранятся в volume)
docker-compose -f docker-compose.prod.tailscale.yml rm -f tailscale

# Загрузить новый образ
docker pull tailscale/tailscale:latest

# Запустить снова
docker-compose -f docker-compose.prod.tailscale.yml up -d tailscale
```

### Ротация Auth Key

Если auth key истёк:

1. Создайте новый ключ на https://login.tailscale.com/admin/settings/keys
2. Обновите `.env`:
   ```bash
   TAILSCALE_AUTH_KEY=tskey-auth-NEW-KEY-HERE
   ```
3. Пересоздайте контейнер:
   ```bash
   docker-compose -f docker-compose.prod.tailscale.yml up -d --force-recreate tailscale
   ```

---

## Безопасность

### Tailscale ACL

Рекомендуется настроить ACL (Access Control Lists) в Tailscale для ограничения доступа:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["tag:zenzefi"],
      "dst": ["100.75.169.33:61000"]
    }
  ],
  "tagOwners": {
    "tag:zenzefi": ["your-email@example.com"]
  }
}
```

### Firewall на Zenzefi сервере

Убедитесь, что firewall разрешает подключения от Tailscale IP:

```bash
# Windows Firewall (на Zenzefi сервере)
New-NetFirewallRule -DisplayName "Zenzefi - Tailscale" `
  -Direction Inbound -LocalPort 61000 -Protocol TCP `
  -RemoteAddress 100.0.0.0/8 -Action Allow
```

---

## Сравнение вариантов деплоя

| Критерий | Tailscale в Docker | Tailscale на хосте |
|----------|-------------------|-------------------|
| **Изоляция** | ✅ Полная | ⚠️ Частичная |
| **Простота** | ⚠️ Сложнее | ✅ Проще |
| **Управление** | ✅ Docker Compose | ⚠️ Systemd |
| **Накладные расходы** | ⚠️ ~50MB RAM | ✅ ~30MB RAM |
| **Множественные VPN** | ✅ Легко | ⚠️ Сложнее |
| **Безопасность** | ✅ Privileged container | ✅ Root на хосте |

---

## Дополнительные ресурсы

- [Tailscale Documentation](https://tailscale.com/kb/)
- [Tailscale Docker Guide](https://tailscale.com/kb/1282/docker/)
- [Tailscale ACL Documentation](https://tailscale.com/kb/1018/acls/)
- [DEPLOYMENT_DOCKER.md](./DEPLOYMENT_DOCKER.md) - Полное руководство по Docker деплою
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Нативная установка без Docker

---

## Контакты и поддержка

При возникновении проблем с Tailscale VPN:

1. Проверьте логи: `docker logs zenzefi-tailscale`
2. Проверьте статус: `docker exec zenzefi-tailscale tailscale status`
3. Создайте issue в репозитории проекта
4. Обратитесь к документации Tailscale
