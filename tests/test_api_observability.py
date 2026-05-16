from __future__ import annotations

import logging

from src.adapters.api.observability import build_runtime_report, is_absolute_http_url, resolve_log_level


def test_resolve_log_level_and_url_validation_helpers() -> None:
    assert resolve_log_level(None) == logging.INFO
    assert resolve_log_level("debug") == logging.DEBUG
    assert resolve_log_level("not-a-level") == logging.INFO

    assert is_absolute_http_url("https://example.com")
    assert is_absolute_http_url("http://localhost:3000")
    assert is_absolute_http_url("  https://example.com/path  ")
    assert not is_absolute_http_url("")
    assert not is_absolute_http_url("/dashboard")
    assert not is_absolute_http_url("ftp://example.com")


def test_build_runtime_report_defaults_to_degraded_without_auth_config(monkeypatch) -> None:
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    monkeypatch.delenv("BRIVOLY_API_BASE_URL", raising=False)
    monkeypatch.delenv("TRADE_API_BASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    report = build_runtime_report()

    assert report["status"] == "degraded"
    checks = report["checks"]
    assert checks["app_base_url"] == {"value": "http://localhost:3000", "valid": True}
    assert checks["database"] == {"configured": False}
    assert checks["auth"] == {
        "publishable_key_configured": False,
        "secret_key_configured": False,
        "configured": False,
    }
    assert checks["frontend_api_base_url"] == {"configured": False, "valid": None}
    assert checks["telegram"] == {"configured": False}
    assert checks["smtp_email"] == {"configured": False}
    assert checks["openai"] == {"configured": False}


def test_build_runtime_report_marks_configured_runtime_as_ok(monkeypatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://app.brivoly.example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/trade")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_value")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_value")
    monkeypatch.setenv("BRIVOLY_API_BASE_URL", "https://api.brivoly.example.com")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("APP_OPENAI_API_KEY", "sk-test")

    report = build_runtime_report()

    assert report["status"] == "ok"
    checks = report["checks"]
    assert checks["app_base_url"] == {"value": "https://app.brivoly.example.com", "valid": True}
    assert checks["database"] == {"configured": True}
    assert checks["auth"] == {
        "publishable_key_configured": True,
        "secret_key_configured": True,
        "configured": True,
    }
    assert checks["frontend_api_base_url"] == {"configured": True, "valid": True}
    assert checks["telegram"] == {"configured": True}
    assert checks["smtp_email"] == {"configured": True}
    assert checks["openai"] == {"configured": True}
