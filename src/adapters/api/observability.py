from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

API_LOGGER_NAME = "brivoly.api"
REQUEST_ID_HEADER = "X-Request-ID"


def resolve_log_level(value: str | None) -> int:
    if not value:
        return logging.INFO
    return getattr(logging, value.upper(), logging.INFO)


def configure_api_logger() -> logging.Logger:
    level = resolve_log_level(os.getenv("LOG_LEVEL"))
    logging.basicConfig(level=level, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger().setLevel(level)
    logger = logging.getLogger(API_LOGGER_NAME)
    logger.setLevel(level)
    return logger


def is_absolute_http_url(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return False

    parsed = urlsplit(candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def build_runtime_report() -> dict[str, object]:
    app_base_url = os.getenv("APP_BASE_URL") or os.getenv("PUBLIC_APP_URL") or "http://localhost:3000"
    database_url = os.getenv("DATABASE_URL", "").strip()
    publishable_key = os.getenv("CLERK_PUBLISHABLE_KEY", "").strip()
    secret_key = os.getenv("CLERK_SECRET_KEY", "").strip()
    frontend_api_base_url = os.getenv("BRIVOLY_API_BASE_URL", "").strip() or os.getenv("TRADE_API_BASE_URL", "").strip()
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

    auth_configured = bool(database_url) and bool(publishable_key)
    app_base_url_valid = is_absolute_http_url(app_base_url)
    frontend_api_base_url_valid = is_absolute_http_url(frontend_api_base_url) if frontend_api_base_url else None

    return {
        "status": "ok" if app_base_url_valid and auth_configured else "degraded",
        "checks": {
            "app_base_url": {
                "value": app_base_url,
                "valid": app_base_url_valid,
            },
            "database": {
                "configured": bool(database_url),
            },
            "auth": {
                "publishable_key_configured": bool(publishable_key),
                "secret_key_configured": bool(secret_key),
                "configured": auth_configured,
            },
            "frontend_api_base_url": {
                "configured": bool(frontend_api_base_url),
                "valid": frontend_api_base_url_valid,
            },
            "telegram": {
                "configured": bool(telegram_bot_token) and bool(telegram_chat_id),
            },
            "smtp_email": {
                "configured": bool(smtp_host) and bool(smtp_username),
            },
            "openai": {
                "configured": bool(openai_api_key),
            },
        },
    }
