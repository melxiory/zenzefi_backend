#!/bin/bash

#
# Zenzefi Backend - Automated Docker Deployment Script
# Ubuntu 22.04 LTS
#

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
INSTALL_DIR="/opt/zenzefi"
DOMAIN=""
DB_PASSWORD=""
REDIS_PASSWORD=""
SECRET_KEY=""
LETSENCRYPT_EMAIL=""

# Functions
print_header() {
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Intro
print_header "Zenzefi Backend Docker Deployment"
echo "This script will install Docker and deploy:"
echo "  - PostgreSQL 15 (Docker)"
echo "  - Redis (Docker)"
echo "  - Zenzefi Backend (Docker)"
echo "  - Nginx + SSL (Docker)"
echo ""

# Collect configuration
read -p "Enter your domain (e.g., api.yourdomain.com): " DOMAIN
read -sp "Enter PostgreSQL password: " DB_PASSWORD
echo
read -sp "Enter Redis password: " REDIS_PASSWORD
echo
read -p "Enter your email for Let's Encrypt: " LETSENCRYPT_EMAIL
read -p "Enter Git repository URL: " GIT_REPO

# Generate SECRET_KEY
SECRET_KEY=$(openssl rand -base64 32)

echo ""
echo "Configuration:"
echo "  Domain: $DOMAIN"
echo "  Install directory: $INSTALL_DIR"
echo "  Database password: ********"
echo "  Redis password: ********"
echo "  Let's Encrypt email: $LETSENCRYPT_EMAIL"
echo ""

read -p "Continue with installation? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Update system
print_header "1. Updating System"
apt update && apt upgrade -y
print_success "System updated"

# Install dependencies
print_header "2. Installing Dependencies"
apt install -y curl git ufw ca-certificates gnupg lsb-release
print_success "Dependencies installed"

# Setup firewall
print_header "3. Configuring Firewall"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
print_success "Firewall configured"

# Install Docker
print_header "4. Installing Docker"

# Remove old versions
apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Add Docker GPG key
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

print_success "Docker installed"

# Clone repository
print_header "5. Cloning Repository"
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

if [ -d ".git" ]; then
    print_warning "Repository already exists, pulling updates"
    git pull origin main
else
    git clone $GIT_REPO .
fi

# Create directories
mkdir -p data/postgres data/redis data/certbot/conf data/certbot/www backups logs nginx/conf.d

print_success "Repository cloned"

# Create .env.prod
print_header "6. Creating Configuration Files"

cat > $INSTALL_DIR/.env.prod <<EOF
# Application
DEBUG=False
SECRET_KEY=$SECRET_KEY
BACKEND_URL=https://$DOMAIN

# Database
POSTGRES_SERVER=postgres
POSTGRES_PORT=5432
POSTGRES_USER=zenzefi_user
POSTGRES_PASSWORD=$DB_PASSWORD
POSTGRES_DB=zenzefi_prod

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=$REDIS_PASSWORD
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
EOF

chmod 600 $INSTALL_DIR/.env.prod
print_success ".env.prod created"

# Create docker-compose.prod.yml
cat > $INSTALL_DIR/docker-compose.prod.yml <<'EOFCOMPOSE'
version: '3.8'

services:
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
EOFCOMPOSE

print_success "docker-compose.prod.yml created"

# Create Dockerfile
cat > $INSTALL_DIR/Dockerfile <<'EOFDOCKER'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install poetry==1.7.1

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-root --no-interaction --no-ansi

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

RUN mkdir -p /app/logs

CMD poetry run alembic upgrade head && \
    poetry run uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info \
    --access-log \
    --proxy-headers
EOFDOCKER

print_success "Dockerfile created"

# Create Nginx config (temporary HTTP)
cat > $INSTALL_DIR/nginx/conf.d/zenzefi.conf <<EOFNGINX
upstream backend {
    server backend:8000;
}

server {
    listen 80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOFNGINX

print_success "Nginx config created"

# Build and start containers
print_header "7. Building Docker Images"
cd $INSTALL_DIR
docker compose -f docker-compose.prod.yml build
print_success "Docker images built"

# Start containers (without SSL first)
print_header "8. Starting Containers"
docker compose -f docker-compose.prod.yml up -d postgres redis backend nginx
sleep 10
print_success "Containers started"

# Obtain SSL certificate
print_header "9. Obtaining SSL Certificate"
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email $LETSENCRYPT_EMAIL \
    --agree-tos \
    --no-eff-email \
    -d $DOMAIN

print_success "SSL certificate obtained"

# Update Nginx config for HTTPS
print_header "10. Updating Nginx Configuration"

cat > $INSTALL_DIR/nginx/conf.d/zenzefi.conf <<EOFNGINXSSL
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone \$binary_remote_addr zone=auth_limit:10m rate=5r/s;

upstream backend {
    server backend:8000;
}

server {
    listen 80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers off;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    client_max_body_size 10M;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    location / {
        limit_req zone=api_limit burst=20 nodelay;

        proxy_pass http://backend;
        proxy_redirect off;
        proxy_buffering off;

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location ~ ^/api/v1/auth/(register|login) {
        limit_req zone=auth_limit burst=5 nodelay;
        proxy_pass http://backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /health {
        access_log off;
        proxy_pass http://backend;
    }
}
EOFNGINXSSL

# Restart Nginx
docker compose -f docker-compose.prod.yml restart nginx
print_success "Nginx configuration updated"

# Start certbot for auto-renewal
docker compose -f docker-compose.prod.yml up -d certbot
print_success "Certbot auto-renewal configured"

# Create backup script
print_header "11. Creating Backup Script"

cat > $INSTALL_DIR/backup.sh <<EOFBACKUP
#!/bin/bash
BACKUP_DIR="$INSTALL_DIR/backups"
DATE=\$(date +%Y%m%d_%H%M%S)

mkdir -p \$BACKUP_DIR

docker exec -e PGPASSWORD=$DB_PASSWORD zenzefi-postgres \\
    pg_dump -U zenzefi_user zenzefi_prod | \\
    gzip > \$BACKUP_DIR/postgres_\$DATE.sql.gz

find \$BACKUP_DIR -name "postgres_*.sql.gz" -mtime +7 -delete

echo "Backup completed: postgres_\$DATE.sql.gz"
EOFBACKUP

chmod +x $INSTALL_DIR/backup.sh

# Setup cron
(crontab -l 2>/dev/null; echo "0 3 * * * $INSTALL_DIR/backup.sh >> $INSTALL_DIR/backup.log 2>&1") | crontab -

print_success "Backup script created and scheduled"

# Final checks
print_header "12. Final Checks"
sleep 5

# Check containers
docker compose -f docker-compose.prod.yml ps

# Test API
echo ""
print_header "Testing API"
sleep 3

if curl -f -s -o /dev/null "https://$DOMAIN/health"; then
    print_success "API health check: OK"
else
    print_error "API health check: FAILED"
fi

# Summary
print_header "Deployment Complete!"
echo ""
echo "Your Zenzefi Backend is now running at:"
echo "  🌐 https://$DOMAIN"
echo "  📖 API Docs: https://$DOMAIN/docs"
echo "  💚 Health: https://$DOMAIN/health"
echo ""
echo "Docker containers:"
echo "  🐘 PostgreSQL: zenzefi-postgres"
echo "  🔴 Redis: zenzefi-redis"
echo "  🚀 Backend: zenzefi-backend"
echo "  🌐 Nginx: zenzefi-nginx"
echo "  🔒 Certbot: zenzefi-certbot"
echo ""
echo "Important credentials (save securely):"
echo "  Database password: $DB_PASSWORD"
echo "  Redis password: $REDIS_PASSWORD"
echo "  Secret key: $SECRET_KEY"
echo ""
echo "Useful commands:"
echo "  cd $INSTALL_DIR"
echo "  View logs: sudo docker compose -f docker-compose.prod.yml logs -f"
echo "  Restart all: sudo docker compose -f docker-compose.prod.yml restart"
echo "  Stop all: sudo docker compose -f docker-compose.prod.yml down"
echo "  View stats: sudo docker stats"
echo ""
print_success "Deployment script completed successfully! 🐳"