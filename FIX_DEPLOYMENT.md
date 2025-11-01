# Исправление проблем с развёрнутым бэкендом

## Проблемы

1. **Backend контейнер (unhealthy)**: Ошибка прав доступа к `/app/logs/error.log`
2. **Nginx контейнер (restarting)**: Отсутствует секция "events" в конфигурации

## Решение

### На сервере выполните следующие команды:

```bash
# 1. Перейти в директорию установки
cd /opt/zenzefi

# 2. Остановить контейнеры
sudo docker-compose -f docker-compose.prod.yml down

# 3. Создать главный конфиг nginx с секцией events
sudo tee nginx/nginx.conf > /dev/null <<'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 20M;

    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss;

    include /etc/nginx/conf.d/*.conf;
}
EOF

# 4. Исправить Dockerfile - переместить создание logs директории ДО переключения на пользователя zenzefi
sudo sed -i 's/RUN mkdir -p \/app\/logs/# Create non-root user for security\nRUN useradd -m -u 1000 zenzefi\n\n# Create logs directory with correct permissions\nRUN mkdir -p \/app\/logs \&\& chown -R zenzefi:zenzefi \/app/' Dockerfile

# Или вручную отредактируйте Dockerfile:
sudo nano Dockerfile
# Найдите секцию с RUN mkdir -p /app/logs и замените на:
#
# # Create non-root user for security
# RUN useradd -m -u 1000 zenzefi
#
# # Create logs directory with correct permissions
# RUN mkdir -p /app/logs && chown -R zenzefi:zenzefi /app
#
# USER zenzefi
  
# 5. Пересобрать backend образ
sudo docker-compose -f docker-compose.prod.yml build backend

# 6. Запустить контейнеры
sudo docker-compose -f docker-compose.prod.yml up -d

# 7. Проверить статус
sudo docker-compose -f docker-compose.prod.yml ps

# 8. Проверить логи backend
sudo docker-compose -f docker-compose.prod.yml logs -f backend

# 9. Проверить логи nginx
sudo docker-compose -f docker-compose.prod.yml logs -f nginx

# 10. Проверить health endpoint
curl http://localhost:8000/health
```

## Альтернативное решение (Самый простой способ - БЕЗ пересборки!)

Если вы не хотите редактировать Dockerfile и пересобирать образ, используйте этот способ:

```bash
cd /opt/zenzefi

# 1. Остановить контейнеры
sudo docker-compose -f docker-compose.prod.yml down

# 2. Создать nginx.conf (если ещё не создан)
sudo tee nginx/nginx.conf > /dev/null <<'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 20M;

    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss;

    include /etc/nginx/conf.d/*.conf;
}
EOF

# 3. Создать директорию logs на хосте с правильными правами
sudo mkdir -p logs
sudo chmod 777 logs  # Разрешить всем писать (временно для упрощения)

# 4. Запустить контейнеры
sudo docker-compose -f docker-compose.prod.yml up -d

# 5. Проверить статус (подождите 30-40 секунд)
sudo docker-compose -f docker-compose.prod.yml ps
```

### Пояснение:
- Директория `logs/` на хосте (/opt/zenzefi/logs) будет смонтирована в контейнер как `/app/logs`
- `chmod 777` даёт полные права всем (это безопасно, т.к. директория внутри /opt/zenzefi)
- Docker автоматически создаст файлы логов внутри этой директории

## Проверка результата

После исправления все контейнеры должны быть в состоянии "Up (healthy)":

```bash
sudo docker-compose -f docker-compose.prod.yml ps
```

Ожидаемый вывод:
```
zenzefi-backend    Up (healthy)     8000/tcp
zenzefi-certbot    Up               443/tcp, 80/tcp
zenzefi-nginx      Up               0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
zenzefi-postgres   Up (healthy)     5432/tcp
zenzefi-redis      Up (healthy)     6379/tcp
```

## Тестирование API

```bash
# На сервере
curl http://localhost:8000/health

# С вашего компьютера (замените YOUR_DOMAIN)
curl https://YOUR_DOMAIN/health
```

Ожидаемый ответ:
```json
{"status":"healthy","timestamp":"..."}
```

## Если проблема сохраняется

Соберите логи и отправьте их:

```bash
# Все логи
sudo docker-compose -f docker-compose.prod.yml logs > /tmp/zenzefi-logs.txt

# Только backend
sudo docker-compose -f docker-compose.prod.yml logs backend > /tmp/backend-logs.txt

# Только nginx
sudo docker-compose -f docker-compose.prod.yml logs nginx > /tmp/nginx-logs.txt
```
