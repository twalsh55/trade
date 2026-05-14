from __future__ import annotations

from datetime import UTC, datetime

from src.adapters.prospecting.runtime import (
    build_config_from_env,
    build_drafter_from_env,
    build_digest_delivery_from_env,
    build_email_notifier_from_env,
    build_lead_source_from_env,
    build_telegram_digest_notifier_from_env,
    collect_prospecting_config_errors,
    has_configured_smtp_delivery,
    has_configured_telegram_delivery,
    parse_positive_int,
    required_env,
    run_prospecting_job,
)


def test_build_config_from_env_uses_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PROSPECT_REDDIT_SEARCH_TERMS", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)

    config = build_config_from_env()

    assert config.recipient_email == "tom.mg.walsh@gmail.com"
    assert config.search_terms
    assert config.app_url is None


def test_build_email_notifier_requires_env(monkeypatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)

    try:
        build_email_notifier_from_env()
    except ValueError as exc:
        assert str(exc) == "Missing SMTP_HOST. Add it to .env first."
    else:
        raise AssertionError("Expected ValueError")


def test_build_email_notifier_from_env_builds_configured_notifier(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USE_TLS", "false")

    notifier = build_email_notifier_from_env()

    assert notifier.host == "smtp.example.com"
    assert notifier.port == 2525
    assert notifier.username == "mailer"
    assert notifier.from_email == "alerts@example.com"
    assert notifier.use_tls is False


def test_build_drafter_from_env_uses_template_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert build_drafter_from_env().__class__.__name__ == "TemplateProspectDrafter"


def test_build_drafter_from_env_uses_openai_when_api_key_present(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert build_drafter_from_env().__class__.__name__ == "OpenAIProspectDrafter"


def test_build_lead_source_from_env_uses_custom_user_agent(monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_REDDIT_USER_AGENT", "custom-agent")
    source = build_lead_source_from_env()
    assert source.user_agent == "custom-agent"


def test_build_telegram_digest_notifier_from_env_requires_telegram(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    try:
        build_telegram_digest_notifier_from_env()
    except ValueError as exc:
        assert str(exc) == "Missing TELEGRAM_BOT_TOKEN. Add it to .env first."
    else:
        raise AssertionError("Expected ValueError")


def test_build_digest_delivery_from_env_prefers_smtp_but_falls_back_to_telegram(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    fallback = build_digest_delivery_from_env()
    assert fallback.__class__.__name__ == "TelegramDigestNotifier"

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    smtp = build_digest_delivery_from_env()
    assert smtp.__class__.__name__ == "SMTPEmailNotifier"


def test_collect_prospecting_config_errors_reports_missing_and_invalid_fields(monkeypatch) -> None:
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PROSPECT_MAX_MATCHES", "abc")
    monkeypatch.setenv("SMTP_PORT", "0")

    errors = collect_prospecting_config_errors()

    assert "Missing SMTP delivery settings and Telegram delivery fallback is unavailable" in errors
    assert "PROSPECT_MAX_MATCHES must be an integer" in errors
    assert "SMTP_PORT must be greater than zero" in errors


def test_collect_prospecting_config_errors_allows_telegram_fallback(monkeypatch) -> None:
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    assert collect_prospecting_config_errors() == []


def test_required_env_and_parse_positive_int(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("PROSPECT_MAX_MATCHES", "4")

    assert required_env("SMTP_HOST") == "smtp.example.com"
    assert parse_positive_int("PROSPECT_MAX_MATCHES", default=3) == 4


def test_delivery_configuration_helpers(monkeypatch) -> None:
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    assert has_configured_smtp_delivery() is False
    assert has_configured_telegram_delivery() is False

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    assert has_configured_telegram_delivery() is True

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    assert has_configured_smtp_delivery() is True


def test_parse_positive_int_raises_for_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_MAX_MATCHES", "0")

    try:
        parse_positive_int("PROSPECT_MAX_MATCHES", default=3)
    except ValueError as exc:
        assert str(exc) == "PROSPECT_MAX_MATCHES must be greater than zero."
    else:
        raise AssertionError("Expected ValueError")

    monkeypatch.setenv("PROSPECT_MAX_MATCHES", "abc")
    try:
        parse_positive_int("PROSPECT_MAX_MATCHES", default=3)
    except ValueError as exc:
        assert str(exc) == "PROSPECT_MAX_MATCHES must be an integer."
    else:
        raise AssertionError("Expected ValueError")


def test_run_prospecting_job_builds_and_executes_use_case(monkeypatch) -> None:
    config = object()
    lead_source = object()
    drafter = object()
    email_delivery = object()
    digest = type(
        "Digest",
        (),
        {
            "generated_at": datetime(2026, 5, 14, tzinfo=UTC),
            "scanned_post_count": 3,
            "shortlisted_count": 1,
            "shortlisted_posts": (),
        },
    )()
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_config_from_env", lambda: config)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_lead_source_from_env", lambda: lead_source)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_drafter_from_env", lambda: drafter)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_digest_delivery_from_env", lambda: email_delivery)

    class FakeUseCase:
        def __init__(self, lead_source, drafter, email_delivery) -> None:  # type: ignore[no-untyped-def]
            self.lead_source = lead_source
            self.drafter = drafter
            self.email_delivery = email_delivery

        def execute(self, passed_config):  # type: ignore[no-untyped-def]
            assert passed_config is config
            assert self.lead_source is lead_source
            assert self.drafter is drafter
            assert self.email_delivery is email_delivery
            return digest

    monkeypatch.setattr("src.adapters.prospecting.runtime.RunDailyProspectingUseCase", FakeUseCase)

    assert run_prospecting_job() is digest
