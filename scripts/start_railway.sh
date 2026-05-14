#!/bin/sh
set -eu

export PORT="${PORT:-8000}"

echo "Sending Telegram startup notification if configured"
.venv/bin/python scripts/send_telegram_startup.py || true

.venv/bin/uvicorn src.adapters.api.app:app \
  --host 0.0.0.0 \
  --port "${PORT}"
