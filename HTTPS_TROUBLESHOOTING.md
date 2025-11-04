# HTTPS Troubleshooting Guide

Это руководство поможет диагностировать и исправить проблемы с HTTPS после деплоя.

## Быстрое исправление

### Автоматическая диагностика и исправление

```bash
cd /opt/zenzefi
sudo bash scripts/fix_ssl.sh
```

Этот скрипт автоматически:
- Проверит статус SSL-сертификата
- Проверит активную конфигурацию Nginx
- Проверит порты и firewall
- Предложит исправить обнаруженные проблемы
- При необходимости получит SSL-сертификат через Let's Encrypt

---

## Ручная диагностика

### Шаг 1: Проверка статуса контейнеров

```bash
cd /opt/zenzefi
docker compose -f docker-compose.prod.tailscale.yml ps
```

**Ожидаемый результат:** Все контейнеры в статусе "Up" и "healthy".

**Если контейнеры не запущены:**
```bash
docker compose -f docker-compose.prod.tailscale.yml up -d
```

### Шаг 2: Проверка наличия SSL-сертификата

```bash
# Проверить наличие сертификата (замените melxiorylab.ru на ваш домен)
ls -la /opt/zenzefi/data/certbot/conf/live/melxiorylab.ru/
```

**Ожидаемый результат:** Должны быть файлы `fullchain.pem` и `privkey.pem`.

**Если сертификата нет:**
```bash
# Проверить логи certbot
docker logs zenzefi-certbot
```

### Шаг 3: Проверка активной конфигурации Nginx

```bash
cd /opt/zenzefi
ls -la nginx/conf.d/
```

**Правильная конфигурация для HTTPS:**
- ✅ `zenzefi.conf` - должен существовать (HTTPS конфигурация)
- ✅ `zenzefi-init.conf.disabled` - должен быть отключен (HTTP-only конфигурация)

**Неправильная конфигурация (только HTTP):**
- ❌ `zenzefi.conf.disabled` - HTTPS конфигурация отключена
- ❌ `zenzefi-init.conf` - HTTP-only конфигурация активна

### Шаг 4: Проверка логов Nginx

```bash
# Последние 50 строк логов
docker logs zenzefi-nginx --tail 50

# Следить за логами в реальном времени
docker logs -f zenzefi-nginx
```

**Распространённые ошибки:**

1. **"SSL: error:02001002:system library:fopen:No such file or directory"**
   - Сертификат не найден
   - Решение: Получить сертификат через Let's Encrypt

2. **"nginx: [emerg] host not found in upstream"**
   - Backend не доступен для Nginx
   - Решение: Проверить, что backend контейнер запущен

3. **"connect() failed (111: Connection refused)"**
   - Backend не отвечает на порту 8000
   - Решение: Проверить логи backend: `docker logs zenzefi-backend`

### Шаг 5: Проверка портов

```bash
# Проверить, что Nginx слушает порты 80 и 443
ss -tuln | grep -E ':80|:443'
# Или используйте netstat
netstat -tuln | grep -E ':80|:443'
```

**Ожидаемый результат:**
```
tcp   LISTEN 0      511          0.0.0.0:80         0.0.0.0:*
tcp   LISTEN 0      511          0.0.0.0:443        0.0.0.0:*
```

### Шаг 6: Проверка firewall

```bash
# Проверить статус UFW
sudo ufw status

# Должно быть:
# 80/tcp                     ALLOW       Anywhere
# 443/tcp                    ALLOW       Anywhere
```

**Если порт 443 не открыт:**
```bash
sudo ufw allow 443/tcp
```

### Шаг 7: Тестирование HTTPS подключения

```bash
# Тест с локального сервера (самоподписанный сертификат допустим)
curl -k -v https://localhost/health

# Тест через доменное имя (замените melxiorylab.ru на ваш домен)
curl -v https://melxiorylab.ru/health

# Проверка сертификата
openssl s_client -connect melxiorylab.ru:443 -servername melxiorylab.ru
```

---

## Типовые проблемы и решения

### Проблема 1: Сертификат не получен во время деплоя

**Симптомы:**
- Работает только HTTP (port 80)
- HTTPS (port 443) не отвечает
- В логах certbot есть ошибки

**Причины:**
1. DNS не настроен или не распространился (TTL)
2. Порт 80 или 443 заблокирован файрволом
3. Let's Encrypt не может достучаться до сервера

**Решение:**

1. Проверьте DNS:
```bash
# Должен показывать IP вашего сервера
nslookup melxiorylab.ru

# Или
dig melxiorylab.ru +short
```

2. Проверьте доступность порта 80 снаружи:
```bash
# С другого компьютера или используйте онлайн сервисы типа:
# https://www.yougetsignal.com/tools/open-ports/
curl http://ваш-домен.ru
```

3. Получите сертификат вручную:
```bash
cd /opt/zenzefi

# Убедитесь, что активна HTTP-only конфигурация
sudo mv nginx/conf.d/zenzefi.conf nginx/conf.d/zenzefi.conf.disabled 2>/dev/null || true
sudo mv nginx/conf.d/zenzefi-init.conf.disabled nginx/conf.d/zenzefi-init.conf 2>/dev/null || true

# Перезапустите Nginx
docker compose -f docker-compose.prod.tailscale.yml restart nginx
sleep 5

# Попробуйте метод webroot (предпочтительно)
docker compose -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@example.com \
    --agree-tos \
    --no-eff-email \
    -d your-domain.com

# Если webroot не работает, используйте standalone
# (нужно остановить Nginx)
docker compose -f docker-compose.prod.tailscale.yml stop nginx

docker compose -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
    --standalone \
    --email your-email@example.com \
    --agree-tos \
    --no-eff-email \
    -d your-domain.com

# После получения сертификата переключитесь на HTTPS конфигурацию
sudo mv nginx/conf.d/zenzefi-init.conf nginx/conf.d/zenzefi-init.conf.disabled
sudo mv nginx/conf.d/zenzefi.conf.disabled nginx/conf.d/zenzefi.conf

# Запустите Nginx с HTTPS
docker compose -f docker-compose.prod.tailscale.yml up -d nginx
```

### Проблема 2: Сертификат есть, но HTTPS не работает

**Симптомы:**
- Сертификат присутствует в `data/certbot/conf/live/домен/`
- HTTP работает, но HTTPS не отвечает
- Nginx запущен, ошибок в логах нет

**Причины:**
- Активна HTTP-only конфигурация вместо HTTPS
- Конфигурация не обновилась после получения сертификата

**Решение:**

```bash
cd /opt/zenzefi

# Проверьте активную конфигурацию
ls -la nginx/conf.d/

# Переключитесь на HTTPS конфигурацию
sudo mv nginx/conf.d/zenzefi-init.conf nginx/conf.d/zenzefi-init.conf.disabled 2>/dev/null || true
sudo mv nginx/conf.d/zenzefi.conf.disabled nginx/conf.d/zenzefi.conf 2>/dev/null || true

# Проверьте конфигурацию Nginx
docker exec zenzefi-nginx nginx -t

# Перезапустите Nginx
docker compose -f docker-compose.prod.tailscale.yml restart nginx

# Дайте время на запуск
sleep 5

# Проверьте, что порт 443 слушается
ss -tuln | grep :443

# Протестируйте HTTPS
curl -k -v https://localhost/health
```

### Проблема 3: "ERR_SSL_PROTOCOL_ERROR" в браузере

**Симптомы:**
- Браузер показывает "ERR_SSL_PROTOCOL_ERROR"
- `curl` не может подключиться по HTTPS

**Причины:**
- Nginx не слушает порт 443
- SSL конфигурация некорректна
- Сертификат поврежден

**Решение:**

```bash
# 1. Проверьте, что Nginx слушает порт 443
docker exec zenzefi-nginx netstat -tuln | grep :443

# 2. Проверьте конфигурацию Nginx
docker exec zenzefi-nginx nginx -t

# 3. Проверьте права на сертификат
ls -la /opt/zenzefi/data/certbot/conf/live/your-domain.com/

# 4. Проверьте содержимое сертификата
openssl x509 -in /opt/zenzefi/data/certbot/conf/live/your-domain.com/fullchain.pem -text -noout

# 5. Перезапустите Nginx с чистой конфигурацией
docker compose -f docker-compose.prod.tailscale.yml restart nginx

# 6. Проверьте логи
docker logs zenzefi-nginx --tail 100
```

### Проблема 4: HTTP не редиректит на HTTPS

**Симптомы:**
- HTTPS работает
- HTTP тоже работает, но не редиректит на HTTPS

**Причины:**
- Активна HTTP-only конфигурация (`zenzefi-init.conf`)
- HTTPS конфигурация отключена

**Решение:** См. "Проблема 2" выше.

### Проблема 5: Сертификат просрочен или скоро истечёт

**Симптомы:**
- Браузер показывает предупреждение о просроченном сертификате
- `openssl x509 -checkend` показывает, что сертификат истёк

**Решение:**

```bash
cd /opt/zenzefi

# Обновите сертификат вручную
docker compose -f docker-compose.prod.tailscale.yml run --rm certbot renew

# Перезапустите Nginx для применения нового сертификата
docker compose -f docker-compose.prod.tailscale.yml restart nginx

# Проверьте новую дату истечения
openssl x509 -enddate -noout -in data/certbot/conf/live/your-domain.com/fullchain.pem
```

**Автоматическое обновление:**
Контейнер `certbot` настроен на автоматическое обновление каждые 12 часов. Проверьте его статус:

```bash
docker logs zenzefi-certbot --tail 50
```

---

## Проверочный чеклист

После исправления проблемы проверьте:

- [ ] Контейнер `zenzefi-nginx` запущен и healthy
- [ ] Сертификат существует: `/opt/zenzefi/data/certbot/conf/live/ваш-домен/fullchain.pem`
- [ ] Активна HTTPS конфигурация: `nginx/conf.d/zenzefi.conf` (без `.disabled`)
- [ ] HTTP-only конфигурация отключена: `nginx/conf.d/zenzefi-init.conf.disabled`
- [ ] Nginx слушает порт 443: `ss -tuln | grep :443`
- [ ] Firewall разрешает порт 443: `sudo ufw status`
- [ ] HTTPS endpoint отвечает: `curl -k https://localhost/health`
- [ ] HTTP редиректит на HTTPS: `curl -I http://ваш-домен/health` (301/302)
- [ ] Сертификат валиден: `openssl x509 -checkend 86400 -in data/certbot/conf/live/ваш-домен/fullchain.pem`

---

## Полезные команды

### Просмотр логов

```bash
# Все логи
docker compose -f docker-compose.prod.tailscale.yml logs -f

# Только Nginx
docker logs -f zenzefi-nginx

# Только Backend
docker logs -f zenzefi-backend

# Только Certbot
docker logs zenzefi-certbot --tail 100
```

### Управление конфигурацией

```bash
cd /opt/zenzefi/nginx/conf.d/

# Включить HTTPS конфигурацию
sudo mv zenzefi.conf.disabled zenzefi.conf 2>/dev/null || true
sudo mv zenzefi-init.conf zenzefi-init.conf.disabled 2>/dev/null || true
docker compose -f /opt/zenzefi/docker-compose.prod.tailscale.yml restart nginx

# Включить HTTP-only конфигурацию (для получения сертификата)
sudo mv zenzefi.conf zenzefi.conf.disabled 2>/dev/null || true
sudo mv zenzefi-init.conf.disabled zenzefi-init.conf 2>/dev/null || true
docker compose -f /opt/zenzefi/docker-compose.prod.tailscale.yml restart nginx
```

### Проверка Nginx

```bash
# Проверить синтаксис конфигурации
docker exec zenzefi-nginx nginx -t

# Перезагрузить конфигурацию без перезапуска контейнера
docker exec zenzefi-nginx nginx -s reload

# Просмотр активной конфигурации
docker exec zenzefi-nginx cat /etc/nginx/conf.d/zenzefi.conf
```

### Работа с сертификатами

```bash
# Просмотр информации о сертификате
openssl x509 -in /opt/zenzefi/data/certbot/conf/live/your-domain.com/fullchain.pem -text -noout

# Проверка даты истечения
openssl x509 -enddate -noout -in /opt/zenzefi/data/certbot/conf/live/your-domain.com/fullchain.pem

# Проверка валидности (24 часа)
openssl x509 -checkend 86400 -noout -in /opt/zenzefi/data/certbot/conf/live/your-domain.com/fullchain.pem

# Тест SSL подключения
openssl s_client -connect your-domain.com:443 -servername your-domain.com

# Обновление сертификата
docker compose -f docker-compose.prod.tailscale.yml run --rm certbot renew

# Принудительное обновление (даже если не истёк)
docker compose -f docker-compose.prod.tailscale.yml run --rm certbot renew --force-renewal
```

---

## Дополнительная помощь

Если проблема не решена:

1. Соберите диагностическую информацию:
```bash
cd /opt/zenzefi

# Статус контейнеров
docker compose -f docker-compose.prod.tailscale.yml ps > diagnostic.txt

# Логи
docker logs zenzefi-nginx --tail 100 >> diagnostic.txt
docker logs zenzefi-backend --tail 100 >> diagnostic.txt
docker logs zenzefi-certbot --tail 100 >> diagnostic.txt

# Конфигурация
ls -la nginx/conf.d/ >> diagnostic.txt
cat nginx/conf.d/zenzefi.conf >> diagnostic.txt 2>&1 || echo "HTTPS config not found" >> diagnostic.txt
cat nginx/conf.d/zenzefi-init.conf >> diagnostic.txt 2>&1 || echo "HTTP config not found" >> diagnostic.txt

# Сертификаты
ls -la data/certbot/conf/live/ >> diagnostic.txt

# Порты
ss -tuln | grep -E ':80|:443' >> diagnostic.txt

# Тест подключения
curl -v https://localhost/health >> diagnostic.txt 2>&1
```

2. Просмотрите файл `diagnostic.txt` для анализа проблемы

3. Обратитесь в поддержку с собранной информацией

---

## См. также

- [DEPLOYMENT_DOCKER.md](docs/DEPLOYMENT_DOCKER.md) - Полная документация по деплою
- [NGINX_SSL_SETUP.md](NGINX_SSL_SETUP.md) - Настройка SSL для Nginx
- [QUICK_DEPLOY_CHECKLIST.md](QUICK_DEPLOY_CHECKLIST.md) - Чеклист для быстрого деплоя