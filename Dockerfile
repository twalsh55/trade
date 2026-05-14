FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8000

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen

COPY . .

RUN chmod +x /app/scripts/start_railway.sh

EXPOSE 8000

CMD ["/bin/sh", "/app/scripts/start_railway.sh"]
