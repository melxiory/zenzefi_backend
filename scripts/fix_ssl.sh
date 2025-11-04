#!/bin/bash

#
# SSL/HTTPS Fix Script for Zenzefi Backend
# Diagnoses and fixes HTTPS issues after deployment
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
INSTALL_DIR="/opt/zenzefi"
DOMAIN=""

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

# Get domain from .env or user input
if [ -f "$INSTALL_DIR/.env" ]; then
    BACKEND_URL=$(grep BACKEND_URL $INSTALL_DIR/.env | cut -d '=' -f2)
    DOMAIN=$(echo $BACKEND_URL | sed -e 's|https://||' -e 's|http://||')
    print_info "Detected domain from .env: $DOMAIN"
else
    read -p "Enter your domain: " DOMAIN
fi

cd $INSTALL_DIR

print_header "1. Checking Current Status"

# Check Docker Compose
if docker compose version > /dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# Check Nginx container
if docker ps | grep -q zenzefi-nginx; then
    print_success "Nginx container is running"
else
    print_error "Nginx container is not running"
    print_info "Starting Nginx..."
    $DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml up -d nginx
    sleep 5
fi

# Check which config is active
print_info "Checking active Nginx configuration..."
if [ -f "nginx/conf.d/zenzefi.conf" ] && [ ! -f "nginx/conf.d/zenzefi.conf.disabled" ]; then
    print_success "HTTPS configuration is active"
    HTTPS_CONFIG_ACTIVE=true
elif [ -f "nginx/conf.d/zenzefi-init.conf" ] && [ ! -f "nginx/conf.d/zenzefi-init.conf.disabled" ]; then
    print_warning "HTTP-only configuration is active (initial setup mode)"
    HTTPS_CONFIG_ACTIVE=false
else
    print_error "Configuration state is unclear"
    ls -la nginx/conf.d/
    HTTPS_CONFIG_ACTIVE=false
fi

# Check SSL certificate
print_header "2. Checking SSL Certificate"

CERT_PATH="data/certbot/conf/live/$DOMAIN/fullchain.pem"
KEY_PATH="data/certbot/conf/live/$DOMAIN/privkey.pem"

if [ -f "$CERT_PATH" ] && [ -f "$KEY_PATH" ]; then
    print_success "SSL certificate exists"

    # Check certificate expiration
    CERT_EXPIRY=$(openssl x509 -enddate -noout -in "$CERT_PATH" | cut -d= -f2)
    print_info "Certificate expires: $CERT_EXPIRY"

    # Check if certificate is valid
    if openssl x509 -checkend 86400 -noout -in "$CERT_PATH"; then
        print_success "Certificate is valid for at least 24 hours"
    else
        print_warning "Certificate expires soon or is expired"
    fi
else
    print_error "SSL certificate not found at $CERT_PATH"
    print_info "Certificate needs to be obtained"
    CERT_EXISTS=false
fi

# Check port 443
print_header "3. Checking Port 443"

if netstat -tuln 2>/dev/null | grep -q ':443'; then
    print_success "Port 443 is listening"
elif ss -tuln 2>/dev/null | grep -q ':443'; then
    print_success "Port 443 is listening"
else
    print_warning "Port 443 is not listening"
fi

# Check firewall
print_header "4. Checking Firewall"

if ufw status | grep -q 'Status: active'; then
    print_info "UFW is active"
    if ufw status | grep -q '443/tcp.*ALLOW'; then
        print_success "Port 443 is allowed in firewall"
    else
        print_warning "Port 443 is not allowed in firewall"
        print_info "Adding firewall rule..."
        ufw allow 443/tcp
        print_success "Firewall rule added"
    fi
else
    print_info "UFW is not active (may be using different firewall or none)"
fi

# Check Nginx logs
print_header "5. Checking Nginx Logs"

print_info "Recent Nginx error log entries:"
docker logs zenzefi-nginx --tail 20 2>&1 | grep -i error || print_info "No recent errors"

# Diagnose and fix
print_header "6. Diagnosis and Fix"

if [ "$HTTPS_CONFIG_ACTIVE" = false ]; then
    if [ -f "$CERT_PATH" ]; then
        print_warning "Certificate exists but HTTPS config is not active"
        print_info "Switching to HTTPS configuration..."

        # Switch configs
        if [ -f "nginx/conf.d/zenzefi-init.conf" ]; then
            mv nginx/conf.d/zenzefi-init.conf nginx/conf.d/zenzefi-init.conf.disabled
        fi

        if [ -f "nginx/conf.d/zenzefi.conf.disabled" ]; then
            mv nginx/conf.d/zenzefi.conf.disabled nginx/conf.d/zenzefi.conf
        fi

        print_success "Configuration switched to HTTPS"

        # Restart Nginx
        print_info "Restarting Nginx..."
        $DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml restart nginx
        sleep 5
        print_success "Nginx restarted"
    else
        print_warning "Certificate does not exist - need to obtain it first"
        print_info "Options:"
        echo "  1. Obtain certificate using certbot"
        echo "  2. Use existing certificate (if you have one)"
        echo ""
        read -p "Choose option (1/2): " OPTION

        if [ "$OPTION" = "1" ]; then
            print_header "7. Obtaining SSL Certificate"

            # Ensure HTTP-only config is active for ACME challenge
            if [ ! -f "nginx/conf.d/zenzefi-init.conf" ]; then
                if [ -f "nginx/conf.d/zenzefi-init.conf.disabled" ]; then
                    mv nginx/conf.d/zenzefi-init.conf.disabled nginx/conf.d/zenzefi-init.conf
                fi
            fi

            if [ -f "nginx/conf.d/zenzefi.conf" ]; then
                mv nginx/conf.d/zenzefi.conf nginx/conf.d/zenzefi.conf.disabled
            fi

            # Restart Nginx with HTTP-only config
            print_info "Restarting Nginx with HTTP-only config..."
            $DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml restart nginx
            sleep 5

            # Get email for Let's Encrypt
            read -p "Enter your email for Let's Encrypt: " LETSENCRYPT_EMAIL

            # Try webroot method first (preferred)
            print_info "Attempting certificate generation with webroot method..."
            if $DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
                --webroot \
                --webroot-path=/var/www/certbot \
                --email $LETSENCRYPT_EMAIL \
                --agree-tos \
                --no-eff-email \
                -d $DOMAIN; then
                print_success "Certificate obtained successfully with webroot method"
            else
                print_warning "Webroot method failed, trying standalone method..."

                # Stop Nginx for standalone mode
                $DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml stop nginx

                # Try standalone mode
                if $DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml run --rm certbot certonly \
                    --standalone \
                    --email $LETSENCRYPT_EMAIL \
                    --agree-tos \
                    --no-eff-email \
                    -d $DOMAIN; then
                    print_success "Certificate obtained successfully with standalone method"
                else
                    print_error "Failed to obtain certificate"
                    print_info "Please check:"
                    echo "  1. DNS is correctly configured for $DOMAIN"
                    echo "  2. Port 80 and 443 are accessible from internet"
                    echo "  3. No firewall is blocking Let's Encrypt servers"
                    exit 1
                fi
            fi

            # Switch to HTTPS config
            print_info "Switching to HTTPS configuration..."
            mv nginx/conf.d/zenzefi-init.conf nginx/conf.d/zenzefi-init.conf.disabled
            mv nginx/conf.d/zenzefi.conf.disabled nginx/conf.d/zenzefi.conf

            # Start/restart Nginx
            print_info "Restarting Nginx with HTTPS..."
            $DOCKER_COMPOSE -f docker-compose.prod.tailscale.yml up -d nginx
            sleep 5
            print_success "HTTPS configuration activated"
        fi
    fi
else
    print_success "HTTPS configuration is already active"
fi

# Test HTTPS endpoint
print_header "8. Testing HTTPS Connection"

sleep 5

if curl -k -f -s -o /dev/null "https://$DOMAIN/health"; then
    print_success "HTTPS health endpoint responds: https://$DOMAIN/health"
else
    print_warning "HTTPS health endpoint does not respond"
    print_info "This might be normal if DNS is not yet propagated"
fi

if curl -f -s -o /dev/null "http://$DOMAIN/health"; then
    print_success "HTTP health endpoint responds: http://$DOMAIN/health"
    if [ "$HTTPS_CONFIG_ACTIVE" = true ]; then
        print_info "HTTP should redirect to HTTPS"
        HTTP_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://$DOMAIN/health")
        if [ "$HTTP_RESPONSE" = "301" ] || [ "$HTTP_RESPONSE" = "302" ]; then
            print_success "HTTP redirects to HTTPS (status $HTTP_RESPONSE)"
        else
            print_warning "HTTP does not redirect (status $HTTP_RESPONSE)"
        fi
    fi
else
    print_warning "HTTP health endpoint does not respond"
fi

# Summary
print_header "Summary"

echo ""
echo "Current Status:"
echo "  Domain: $DOMAIN"
echo "  SSL Certificate: $([ -f "$CERT_PATH" ] && echo 'Present' || echo 'Missing')"
echo "  HTTPS Config: $([ "$HTTPS_CONFIG_ACTIVE" = true ] && echo 'Active' || echo 'Inactive')"
echo ""

if [ -f "$CERT_PATH" ] && [ "$HTTPS_CONFIG_ACTIVE" = true ]; then
    print_success "HTTPS should be working! 🎉"
    echo ""
    echo "Access your backend at:"
    echo "  https://$DOMAIN"
    echo "  https://$DOMAIN/docs"
    echo ""
else
    print_warning "HTTPS is not fully configured"
    echo ""
fi

print_info "Useful debugging commands:"
echo "  # Check Nginx logs"
echo "  docker logs zenzefi-nginx"
echo ""
echo "  # Check Nginx configuration"
echo "  docker exec zenzefi-nginx nginx -t"
echo ""
echo "  # List active configs"
echo "  ls -la $INSTALL_DIR/nginx/conf.d/"
echo ""
echo "  # Test certificate"
echo "  openssl s_client -connect $DOMAIN:443 -servername $DOMAIN"
echo ""

print_success "SSL fix script completed"