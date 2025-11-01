# Чеклист быстрого деплоя Zenzefi Backend

Краткая пошаговая инструкция для деплоя на production сервере с Tailscale VPN.

## Предварительная подготовка

- [ ] Домен настроен и указывает на сервер (A-запись)
- [ ] Сервер доступен по SSH
- [ ] Docker и Docker Compose установлены
- [ ] Tailscale Auth Key получен с https://login.tailscale.com/admin/settings/keys

## 1. Клонирование и настройка

```bash
# Клонировать репозиторий
cd /opt
git clone <repo-url> zenzefi_backend
cd zenzefi_backend

# Создать .env из примера
cp .env.example .env
nano .env
```

**Обязательные переменные в .env:**
```bash
SECRET_KEY=<случайная-строка-минимум-32-символа>
POSTGRES_PASSWORD=<надежный-пароль>
REDIS_PASSWORD=<надежный-пароль>
TAILSCALE_AUTH_KEY=tskey-auth-xxxxxxxxxxxxx
ZENZEFI_TARGET_URL=https://100.75.169.33:61000
BACKEND_URL=https://ваш-домен.ru
COOKIE_SECURE=True
COOKIE_SAMESITE=none
```

- [ ] .env файл создан и заполнен

## 2. Создание директорий

```bash
mkdir -p data/{postgres,redis,tailscale,certbot/conf,certbot/www}
mkdir -p logs
chmod 755 data/tailscale
```

- [ ] Все директории созданы

## 3. Первоначальный запуск (без SSL)

```bash
# Переименовать конфигурации для HTTP
cd nginx/conf.d
mv zenzefi.conf zenzefi.conf.disabled
mv zenzefi-init.conf.disabled zenzefi-init.conf
cd ../..

# Запустить все сервисы
docker-compose -f docker-compose.prod.tailscale.yml up -d

# Проверить статус
docker-compose -f docker-compose.prod.tailscale.yml ps
```

**Все контейнеры должны быть "Up (healthy)":**
- [ ] zenzefi-postgres
- [ ] zenzefi-redis
- [ ] zenzefi-tailscale
- [ ] zenzefi-backend
- [ ] zenzefi-nginx

## 4. Проверка Tailscale VPN

```bash
# Проверить статус Tailscale
docker exec zenzefi-tailscale tailscale status

# Проверить доступность Zenzefi сервера из backend
docker exec zenzefi-backend curl -k https://100.75.169.33:61000 -I
```

- [ ] Tailscale подключен
- [ ] Zenzefi сервер доступен (HTTP 200 или 401)

## 5. Применение миграций

```bash
# Применить миграции базы данных
docker exec zenzefi-backend alembic upgrade head
```

- [ ] Миграции применены без ошибок

## 6. Проверка HTTP доступа

```bash
# Проверить health endpoint
curl http://ваш-домен.ru/health
# Ожидается: {"status":"healthy"}
```

- [ ] Backend отвечает через HTTP

## 7. Получение SSL сертификата

```bash
# Остановить Nginx для certbot standalone
docker-compose -f docker-compose.prod.tailscale.yml stop nginx

# Получить сертификат Let's Encrypt
docker-compose -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
  --standalone \
  --email ваш-email@example.com \
  --agree-tos \
  --no-eff-email \
  -d ваш-домен.ru

# Проверить, что сертификат создан
ls -la data/certbot/conf/live/ваш-домен.ru/
```

**Должны быть файлы:**
- [ ] fullchain.pem
- [ ] privkey.pem

## 8. Переключение на HTTPS

```bash
# Обновить конфигурацию Nginx для HTTPS
cd nginx/conf.d
mv zenzefi-init.conf zenzefi-init.conf.disabled
mv zenzefi.conf.disabled zenzefi.conf

# Обновить server_name в zenzefi.conf
nano zenzefi.conf
# Измените: server_name _; → server_name ваш-домен.ru;
# Измените пути к сертификатам на ваш домен

cd ../..

# Перезапустить Nginx
docker-compose -f docker-compose.prod.tailscale.yml restart nginx
```

- [ ] Конфигурация обновлена
- [ ] Nginx перезапущен

## 9. Проверка HTTPS

```bash
# Проверить HTTPS доступ
curl https://ваш-домен.ru/health
# Ожидается: {"status":"healthy"}

# Проверить редирект с HTTP на HTTPS
curl -I http://ваш-домен.ru/health
# Ожидается: 301 Moved Permanently, Location: https://...

# Проверить SSL сертификат
openssl s_client -connect ваш-домен.ru:443 -servername ваш-домен.ru </dev/null 2>/dev/null | grep -A 5 "Verify return code"
# Ожидается: Verify return code: 0 (ok)
```

- [ ] HTTPS работает
- [ ] HTTP редиректится на HTTPS
- [ ] SSL сертификат валиден

## 10. Создание первого пользователя

```bash
# Опционально: создать суперпользователя
docker exec -it zenzefi-backend python scripts/create_superuser.py

# Или использовать API для регистрации
curl -X POST https://ваш-домен.ru/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "username": "admin",
    "password": "secure-password-here",
    "full_name": "Admin User"
  }'
```

- [ ] Тестовый пользователь создан

## 11. Финальные проверки

```bash
# Проверить все контейнеры
docker-compose -f docker-compose.prod.tailscale.yml ps

# Проверить логи на ошибки
docker-compose -f docker-compose.prod.tailscale.yml logs --tail=50

# Проверить использование ресурсов
docker stats --no-stream

# Проверить автоматический рестарт
docker-compose -f docker-compose.prod.tailscale.yml restart backend
sleep 10
curl https://ваш-домен.ru/health
```

- [ ] Все контейнеры работают
- [ ] Нет критических ошибок в логах
- [ ] Ресурсы используются разумно
- [ ] Автоматический рестарт работает

## 12. Настройка мониторинга и бэкапов

```bash
# Настроить автоматические бэкапы PostgreSQL (cron)
crontab -e
# Добавить:
# 0 3 * * * cd /opt/zenzefi_backend && ./scripts/backup.sh

# Настроить мониторинг health check
# (опционально через UptimeRobot, Pingdom и т.д.)
```

- [ ] Автоматические бэкапы настроены
- [ ] Мониторинг настроен

## 13. Безопасность

```bash
# Настроить firewall (UFW)
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (для Let's Encrypt)
ufw allow 443/tcp   # HTTPS
ufw enable

# Проверить права доступа
ls -la .env         # Должен быть -rw------- или -rw-r-----
ls -la data/        # Владелец: root или текущий пользователь
```

- [ ] Firewall настроен
- [ ] Права доступа корректны

## Troubleshooting

### Nginx не может подключиться к backend

```bash
# Проверить, что backend использует tailscale namespace
docker inspect zenzefi-backend | grep NetworkMode
# Должно быть: "NetworkMode": "container:zenzefi-tailscale"

# Проверить, что Nginx может резолвить tailscale
docker exec zenzefi-nginx nslookup tailscale

# Проверить доступность backend через tailscale хост
docker exec zenzefi-nginx wget -O- http://tailscale:8000/health
```

### SSL сертификат не работает

```bash
# Проверить сертификаты
docker exec zenzefi-nginx ls -la /etc/letsencrypt/live/ваш-домен.ru/

# Проверить конфигурацию Nginx
docker exec zenzefi-nginx nginx -t

# Посмотреть логи Nginx
docker logs zenzefi-nginx
```

### Backend не может подключиться к Zenzefi

```bash
# Проверить Tailscale статус
docker exec zenzefi-tailscale tailscale status

# Проверить доступность Zenzefi
docker exec zenzefi-backend ping 100.75.169.33

# Проверить переменные окружения
docker exec zenzefi-backend env | grep ZENZEFI_TARGET_URL
```

## Дополнительная документация

- **Подробная инструкция:** [DEPLOYMENT_TAILSCALE.md](docs/DEPLOYMENT_TAILSCALE.md)
- **Настройка Nginx и SSL:** [NGINX_SSL_SETUP.md](NGINX_SSL_SETUP.md)
- **Docker деплой:** [DEPLOYMENT_DOCKER.md](docs/DEPLOYMENT_DOCKER.md)

## Контакты

При возникновении проблем:
1. Проверьте логи: `docker-compose -f docker-compose.prod.tailscale.yml logs`
2. Создайте issue в репозитории проекта
3. Обратитесь к документации выше

---

**Статус:** ✅ Деплой завершен успешно!
