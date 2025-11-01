#!/bin/bash

# Быстрое исправление проблем с развёрнутым бэкендом
# Запустите этот скрипт на сервере: sudo bash QUICK_FIX.sh

set -e

echo "🔧 Исправление проблем с Zenzefi Backend..."
echo ""

# 1. Перейти в директорию
cd /opt/zenzefi
echo "✓ Перешли в /opt/zenzefi"

# 2. Остановить контейнеры
echo "⏸️  Останавливаем контейнеры..."
docker-compose -f docker-compose.prod.yml down
echo "✓ Контейнеры остановлены"

# 3. Создать nginx.conf
echo "📝 Создаём nginx.conf..."
cat > nginx/nginx.conf <<'EOF'
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
echo "✓ nginx.conf создан"

# 4. Создать директорию logs с правильными правами
echo "📁 Создаём директорию logs..."
mkdir -p logs
chmod 777 logs
echo "✓ Директория logs создана с правами 777"

# 5. Запустить контейнеры
echo "🚀 Запускаем контейнеры..."
docker-compose -f docker-compose.prod.yml up -d
echo "✓ Контейнеры запущены"

# 6. Подождать немного
echo ""
echo "⏳ Ожидание 40 секунд для healthcheck..."
sleep 40

# 7. Проверить статус
echo ""
echo "📊 Статус контейнеров:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "📋 Проверка логов backend (последние 20 строк):"
docker-compose -f docker-compose.prod.yml logs --tail=20 backend

echo ""
echo "🏥 Проверка health endpoint:"
curl -s http://localhost:8000/health | jq . || curl -s http://localhost:8000/health

echo ""
echo "✅ Готово! Проверьте статус выше."
echo ""
echo "Для просмотра логов используйте:"
echo "  sudo docker-compose -f /opt/zenzefi/docker-compose.prod.yml logs -f backend"
echo ""
