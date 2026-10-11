#!/usr/bin/env bash
# ==============================================================================
# SAVI Intelligence Platform - Automated VPS Provisioning & Deployment Script
# Supports: Ubuntu 22.04 / 24.04 LTS, Debian 12
# Usage:
#   chmod +x deploy/vps_setup.sh
#   ./deploy/vps_setup.sh
# ==============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "\n${CYAN}==============================================================================${NC}"
echo -e "${CYAN}      SAVI INTELLIGENCE PLATFORM: VPS AUTOMATED PROVISIONING                  ${NC}"
echo -e "${CYAN}==============================================================================${NC}\n"

# 1. Root / Sudo Check
if [[ $EUID -ne 0 ]]; then
   echo -e "${YELLOW}[!] Warning: Not running as root. Prefixing commands with sudo where needed.${NC}"
   SUDO="sudo"
else
   SUDO=""
fi

# 2. Update System Packages
echo -e "${CYAN}[1/6] Updating system packages...${NC}"
$SUDO apt-get update -y
$SUDO apt-get install -y --no-install-recommends \
    curl \
    git \
    ufw \
    ca-certificates \
    gnupg \
    lsb-release

# 3. Install Docker & Docker Compose if missing
if ! command -v docker &> /dev/null; then
    echo -e "${CYAN}[2/6] Installing Docker Engine & Docker Compose Plugin...${NC}"
    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
      $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null

    $SUDO apt-get update -y
    $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    $SUDO systemctl enable docker
    $SUDO systemctl start docker
    echo -e "${GREEN}[✔] Docker successfully installed.${NC}"
else
    echo -e "${GREEN}[✔] Docker is already installed: $(docker --version)${NC}"
fi

# 4. Firewall Configuration (UFW)
echo -e "${CYAN}[3/6] Configuring Firewall (UFW) for Web & SSH...${NC}"
if command -v ufw &> /dev/null; then
    $SUDO ufw allow 22/tcp comment 'SSH' || true
    $SUDO ufw allow 80/tcp comment 'HTTP (Nginx)' || true
    $SUDO ufw allow 443/tcp comment 'HTTPS (Nginx SSL)' || true
    $SUDO ufw --force enable || true
    echo -e "${GREEN}[✔] Firewall rules enabled (ports 22, 80, 443 open).${NC}"
fi

# 5. Environment File Setup
echo -e "${CYAN}[4/6] Verifying environment configuration (.env)...${NC}"
if [[ ! -f ".env" ]]; then
    if [[ -f ".env.vps.example" ]]; then
        cp .env.vps.example .env
        echo -e "${GREEN}[✔] Created .env from .env.vps.example.${NC}"
    else
        echo -e "${YELLOW}[!] Warning: .env not found. Please populate credentials.${NC}"
    fi
else
    echo -e "${GREEN}[✔] Existing .env detected.${NC}"
fi

# Create required Certbot directories for Nginx
mkdir -p deploy/certbot/conf deploy/certbot/www

# 6. Build and Start Docker Compose Stack
echo -e "${CYAN}[5/6] Building and launching SAVI VPS container mesh...${NC}"
$SUDO docker compose -f docker-compose.vps.yml down --remove-orphans || true
$SUDO docker compose -f docker-compose.vps.yml up -d --build

# 7. Pre-flight Verification & Health Check
echo -e "${CYAN}[6/6] Waiting for services to become healthy...${NC}"
sleep 10

RETRIES=15
HEALTH_URL="http://localhost:8000/health"
UP=false

for i in $(seq 1 $RETRIES); do
    if curl -s -f "$HEALTH_URL" > /dev/null 2>&1; then
        UP=true
        break
    fi
    echo -n "."
    sleep 3
done
echo ""

if [ "$UP" = true ]; then
    echo -e "\n${GREEN}==============================================================================${NC}"
    echo -e "${GREEN}   ✔ SAVI PLATFORM IS LIVE AND HEALTHY ON THIS VPS!                           ${NC}"
    echo -e "${GREEN}==============================================================================${NC}"
    echo -e " Backend API:     http://localhost:8000/docs"
    echo -e " Public Reverse:  http://$(curl -s ifconfig.me || echo 'YOUR_VPS_IP')/"
    echo -e " Health Endpoint: http://localhost:8000/health"
    echo -e " Extension URL:   http://$(curl -s ifconfig.me || echo 'YOUR_VPS_IP')"
    echo -e "\n${CYAN}To connect your SAVI Browser Extension:${NC}"
    echo -e "1. Open the browser extension popup."
    echo -e "2. Click ⚙️ and set VPS URL to: http://$(curl -s ifconfig.me || echo 'YOUR_VPS_IP')"
    echo -e "3. Click Save -> The status pill will turn green (VPS Online).\n"
else
    echo -e "${RED}[✘] Health check timed out. Inspect logs with: docker compose -f docker-compose.vps.yml logs -f${NC}"
    exit 1
fi
