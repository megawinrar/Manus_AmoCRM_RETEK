#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# RETEK amoCRM Microservice — VM Setup Script
# Run on a fresh Ubuntu 22.04/24.04 Yandex Cloud VM
# Usage: sudo bash setup_vm.sh
# ═══════════════════════════════════════════════════════════════════

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  RETEK amoCRM — Настройка сервера"
echo "═══════════════════════════════════════════════════════════"

# 1. System update
echo "[1/6] Обновление системы..."
apt-get update -y && apt-get upgrade -y

# 2. Install Docker
echo "[2/6] Установка Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    usermod -aG docker ubuntu
fi

# 3. Install Docker Compose
echo "[3/6] Установка Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    apt-get install -y docker-compose-plugin
fi

# 4. Install Git
echo "[4/6] Установка Git..."
apt-get install -y git

# 5. Firewall
echo "[5/6] Настройка firewall..."
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable

# 6. Create app directory
echo "[6/6] Создание директорий..."
mkdir -p /opt/retek-amocrm
chown ubuntu:ubuntu /opt/retek-amocrm

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ Сервер готов!"
echo ""
echo "  Следующие шаги:"
echo "  1. cd /opt/retek-amocrm"
echo "  2. git clone https://github.com/megawinrar/Manus_AmoCRM_RETEK.git ."
echo "  3. cp .env.example .env && nano .env  (настроить credentials)"
echo "  4. cd deploy && docker compose up -d --build"
echo "  5. docker compose logs -f  (проверить логи)"
echo "═══════════════════════════════════════════════════════════"
