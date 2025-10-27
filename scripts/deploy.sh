#!/bin/bash

#
# Zenzefi Backend - Automated Deployment Script
# Ubuntu 22.04 LTS
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_USER="zenzefi"
APP_DIR="/home/$APP_USER/apps/zenzefi_backend"
DOMAIN=""
DB_PASSWORD=""
REDIS_PASSWORD=""
SECRET_KEY=""

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

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Intro
print_header "Zenzefi Backend Deployment Script"
echo "This script will install and configure:"
echo "  - PostgreSQL 15"
echo "  - Redis"
echo "  - Python 3.11 + Poetry"
echo "  - Nginx + SSL (Let's Encrypt)"
echo "  - Systemd service"
echo ""

# Collect configuration
read -p "Enter your domain (e.g., api.yourdomain.com): " DOMAIN
read -p "Enter PostgreSQL password: " DB_PASSWORD
read -p "Enter Redis password: " REDIS_PASSWORD
read -p "Enter your email for Let's Encrypt: " LETSENCRYPT_EMAIL

# Generate SECRET_KEY
SECRET_KEY=$(openssl rand -base64 32)

echo ""
echo "Configuration:"
echo "  Domain: $DOMAIN"
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
apt install -y software-properties-common curl git ufw nginx redis-server postgresql-15 postgresql-contrib-15 certbot python3-certbot-nginx
print_success "Dependencies installed"

# Setup firewall
print_header "3. Configuring Firewall"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
print_success "Firewall configured"

# Install Python 3.11
print_header "4. Installing Python 3.11"
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.11 python3.11-venv python3.11-dev
print_success "Python 3.11 installed"

# Create app user
print_header "5. Creating Application User"
if id "$APP_USER" &>/dev/null; then
    print_warning "User $APP_USER already exists"
else
    adduser $APP_USER --disabled-password --gecos ""
    print_success "User $APP_USER created"
fi

# Configure PostgreSQL
print_header "6. Configuring PostgreSQL"
sudo -u postgres psql -c "CREATE USER zenzefi_user WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || print_warning "PostgreSQL user already exists"
sudo -u postgres psql -c "CREATE DATABASE zenzefi_prod OWNER zenzefi_user;" 2>/dev/null || print_warning "PostgreSQL database already exists"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE zenzefi_prod TO zenzefi_user;" 2>/dev/null
print_success "PostgreSQL configured"

# Configure Redis
print_header "7. Configuring Redis"
sed -i "s/^# requirepass .*/requirepass $REDIS_PASSWORD/" /etc/redis/redis.conf
sed -i "s/^requirepass .*/requirepass $REDIS_PASSWORD/" /etc/redis/redis.conf
systemctl restart redis-server
print_success "Redis configured"

# Install Poetry for app user
print_header "8. Installing Poetry"
sudo -u $APP_USER bash -c 'curl -sSL https://install.python-poetry.org | python3.11 -'
sudo -u $APP_USER bash -c 'echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc'
print_success "Poetry installed"

# Clone repository
print_header "9. Cloning Repository"
sudo -u $APP_USER mkdir -p /home/$APP_USER/apps
if [ -d "$APP_DIR" ]; then
    print_warning "Application directory already exists, skipping clone"
else
    read -p "Enter Git repository URL: " GIT_REPO
    sudo -u $APP_USER git clone $GIT_REPO $APP_DIR
    print_success "Repository cloned"
fi

# Install Python dependencies
print_header "10. Installing Python Dependencies"
cd $APP_DIR
sudo -u $APP_USER bash -c "cd $APP_DIR && /home/$APP_USER/.local/bin/poetry config virtualenvs.in-project true"
sudo -u $APP_USER bash -c "cd $APP_DIR && /home/$APP_USER/.local/bin/poetry install --no-dev --no-root"
print_success "Dependencies installed"

# Create .env file
print_header "11. Creating .env File"
cat > $APP_DIR/.env <<EOF
# Application
DEBUG=False
SECRET_KEY=$SECRET_KEY
BACKEND_URL=https://$DOMAIN

# Database
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=zenzefi_user
POSTGRES_PASSWORD=$DB_PASSWORD
POSTGRES_DB=zenzefi_prod

# Redis
REDIS_HOST=localhost
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

chown $APP_USER:$APP_USER $APP_DIR/.env
chmod 600 $APP_DIR/.env
print_success ".env file created"

# Run database migrations
print_header "12. Running Database Migrations"
sudo -u $APP_USER bash -c "cd $APP_DIR && /home/$APP_USER/.local/bin/poetry run alembic upgrade head"
print_success "Migrations applied"

# Create systemd service
print_header "13. Creating Systemd Service"
cat > /etc/systemd/system/zenzefi-backend.service <<EOF
[Unit]
Description=Zenzefi Backend FastAPI Application
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=notify
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/.venv/bin"
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app \\
    --host 127.0.0.1 \\
    --port 8000 \\
    --workers 4 \\
    --log-level info \\
    --access-log \\
    --proxy-headers \\
    --forwarded-allow-ips '*'

Restart=always
RestartSec=5

StandardOutput=journal
StandardError=journal
SyslogIdentifier=zenzefi-backend

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable zenzefi-backend
systemctl start zenzefi-backend
print_success "Systemd service created and started"

# Configure Nginx (HTTP only, for Certbot)
print_header "14. Configuring Nginx (temporary HTTP)"
cat > /etc/nginx/sites-available/zenzefi-backend <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/zenzefi-backend /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
print_success "Nginx configured"

# Obtain SSL certificate
print_header "15. Obtaining SSL Certificate"
certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email $LETSENCRYPT_EMAIL --redirect
print_success "SSL certificate obtained"

# Update Nginx configuration with full setup
print_header "16. Updating Nginx Configuration"
cat > /etc/nginx/sites-available/zenzefi-backend <<EOF
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone \$binary_remote_addr zone=auth_limit:10m rate=5r/s;

upstream zenzefi_backend {
    server 127.0.0.1:8000 fail_timeout=0;
}

server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    access_log /var/log/nginx/zenzefi-backend-access.log;
    error_log /var/log/nginx/zenzefi-backend-error.log;

    client_max_body_size 10M;
    client_body_timeout 60s;

    gzip on;
    gzip_vary on;
    gzip_min_length 1000;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss;

    location / {
        limit_req zone=api_limit burst=20 nodelay;

        proxy_pass http://zenzefi_backend;
        proxy_redirect off;
        proxy_buffering off;

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$server_name;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location ~ ^/api/v1/auth/(register|login) {
        limit_req zone=auth_limit burst=5 nodelay;

        proxy_pass http://zenzefi_backend;
        proxy_redirect off;
        proxy_buffering off;

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$server_name;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /health {
        access_log off;
        proxy_pass http://zenzefi_backend;
        proxy_set_header Host \$host;
    }
}
EOF

nginx -t
systemctl reload nginx
print_success "Nginx configuration updated"

# Create backup script
print_header "17. Creating Backup Script"
cat > /home/$APP_USER/backup_db.sh <<'EOF'
#!/bin/bash
BACKUP_DIR="/home/zenzefi/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="zenzefi_prod"
DB_USER="zenzefi_user"

mkdir -p $BACKUP_DIR
PGPASSWORD=$DB_PASSWORD pg_dump -U $DB_USER -h localhost $DB_NAME | gzip > $BACKUP_DIR/zenzefi_prod_$DATE.sql.gz
find $BACKUP_DIR -name "zenzefi_prod_*.sql.gz" -mtime +7 -delete
echo "Backup completed: zenzefi_prod_$DATE.sql.gz"
EOF

sed -i "s/\$DB_PASSWORD/$DB_PASSWORD/" /home/$APP_USER/backup_db.sh
chown $APP_USER:$APP_USER /home/$APP_USER/backup_db.sh
chmod +x /home/$APP_USER/backup_db.sh

# Setup cron for backups
(sudo -u $APP_USER crontab -l 2>/dev/null; echo "0 3 * * * /home/$APP_USER/backup_db.sh >> /home/$APP_USER/backup.log 2>&1") | sudo -u $APP_USER crontab -
print_success "Backup script created and scheduled"

# Final checks
print_header "18. Final Checks"
sleep 3

# Check services
systemctl is-active --quiet postgresql && print_success "PostgreSQL: Running" || print_error "PostgreSQL: Not running"
systemctl is-active --quiet redis-server && print_success "Redis: Running" || print_error "Redis: Not running"
systemctl is-active --quiet zenzefi-backend && print_success "Backend: Running" || print_error "Backend: Not running"
systemctl is-active --quiet nginx && print_success "Nginx: Running" || print_error "Nginx: Not running"

# Test API
echo ""
print_header "Testing API"
sleep 2
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
echo "Important credentials (save securely):"
echo "  Database password: $DB_PASSWORD"
echo "  Redis password: $REDIS_PASSWORD"
echo "  Secret key: $SECRET_KEY"
echo ""
echo "Next steps:"
echo "  1. Update ZENZEFI_BASIC_AUTH_USER and ZENZEFI_BASIC_AUTH_PASSWORD in .env"
echo "  2. Edit .env: sudo nano $APP_DIR/.env"
echo "  3. Restart backend: sudo systemctl restart zenzefi-backend"
echo "  4. Create first user via API"
echo ""
echo "Useful commands:"
echo "  View logs: sudo journalctl -u zenzefi-backend -f"
echo "  Restart backend: sudo systemctl restart zenzefi-backend"
echo "  Check status: sudo systemctl status zenzefi-backend"
echo ""
print_success "Deployment script completed successfully!"