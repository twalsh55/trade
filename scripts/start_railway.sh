#!/bin/sh
set -eu

export PORT="${PORT:-8501}"

.venv/bin/streamlit run main.py \
  --server.address 0.0.0.0 \
  --server.port "${PORT}" \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false
