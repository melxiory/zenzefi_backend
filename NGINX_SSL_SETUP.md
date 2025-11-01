# Настройка Nginx с SSL для Zenzefi Backend

## Проблема и решение

**Проблема:** Backend использует `network_mode: service:tailscale`, что означает, что он разделяет сетевой namespace с Tailscale контейнером. Из-за этого Nginx не может найти хост `backend` в обычной Docker сети.

**Решение:** Nginx обращается к `tailscale:8000` вместо `backend:8000`, так как backend доступен через сетевой интерфейс Tailscale контейнера.

## Первоначальная настройка (без SSL)

Для начальной настройки и получения Let's Encrypt сертификата:

```bash
# 1. Переименовать конфигурацию для начальной настройки
cd nginx/conf.d
mv zenzefi.conf zenzefi.conf.disabled
mv zenzefi-init.conf.disabled zenzefi-init.conf

# 2. Запустить контейнеры
cd ../..
docker-compose -f docker-compose.prod.tailscale.yml up -d

# 3. Проверить логи Nginx
docker logs zenzefi-nginx

# 4. Проверить, что backend доступен через HTTP
curl http://your-domain.com/health
# Должен вернуть: {"status": "healthy"}
```

## Получение SSL сертификата

После успешного запуска без SSL получите Let's Encrypt сертификат:

```bash
# 1. Остановить Nginx (чтобы certbot мог использовать порт 80)
docker-compose -f docker-compose.prod.tailscale.yml stop nginx

# 2. Получить сертификат
docker-compose -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
  --standalone \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email \
  -d melxiorylab.ru

# 3. Проверить, что сертификат создан
ls -la data/certbot/conf/live/melxiorylab.ru/
# Должны быть файлы: fullchain.pem, privkey.pem
```

## Переключение на SSL конфигурацию

После получения сертификата переключитесь на конфигурацию с HTTPS:

```bash
# 1. Переключить конфигурации
cd nginx/conf.d
mv zenzefi-init.conf zenzefi-init.conf.disabled
mv zenzefi.conf.disabled zenzefi.conf

# 2. Перезапустить Nginx
cd ../..
docker-compose -f docker-compose.prod.tailscale.yml restart nginx

# 3. Проверить логи
docker logs zenzefi-nginx

# 4. Проверить HTTPS
curl https://melxiorylab.ru/health
# Должен вернуть: {"status": "healthy"}
```

## Автоматическое обновление сертификатов

Certbot контейнер настроен на автоматическое обновление сертификатов каждые 12 часов:

```bash
# Проверить статус certbot контейнера
docker-compose -f docker-compose.prod.tailscale.yml ps certbot

# Проверить логи обновления
docker logs zenzefi-certbot

# Вручную обновить сертификаты (если нужно)
docker-compose -f docker-compose.prod.tailscale.yml run --rm certbot renew

# После обновления перезапустить Nginx
docker-compose -f docker-compose.prod.tailscale.yml restart nginx
```

## Проверка конфигурации

```bash
# Проверить синтаксис Nginx конфигурации
docker exec zenzefi-nginx nginx -t

# Проверить upstream статус
docker exec zenzefi-nginx cat /etc/nginx/conf.d/zenzefi.conf | grep upstream

# Проверить, что backend доступен из Nginx контейнера
docker exec zenzefi-nginx wget -O- http://tailscale:8000/health
```

## Отладка проблем

### Nginx не может подключиться к backend

```bash
# Проверить, что все контейнеры запущены и healthy
docker-compose -f docker-compose.prod.tailscale.yml ps

# Проверить логи backend
docker logs zenzefi-backend

# Проверить логи Tailscale
docker logs zenzefi-tailscale

# Проверить DNS резолвинг в Nginx контейнере
docker exec zenzefi-nginx nslookup tailscale

# Проверить сетевые подключения
docker exec zenzefi-nginx netstat -tlnp
```

### SSL сертификат не работает

```bash
# Проверить права доступа к сертификатам
ls -la data/certbot/conf/live/melxiorylab.ru/

# Проверить, что сертификаты смонтированы в контейнер
docker exec zenzefi-nginx ls -la /etc/letsencrypt/live/melxiorylab.ru/

# Проверить SSL конфигурацию
docker exec zenzefi-nginx nginx -T | grep ssl_certificate

# Проверить срок действия сертификата
openssl x509 -in data/certbot/conf/live/melxiorylab.ru/fullchain.pem -noout -dates
```

## Архитектура сети

```
[Интернет]
    ↓
[Nginx :80/:443]  ← в zenzefi-network
    ↓
[Tailscale :8000]  ← в zenzefi-network (backend использует его namespace)
    ↓
[Backend :8000]  ← использует network_mode: service:tailscale
    ↓
[PostgreSQL :5432] + [Redis :6379]  ← в zenzefi-network
```

**Ключевой момент:** Backend физически недоступен как отдельный хост в Docker сети, так как он использует `network_mode: service:tailscale`. Поэтому Nginx должен обращаться к `tailscale:8000`.

## Дополнительные настройки безопасности

После успешного запуска рекомендуется:

1. **Настроить firewall** (только порты 80 и 443):
```bash
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

2. **Ограничить доступ к Docker API**:
```bash
# В /etc/docker/daemon.json
{
  "hosts": ["unix:///var/run/docker.sock"]
}
```

3. **Настроить fail2ban для защиты от брутфорса**

4. **Регулярно обновлять Docker образы**:
```bash
docker-compose -f docker-compose.prod.tailscale.yml pull
docker-compose -f docker-compose.prod.tailscale.yml up -d
```

## Мониторинг

```bash
# Проверить статус всех сервисов
docker-compose -f docker-compose.prod.tailscale.yml ps

# Проверить использование ресурсов
docker stats

# Проверить логи в реальном времени
docker-compose -f docker-compose.prod.tailscale.yml logs -f

# Проверить health checks
docker inspect zenzefi-nginx | grep -A 10 Health
docker inspect zenzefi-backend | grep -A 10 Health
```
