#!/usr/bin/env bash
# One-shot: generate /opt/warmbly/.env (idempotent, keeps existing secrets).
set -euo pipefail
ENV=/opt/warmbly/.env
touch "$ENV"
chmod 600 "$ENV"
ensure() { grep -q "^$1=" "$ENV" || echo "$1=$2" >> "$ENV"; }
ensure APP_ENV prod
ensure DEPLOYMENT_MODE self_hosted
ensure AUTH_SECRET "$(openssl rand -hex 32)"
ensure KMS_LOCAL_MASTER_KEY "$(openssl rand -base64 32)"
ensure CREDENTIALS_ENCRYPTION_KEY "$(openssl rand -hex 32)"
ensure INTERNAL_API_TOKEN "$(openssl rand -hex 32)"
ensure SECRET_KEY_BASE "$(openssl rand -hex 48)"
ensure BILLING_PROVIDER none
ensure WARMBLY_TAG prod
ensure TRACKING_PORT 3200
ensure FORMS_PORT 8094
ensure TRACKING_DOMAIN warmbly-track.slideinventure.com
ensure APP_URL https://warmbly.slideinventure.com
ensure API_PUBLIC_URL https://warmbly-api.slideinventure.com
ensure CORS_ALLOW_ORIGINS https://warmbly.slideinventure.com
ensure WEBSOCKET_URL wss://warmbly-api.slideinventure.com/socket/websocket
ensure MAIL_TLS_INSECURE true
echo "ENV_OK $(grep -c . "$ENV") keys"
