#!/bin/bash
# Скрипт создаёт .env для production на VM
# Запускать: bash /opt/Manus_AmoCRM_RETEK/deploy/setup_env.sh

set -e
ENV_FILE="/opt/Manus_AmoCRM_RETEK/.env"

cp /opt/Manus_AmoCRM_RETEK/.env.example "$ENV_FILE" 2>/dev/null || touch "$ENV_FILE"

cat > "$ENV_FILE" << 'ENVEOF'
# ─── amoCRM ──────────────────────────────────────────────────────
AMO_DOMAIN=tokutools
AMO_CLIENT_ID=f4b1d4e0-7b6f-4b6e-9c
