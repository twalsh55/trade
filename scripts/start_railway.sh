#!/bin/sh
set -eu

export PORT="${PORT:-8000}"
export LOG_LEVEL="${LOG_LEVEL:-info}"

echo "Sending Telegram startup notification if configured"
.venv/bin/python scripts/send_telegram_startup.py || true

echo "Starting Brivoly API on 0.0.0.0:${PORT}"
echo "APP_BASE_URL configured: $( [ -n "${APP_BASE_URL:-}" ] && echo yes || echo no )"
echo "DATABASE_URL configured: $( [ -n "${DATABASE_URL:-}" ] && echo yes || echo no )"
echo "CLERK_PUBLISHABLE_KEY configured: $( [ -n "${CLERK_PUBLISHABLE_KEY:-}" ] && echo yes || echo no )"

exec .venv/bin/uvicorn src.adapters.api.app:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --log-level "${LOG_LEVEL}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
