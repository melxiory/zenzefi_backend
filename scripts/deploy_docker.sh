#!/bin/bash

#
# Zenzefi Backend - Automated Docker Deployment Script with Tailscale VPN
# Ubuntu 22.04 LTS
#
# This script deploys Zenzefi Backend with Tailscale VPN support
# using existing configuration files from the repository.
#

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
INSTALL_DIR="/opt/zenzefi"
DOMAIN=""
DB_PASSWORD=""
REDIS_PASSWORD=""
SECRET_KEY=""
LETSENCRYPT_EMAIL=""
TAILSCALE_AUTH_KEY=""
GIT_REPO=""

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

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Intro
print_header "Zenzefi Backend Docker Deployment with Tailscale VPN"
echo "This script will install Docker and deploy:"
echo "  - Tailscale VPN (Docker container)"
echo "  - PostgreSQL 15 (Docker)"
echo "  - Redis 7 (Docker)"
echo "  - Zenzefi Backend (Docker)"
echo "  - Nginx + SSL (Docker)"
echo ""
print_info "Using existing configuration files from repository"
echo ""

# Collect configuration
read -p "Enter your domain (e.g., melxiorylab.ru): " DOMAIN
read -sp "Enter PostgreSQL password: " DB_PASSWORD
echo
read -sp "Enter Redis password: " REDIS_PASSWORD
echo
read -p "Enter Tailscale Auth Key (from https://login.tailscale.com/admin/settings/keys): " TAILSCALE_AUTH_KEY
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
echo "  Tailscale Auth Key: ********"
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
apt install -y curl git ufw ca-certificates gnupg lsb-release openssl
print_success "Dependencies installed"

# Setup firewall
print_header "3. Configuring Firewall"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
print_success "Firewall configured (SSH, HTTP, HTTPS)"

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

# Start and enable Docker
systemctl start docker
systemctl enable docker

print_success "Docker installed and started"

# Clone repository
print_header "5. Cloning Repository"

if [ -d "$INSTALL_DIR/.git" ]; then
    print_warning "Repository already exists, pulling updates"
    cd $INSTALL_DIR
    git pull origin main
else
    # Check if directory exists and is not empty
    if [ -d "$INSTALL_DIR" ] && [ "$(ls -A $INSTALL_DIR)" ]; then
        print_error "Directory $INSTALL_DIR exists and is not empty"
        print_error "Please remove it or choose a different location"
        exit 1
    fi

    # Clone repository
    git clone $GIT_REPO $INSTALL_DIR
    cd $INSTALL_DIR
fi

print_success "Repository ready"

# Create data directories
print_header "6. Creating Data Directories"
cd $INSTALL_DIR
mkdir -p data/postgres data/redis data/tailscale data/certbot/conf data/certbot/www
mkdir -p logs backups
chmod 755 data/tailscale
print_success "Data directories created"

# Create .env file
print_header "7. Creating Environment Configuration"

cat > $INSTALL_DIR/.env <<EOF
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

# Tailscale VPN
TAILSCALE_AUTH_KEY=$TAILSCALE_AUTH_KEY

# Zenzefi Target Server (via Tailscale VPN)
# Update this IP after Tailscale connection is established
ZENZEFI_TARGET_URL=https://100.75.169.33:61000

# Token Pricing (MVP - free)
TOKEN_PRICE_1H=0.0
TOKEN_PRICE_12H=0.0
TOKEN_PRICE_24H=0.0
TOKEN_PRICE_WEEK=0.0
TOKEN_PRICE_MONTH=0.0

# Cookie Settings (HTTPS production)
COOKIE_SECURE=True
COOKIE_SAMESITE=none
EOF

chmod 600 $INSTALL_DIR/.env
print_success ".env file created"

# Update Nginx configuration with domain
print_header "8. Configuring Nginx for Domain"

# Backup original configs
cp nginx/conf.d/zenzefi.conf nginx/conf.d/zenzefi.conf.backup 2>/dev/null || true
cp nginx/conf.d/zenzefi-init.conf.disabled nginx/conf.d/zenzefi-init.conf.disabled.backup 2>/dev/null || true

# Update domain in configs (replace placeholder _ with actual domain)
sed -i "s/server_name _;/server_name $DOMAIN;/" nginx/conf.d/zenzefi.conf
sed -i "s|ssl_certificate /etc/letsencrypt/live/melxiorylab.ru/|ssl_certificate /etc/letsencrypt/live/$DOMAIN/|g" nginx/conf.d/zenzefi.conf
sed -i "s|ssl_certificate_key /etc/letsencrypt/live/melxiorylab.ru/|ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/|g" nginx/conf.d/zenzefi.conf

print_success "Nginx configuration updated for $DOMAIN"

# Prepare initial HTTP config (for SSL certificate generation)
print_header "9. Preparing Initial Configuration"

# Disable HTTPS config, enable HTTP-only config
mv nginx/conf.d/zenzefi.conf nginx/conf.d/zenzefi.conf.disabled
mv nginx/conf.d/zenzefi-init.conf.disabled nginx/conf.d/zenzefi-init.conf

print_success "Initial HTTP configuration enabled"

# Pull Docker images with retry
print_header "10. Pulling Docker Images"

pull_image_with_retry() {
    local image=$1
    local max_attempts=3
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        print_info "Pulling $image (attempt $attempt/$max_attempts)..."
        if docker pull $image; then
            print_success "Successfully pulled $image"
            return 0
        else
            print_warning "Failed to pull $image (attempt $attempt/$max_attempts)"
            if [ $attempt -lt $max_attempts ]; then
                print_info "Retrying in 10 seconds..."
                sleep 10
            fi
            attempt=$((attempt + 1))
        fi
    done

    print_error "Failed to pull $image after $max_attempts attempts"
    return 1
}

# Pull all required images
IMAGES=(
    "postgres:15-alpine"
    "redis:7-alpine"
    "nginx:alpine"
    "tailscale/tailscale:latest"
    "certbot/certbot:latest"
    "python:3.13-slim"
)

print_info "Pulling required Docker images..."
PULL_FAILED=0

for image in "${IMAGES[@]}"; do
    if ! pull_image_with_retry "$image"; then
        PULL_FAILED=1
    fi
done

if [ $PULL_FAILED -eq 1 ]; then
    print_error "Some images failed to download"
    print_warning "This might be due to:"
    echo "  - Slow or unstable internet connection"
    echo "  - Docker Hub rate limiting"
    echo "  - Firewall blocking Docker Hub"
    echo ""
    read -p "Do you want to continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

print_success "Docker images pulled"

# Build Docker images
print_header "11. Building Custom Docker Images"
docker compose -f docker-compose.prod.tailscale.yml build
print_success "Docker images built"

# Start containers (without Nginx first)
print_header "12. Starting Core Services"
docker compose -f docker-compose.prod.tailscale.yml up -d postgres redis tailscale backend

print_info "Waiting for services to be healthy (30 seconds)..."
sleep 30

# Check Tailscale status
print_info "Checking Tailscale connection..."
docker exec zenzefi-tailscale tailscale status || print_warning "Tailscale status check failed"

print_success "Core services started"

# Apply database migrations
print_header "13. Applying Database Migrations"
docker exec zenzefi-backend alembic upgrade head
print_success "Database migrations applied"

# Start Nginx for SSL certificate
print_header "14. Starting Nginx"
docker compose -f docker-compose.prod.tailscale.yml up -d nginx

print_info "Waiting for Nginx to start (10 seconds)..."
sleep 10

print_success "Nginx started"

# Obtain SSL certificate
print_header "15. Obtaining SSL Certificate"

# Stop Nginx to use certbot standalone
docker compose -f docker-compose.prod.tailscale.yml stop nginx

print_info "Running certbot in standalone mode..."
docker compose -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
    --standalone \
    --email $LETSENCRYPT_EMAIL \
    --agree-tos \
    --no-eff-email \
    -d $DOMAIN

# Check if certificate was obtained
if [ -f "data/certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    print_success "SSL certificate obtained successfully"
else
    print_error "SSL certificate generation failed"
    print_warning "You can try obtaining it manually later"
    print_info "Continuing with HTTP-only configuration..."
fi

# Switch to HTTPS configuration if certificate exists
if [ -f "data/certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    print_header "16. Enabling HTTPS Configuration"

    # Switch configs
    mv nginx/conf.d/zenzefi-init.conf nginx/conf.d/zenzefi-init.conf.disabled
    mv nginx/conf.d/zenzefi.conf.disabled nginx/conf.d/zenzefi.conf

    print_success "HTTPS configuration enabled"
else
    print_warning "Skipping HTTPS configuration (certificate not found)"
fi

# Restart all services
print_header "17. Restarting All Services"
docker compose -f docker-compose.prod.tailscale.yml restart
sleep 10
print_success "All services restarted"

# Start certbot for auto-renewal
docker compose -f docker-compose.prod.tailscale.yml up -d certbot
print_success "Certbot auto-renewal configured"

# Create backup script
print_header "18. Creating Backup Script"

# Ensure scripts directory exists
mkdir -p $INSTALL_DIR/scripts

cat > $INSTALL_DIR/scripts/backup.sh <<EOFBACKUP
#!/bin/bash
BACKUP_DIR="$INSTALL_DIR/backups"
DATE=\$(date +%Y%m%d_%H%M%S)

mkdir -p \$BACKUP_DIR

# Backup PostgreSQL
docker exec zenzefi-postgres pg_dump -U zenzefi_user zenzefi_prod | \\
    gzip > \$BACKUP_DIR/postgres_\$DATE.sql.gz

# Backup .env file
cp $INSTALL_DIR/.env \$BACKUP_DIR/env_\$DATE.backup

# Keep only last 7 days of backups
find \$BACKUP_DIR -name "postgres_*.sql.gz" -mtime +7 -delete
find \$BACKUP_DIR -name "env_*.backup" -mtime +7 -delete

echo "Backup completed: \$DATE"
echo "  - Database: postgres_\$DATE.sql.gz"
echo "  - Config: env_\$DATE.backup"
EOFBACKUP

chmod +x $INSTALL_DIR/scripts/backup.sh

# Setup cron for daily backups at 3 AM
(crontab -l 2>/dev/null | grep -v "$INSTALL_DIR/scripts/backup.sh"; echo "0 3 * * * $INSTALL_DIR/scripts/backup.sh >> $INSTALL_DIR/logs/backup.log 2>&1") | crontab -

print_success "Backup script created and scheduled (daily at 3 AM)"

# Final checks
print_header "19. Final System Checks"

echo ""
print_info "Container Status:"
docker compose -f docker-compose.prod.tailscale.yml ps
echo ""

print_info "Checking Tailscale VPN connection..."
if docker exec zenzefi-tailscale tailscale status > /dev/null 2>&1; then
    print_success "Tailscale VPN: Connected"
    docker exec zenzefi-tailscale tailscale ip -4 || true
else
    print_warning "Tailscale VPN: Status check failed"
fi

echo ""
print_info "Testing API endpoints..."
sleep 5

# Determine protocol
if [ -f "data/certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    PROTOCOL="https"
else
    PROTOCOL="http"
fi

# Test health endpoint
if curl -f -s -o /dev/null "$PROTOCOL://$DOMAIN/health"; then
    print_success "Health endpoint: OK ($PROTOCOL://$DOMAIN/health)"
else
    print_warning "Health endpoint: Not responding yet (may need more time)"
fi

# Test API docs
if curl -f -s -o /dev/null "$PROTOCOL://$DOMAIN/docs"; then
    print_success "API documentation: OK ($PROTOCOL://$DOMAIN/docs)"
else
    print_warning "API documentation: Not responding yet"
fi

# Summary
print_header "🎉 Deployment Complete!"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Your Zenzefi Backend is deployed at:"
if [ -f "data/certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    echo "   https://$DOMAIN"
    echo ""
    echo "📖 API Documentation: https://$DOMAIN/docs"
    echo "💚 Health Check: https://$DOMAIN/health"
else
    echo "   http://$DOMAIN (HTTP only - SSL setup incomplete)"
    echo ""
    echo "📖 API Documentation: http://$DOMAIN/docs"
    echo "💚 Health Check: http://$DOMAIN/health"
    echo ""
    print_warning "SSL certificate was not obtained. To set up HTTPS:"
    echo "   1. Ensure DNS is properly configured for $DOMAIN"
    echo "   2. Follow instructions in NGINX_SSL_SETUP.md"
fi

echo ""
echo "🐳 Docker Containers:"
echo "   - zenzefi-tailscale (Tailscale VPN)"
echo "   - zenzefi-postgres (PostgreSQL 15)"
echo "   - zenzefi-redis (Redis 7)"
echo "   - zenzefi-backend (FastAPI Backend)"
echo "   - zenzefi-nginx (Nginx Reverse Proxy)"
echo "   - zenzefi-certbot (SSL Certificate Management)"
echo ""
echo "🔐 Important Credentials (SAVE SECURELY):"
echo "   Database Password: $DB_PASSWORD"
echo "   Redis Password: $REDIS_PASSWORD"
echo "   Secret Key: $SECRET_KEY"
echo ""
echo "📁 Installation Directory: $INSTALL_DIR"
echo "📝 Logs Directory: $INSTALL_DIR/logs"
echo "💾 Backups: $INSTALL_DIR/backups (daily at 3 AM)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📚 Useful Commands:"
echo ""
echo "  # Navigate to project"
echo "  cd $INSTALL_DIR"
echo ""
echo "  # View all logs"
echo "  docker compose -f docker-compose.prod.tailscale.yml logs -f"
echo ""
echo "  # View specific service logs"
echo "  docker logs -f zenzefi-backend"
echo "  docker logs -f zenzefi-nginx"
echo "  docker logs -f zenzefi-tailscale"
echo ""
echo "  # Check service status"
echo "  docker compose -f docker-compose.prod.tailscale.yml ps"
echo ""
echo "  # Restart services"
echo "  docker compose -f docker-compose.prod.tailscale.yml restart"
echo ""
echo "  # Stop all services"
echo "  docker compose -f docker-compose.prod.tailscale.yml down"
echo ""
echo "  # Update and redeploy"
echo "  git pull origin main"
echo "  docker compose -f docker-compose.prod.tailscale.yml up -d --build"
echo ""
echo "  # Create backup manually"
echo "  $INSTALL_DIR/scripts/backup.sh"
echo ""
echo "  # Check Tailscale status"
echo "  docker exec zenzefi-tailscale tailscale status"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📖 Documentation:"
echo "   - Quick Deploy Checklist: $INSTALL_DIR/QUICK_DEPLOY_CHECKLIST.md"
echo "   - Nginx SSL Setup: $INSTALL_DIR/NGINX_SSL_SETUP.md"
echo "   - Tailscale Deployment: $INSTALL_DIR/docs/DEPLOYMENT_TAILSCALE.md"
echo ""

if [ ! -f "data/certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    print_warning "Next steps: Configure SSL certificate"
    echo "   Follow: $INSTALL_DIR/NGINX_SSL_SETUP.md"
    echo ""
fi

print_success "Deployment script completed successfully! 🚀"
echo ""
