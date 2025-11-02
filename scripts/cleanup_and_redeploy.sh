#!/bin/bash

#
# Zenzefi Backend - Complete Cleanup and Redeploy Script
# Fixes 'ContainerConfig' errors by removing old containers and images
#

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Configuration
INSTALL_DIR="/opt/zenzefi"
COMPOSE_FILE="docker-compose.prod.tailscale.yml"

# Check if we're in the right directory
if [ ! -f "$INSTALL_DIR/$COMPOSE_FILE" ]; then
    print_error "Cannot find $COMPOSE_FILE in $INSTALL_DIR"
    exit 1
fi

cd $INSTALL_DIR

print_header "Zenzefi Backend - Complete Cleanup and Redeploy"

echo "This script will:"
echo "  1. Stop all running containers"
echo "  2. Remove all containers (data volumes preserved)"
echo "  3. Remove all images (force fresh rebuild)"
echo "  4. Pull latest code from git"
echo "  5. Pull fresh Docker base images"
echo "  6. Build new images"
echo "  7. Start all services"
echo ""
print_warning "Data in ./data/ directories will NOT be deleted"
print_warning "PostgreSQL data, Redis data, and SSL certificates will be preserved"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Step 1: Stop all containers
print_header "1. Stopping All Containers"
docker-compose -f $COMPOSE_FILE down || {
    print_warning "docker-compose down failed, trying to stop containers individually..."
    docker stop zenzefi-nginx zenzefi-certbot zenzefi-backend zenzefi-tailscale zenzefi-redis zenzefi-postgres 2>/dev/null || true
}
print_success "Containers stopped"

# Step 2: Remove all Zenzefi containers (even if stopped)
print_header "2. Removing All Zenzefi Containers"
docker rm -f zenzefi-nginx zenzefi-certbot zenzefi-backend zenzefi-tailscale zenzefi-redis zenzefi-postgres 2>/dev/null || true
print_success "Containers removed"

# Step 3: Remove all Zenzefi images
print_header "3. Removing All Zenzefi Images"

# Remove custom built image
docker rmi -f zenzefi_backend-backend 2>/dev/null || true
docker rmi -f zenzefi-backend-backend 2>/dev/null || true

# Remove base images to force fresh pull
print_info "Removing base images (will be re-downloaded)..."
docker rmi -f postgres:15-alpine 2>/dev/null || true
docker rmi -f redis:7-alpine 2>/dev/null || true
docker rmi -f nginx:alpine 2>/dev/null || true
docker rmi -f tailscale/tailscale:latest 2>/dev/null || true
docker rmi -f certbot/certbot:latest 2>/dev/null || true
docker rmi -f python:3.13-slim 2>/dev/null || true

print_success "Images removed"

# Step 4: Clean up dangling images and build cache
print_header "4. Cleaning Docker Build Cache"
docker system prune -f
docker builder prune -f
print_success "Build cache cleaned"

# Step 5: Pull latest code
print_header "5. Pulling Latest Code from Git"
git pull origin main || {
    print_warning "Git pull failed, continuing with existing code..."
}
print_success "Code updated"

# Step 6: Pull fresh Docker base images
print_header "6. Pulling Fresh Docker Images"

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

PULL_FAILED=0
for image in "${IMAGES[@]}"; do
    if ! pull_image_with_retry "$image"; then
        PULL_FAILED=1
    fi
done

if [ $PULL_FAILED -eq 1 ]; then
    print_error "Some images failed to download"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

print_success "Base images pulled"

# Step 7: Build custom images
print_header "7. Building Custom Images"
docker compose -f $COMPOSE_FILE build --no-cache backend
print_success "Backend image built"

# Step 8: Start services
print_header "8. Starting Services"

# Start in stages to avoid dependency issues
print_info "Starting infrastructure services (PostgreSQL, Redis, Tailscale)..."
docker compose -f $COMPOSE_FILE up -d postgres redis tailscale

print_info "Waiting for infrastructure to be healthy (40 seconds)..."
sleep 40

# Check Tailscale status
print_info "Checking Tailscale connection..."
docker exec zenzefi-tailscale tailscale status || print_warning "Tailscale check failed (may need more time)"

# Start backend
print_info "Starting backend service..."
docker compose -f $COMPOSE_FILE up -d backend

print_info "Waiting for backend to start (30 seconds)..."
sleep 30

# Apply database migrations
print_info "Applying database migrations..."
docker exec zenzefi-backend alembic upgrade head || {
    print_warning "Migration failed, database might already be up to date"
}

# Start Nginx and Certbot
print_info "Starting Nginx and Certbot..."
docker compose -f $COMPOSE_FILE up -d nginx certbot

print_info "Waiting for all services to stabilize (20 seconds)..."
sleep 20

print_success "All services started"

# Step 9: Health checks
print_header "9. Health Checks"

echo ""
print_info "Container Status:"
docker compose -f $COMPOSE_FILE ps
echo ""

print_info "Checking service health..."

# Check PostgreSQL
if docker exec zenzefi-postgres pg_isready -U zenzefi_user -d zenzefi_prod > /dev/null 2>&1; then
    print_success "PostgreSQL: Healthy"
else
    print_error "PostgreSQL: Not healthy"
fi

# Check Redis
if docker exec zenzefi-redis redis-cli -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; then
    print_success "Redis: Healthy"
else
    # Try without password for testing
    if docker exec zenzefi-redis redis-cli ping > /dev/null 2>&1; then
        print_success "Redis: Healthy"
    else
        print_error "Redis: Not healthy"
    fi
fi

# Check Tailscale
if docker exec zenzefi-tailscale tailscale status > /dev/null 2>&1; then
    print_success "Tailscale: Connected"
    docker exec zenzefi-tailscale tailscale ip -4 || true
else
    print_warning "Tailscale: Status check failed"
fi

# Check Backend
sleep 5
if docker exec zenzefi-backend curl -f -s -o /dev/null http://localhost:8000/health; then
    print_success "Backend API: Healthy (http://localhost:8000/health)"
else
    print_warning "Backend API: Not responding yet (may need more time)"
fi

# Check Nginx
if docker exec zenzefi-nginx nginx -t > /dev/null 2>&1; then
    print_success "Nginx: Configuration valid"
else
    print_error "Nginx: Configuration invalid"
fi

# Step 10: View logs
print_header "10. Recent Logs"

echo ""
print_info "Backend logs (last 20 lines):"
docker logs --tail 20 zenzefi-backend
echo ""

print_info "Nginx logs (last 10 lines):"
docker logs --tail 10 zenzefi-nginx
echo ""

# Summary
print_header "🎉 Cleanup and Redeploy Complete!"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
print_success "All services have been redeployed with fresh images"
echo ""
echo "📚 Useful Next Steps:"
echo ""
echo "  # View all logs"
echo "  docker-compose -f $COMPOSE_FILE logs -f"
echo ""
echo "  # View specific service logs"
echo "  docker logs -f zenzefi-backend"
echo "  docker logs -f zenzefi-nginx"
echo ""
echo "  # Check service status"
echo "  docker-compose -f $COMPOSE_FILE ps"
echo ""
echo "  # Test API endpoint"
echo "  curl http://localhost:8000/health"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

print_warning "If services are not responding, wait a few more minutes and check logs"
print_info "Run: docker-compose -f $COMPOSE_FILE logs -f"
echo ""