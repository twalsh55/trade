from __future__ import annotations

import os

from src.adapters.llm.openai_prospect_drafter import OpenAIProspectDrafter, TemplateProspectDrafter
from src.adapters.notifications.smtp_email_notifier import SMTPEmailNotifier
from src.adapters.notifications.telegram_digest_notifier import TelegramDigestNotifier
from src.adapters.notifications.telegram_notifier import TelegramNotifier
from src.adapters.social.reddit_lead_source import RedditLeadSource
from src.application.prospecting import (
    DEFAULT_APP_SUMMARY,
    DEFAULT_PROSPECT_SEARCH_TERMS,
    DailyProspectingConfig,
    ProspectingDigest,
    RunDailyProspectingUseCase,
)

DEFAULT_RECIPIENT = "tom.mg.walsh@gmail.com"


def build_config_from_env() -> DailyProspectingConfig:
    search_terms_env = os.getenv("PROSPECT_REDDIT_SEARCH_TERMS", "").strip()
    search_terms = tuple(item.strip() for item in search_terms_env.split(",") if item.strip()) or DEFAULT_PROSPECT_SEARCH_TERMS
    return DailyProspectingConfig(
        recipient_email=os.getenv("PROSPECT_EMAIL_RECIPIENT", DEFAULT_RECIPIENT).strip() or DEFAULT_RECIPIENT,
        app_summary=os.getenv("PROSPECT_APP_SUMMARY", DEFAULT_APP_SUMMARY),
        app_url=os.getenv("APP_BASE_URL", "").strip() or None,
        search_terms=search_terms,
        per_term_limit=parse_positive_int("PROSPECT_REDDIT_LIMIT_PER_TERM", default=8),
        max_matches=parse_positive_int("PROSPECT_MAX_MATCHES", default=5),
        min_score=parse_positive_int("PROSPECT_MIN_SCORE", default=12),
        verbose_audit=os.getenv("PROSPECT_VERBOSE_AUDIT", "false").strip().lower() == "true",
    )


def build_email_notifier_from_env() -> SMTPEmailNotifier:
    host = required_env("SMTP_HOST")
    username = required_env("SMTP_USERNAME")
    password = required_env("SMTP_PASSWORD")
    from_email = required_env("SMTP_FROM_EMAIL")
    port = parse_positive_int("SMTP_PORT", default=587)
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false"
    return SMTPEmailNotifier(
        host=host,
        port=port,
        username=username,
        password=password,
        from_email=from_email,
        use_tls=use_tls,
    )


def build_digest_delivery_from_env() -> SMTPEmailNotifier | TelegramDigestNotifier:
    if has_configured_smtp_delivery():
        return build_email_notifier_from_env()
    return build_telegram_digest_notifier_from_env()


def build_drafter_from_env() -> OpenAIProspectDrafter | TemplateProspectDrafter:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return TemplateProspectDrafter()
    return OpenAIProspectDrafter(
        api_key=api_key,
        model=os.getenv("PROSPECT_OPENAI_MODEL", "gpt-5-nano").strip() or "gpt-5-nano",
        max_output_tokens=parse_positive_int("PROSPECT_OPENAI_MAX_OUTPUT_TOKENS", default=500),
    )


def build_lead_source_from_env() -> RedditLeadSource:
    return RedditLeadSource(user_agent=os.getenv("PROSPECT_REDDIT_USER_AGENT", "trade-prospecting-bot/0.1"))


def build_telegram_digest_notifier_from_env() -> TelegramDigestNotifier:
    bot_token = required_env("TELEGRAM_BOT_TOKEN")
    chat_id = required_env("TELEGRAM_CHAT_ID")
    return TelegramDigestNotifier(TelegramNotifier(bot_token=bot_token, chat_id=chat_id))


def run_prospecting_job() -> ProspectingDigest:
    config = build_config_from_env()
    use_case = RunDailyProspectingUseCase(
        lead_source=build_lead_source_from_env(),
        drafter=build_drafter_from_env(),
        email_delivery=build_digest_delivery_from_env(),
    )
    return use_case.execute(config)


def collect_prospecting_config_errors() -> list[str]:
    errors: list[str] = []
    if not has_configured_smtp_delivery() and not has_configured_telegram_delivery():
        errors.append("Missing SMTP delivery settings and Telegram delivery fallback is unavailable")

    for name in (
        "PROSPECT_REDDIT_LIMIT_PER_TERM",
        "PROSPECT_MAX_MATCHES",
        "PROSPECT_MIN_SCORE",
        "PROSPECT_OPENAI_MAX_OUTPUT_TOKENS",
        "SMTP_PORT",
    ):
        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            continue
        try:
            if int(raw_value) <= 0:
                errors.append(f"{name} must be greater than zero")
        except ValueError:
            errors.append(f"{name} must be an integer")
    return errors


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing {name}. Add it to .env first.")
    return value


def parse_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def has_configured_smtp_delivery() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL")
    )


def has_configured_telegram_delivery() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    )
