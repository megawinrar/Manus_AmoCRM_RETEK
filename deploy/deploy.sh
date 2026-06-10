#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# RETEK amoCRM Microservice — Deploy/Update Script
# Run from the project root on the VM
# Usage: bash deploy/deploy.sh
# ═══════════════════════════════════════════════════════════════════

set -e

PROJECT_DIR="/opt/retek-amocrm"
COMPOSE_FILE="deploy/docker-compose.yml"

echo "═══════════════════════════════════════════════════════════"
echo "  RETEK amoCRM — Деплой / Обновление"
echo "═══════════════════════════════════════════════════════════"

cd "$PROJECT_DIR"

# 1. Pull latest code
echo "[1/4] Получение обновлений из GitHub..."
git pull origin main

# 2. Build new image
echo "[2/4] Сборка Docker-образа..."
docker compose -f "$COMPOSE_FILE" build --no-cache app

# 3. Restart services
echo "[3/4] Перезапуск сервисов..."
docker compose -f "$COMPOSE_FILE" down
docker compose -f "$COMPOSE_FILE" up -d

# 4. Check health
echo "[4/4] Проверка здоровья..."
sleep 5
if curl -sf http://localhost:8000/health > /dev/null; then
    echo ""
    echo "  ✅ Деплой успешен! Сервис работает."
    echo ""
    docker compose -f "$COMPOSE_FILE" ps
else
    echo ""
    echo "  ❌ Сервис не отвечает! Проверьте логи:"
    echo "     docker compose -f $COMPOSE_FILE logs app"
    exit 1
fi
