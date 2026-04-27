FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8501

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx gettext-base ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv \
    && uv sync --frozen

COPY . .

RUN chmod +x /app/scripts/start_railway.sh

EXPOSE 8501

CMD ["/bin/sh", "/app/scripts/start_railway.sh"]
