#!/bin/sh
set -eu

export PORT="${PORT:-8501}"

mkdir -p /var/log/nginx /var/lib/nginx /run/nginx
envsubst '${PORT}' < /app/nginx.conf.template > /etc/nginx/nginx.conf

echo "Starting Streamlit on 127.0.0.1:8501 and Nginx proxy on :${PORT}"
.venv/bin/streamlit run main.py --server.address 127.0.0.1 --server.port 8501 --server.headless true &
echo "Streamlit background process started"
exec nginx -g 'daemon off;'
