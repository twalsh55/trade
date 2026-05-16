from __future__ import annotations

import os
from pathlib import Path

from src.adapters.llm.openai_prospect_drafter import OpenAIProspectDrafter, TemplateProspectDrafter
from src.adapters.notifications.composite_email_notifier import CompositeEmailNotifier
from src.adapters.notifications.smtp_email_notifier import SMTPEmailNotifier
from src.adapters.notifications.telegram_digest_notifier import TelegramDigestNotifier
from src.adapters.notifications.telegram_notifier import TelegramNotifier
from src.adapters.operator_briefing.runtime import append_prospect_digest_to_history, run_operator_briefing_job
from src.adapters.prospecting.usage_log import ProspectUsageLog
from src.adapters.social.composite_lead_source import CompositeLeadSource
from src.adapters.social.discord_lead_source import DiscordLeadSource
from src.adapters.social.hacker_news_lead_source import HackerNewsLeadSource
from src.adapters.social.indie_hackers_lead_source import IndieHackersLeadSource
from src.adapters.social.reddit_lead_source import RedditLeadSource
from src.adapters.social.review_site_lead_source import ReviewSiteLeadSource
from src.adapters.social.web_lead_source import WebLeadSource
from src.adapters.social.x_lead_source import XLeadSource
from src.application.ports import EmailDeliveryPort
from src.application.prospecting import (
    DEFAULT_APP_SUMMARY,
    DEFAULT_CRM_DIRECTION_SEARCH_TERMS,
    DEFAULT_CRM_DIRECTION_SUMMARY,
    DEFAULT_PROSPECT_SEARCH_TERMS,
    DailyProspectingConfig,
    ProspectingDigest,
    RunDailyProspectingUseCase,
)
from src.env_utils import get_first_configured_env

DEFAULT_RECIPIENT = "tom.mg.walsh@gmail.com"
APP_OPENAI_ENV_NAMES = ("APP_OPENAI_API_KEY", "OPENAI_API_KEY")


def is_placeholder_openai_key(api_key: str) -> bool:
    normalized = api_key.strip()
    return normalized in {"sk-...", "sk-placeholder", "your-openai-api-key"} or len(normalized) < 20


def build_config_from_env() -> DailyProspectingConfig:
    profile = os.getenv("PROSPECT_PROFILE", "general").strip().lower() or "general"
    search_terms_env = os.getenv("PROSPECT_REDDIT_SEARCH_TERMS", "").strip()
    default_search_terms = DEFAULT_CRM_DIRECTION_SEARCH_TERMS if profile == "crm_direction" else DEFAULT_PROSPECT_SEARCH_TERMS
    default_summary = DEFAULT_CRM_DIRECTION_SUMMARY if profile == "crm_direction" else DEFAULT_APP_SUMMARY
    search_terms = tuple(item.strip() for item in search_terms_env.split(",") if item.strip()) or default_search_terms
    return DailyProspectingConfig(
        recipient_email=os.getenv("PROSPECT_EMAIL_RECIPIENT", DEFAULT_RECIPIENT).strip() or DEFAULT_RECIPIENT,
        profile=profile,
        app_summary=os.getenv("PROSPECT_APP_SUMMARY", default_summary),
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


def build_digest_delivery_from_env() -> EmailDeliveryPort:
    notifiers: list[EmailDeliveryPort] = []
    if has_configured_smtp_delivery():
        notifiers.append(build_email_notifier_from_env())
    if has_configured_telegram_delivery():
        notifiers.append(build_telegram_digest_notifier_from_env())
    if not notifiers:
        raise ValueError("Missing SMTP delivery settings and Telegram delivery fallback is unavailable.")
    if len(notifiers) == 1:
        return notifiers[0]
    return CompositeEmailNotifier(tuple(notifiers))


def build_drafter_from_env() -> OpenAIProspectDrafter | TemplateProspectDrafter:
    api_key = get_app_openai_api_key()
    if not api_key or is_placeholder_openai_key(api_key):
        return TemplateProspectDrafter()
    return OpenAIProspectDrafter(
        api_key=api_key,
        model=os.getenv("PROSPECT_OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4",
        max_output_tokens=parse_positive_int("PROSPECT_OPENAI_MAX_OUTPUT_TOKENS", default=500),
    )


def build_lead_source_from_env() -> CompositeLeadSource:
    user_agent = os.getenv("PROSPECT_PUBLIC_SEARCH_USER_AGENT", "trade-prospecting-bot/0.1").strip() or "trade-prospecting-bot/0.1"
    sources = []
    if os.getenv("PROSPECT_ENABLE_REDDIT_SOURCE", "true").strip().lower() != "false":
        sources.append(RedditLeadSource(user_agent=os.getenv("PROSPECT_REDDIT_USER_AGENT", user_agent)))
    if os.getenv("PROSPECT_ENABLE_HACKER_NEWS_SOURCE", "true").strip().lower() != "false":
        sources.append(HackerNewsLeadSource())
    if os.getenv("PROSPECT_ENABLE_WEB_SOURCE", "true").strip().lower() != "false":
        sources.append(WebLeadSource(user_agent=user_agent))
    if os.getenv("PROSPECT_ENABLE_INDIE_HACKERS_SOURCE", "true").strip().lower() != "false":
        sources.append(IndieHackersLeadSource(user_agent=user_agent))
    if os.getenv("PROSPECT_ENABLE_REVIEW_SOURCE", "true").strip().lower() != "false":
        sources.append(ReviewSiteLeadSource(user_agent=user_agent))
    if os.getenv("PROSPECT_ENABLE_X_SOURCE", "true").strip().lower() != "false":
        sources.append(XLeadSource(user_agent=user_agent))
    if os.getenv("PROSPECT_ENABLE_DISCORD_SOURCE", "true").strip().lower() != "false":
        sources.append(DiscordLeadSource(user_agent=user_agent))
    return CompositeLeadSource(sources=tuple(sources))


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
    digest = use_case.execute(config)
    usage_log = build_usage_log_from_env()
    if usage_log is not None:
        usage_log.append(digest)
    append_prospect_digest_to_history(digest)
    if os.getenv("PROSPECT_SEND_OPERATOR_BRIEFING", "true").strip().lower() != "false":
        run_operator_briefing_job(trigger_label="prospect run")
    return digest


def collect_prospecting_config_errors() -> list[str]:
    errors: list[str] = []
    raw_openai_key = get_app_openai_api_key()
    if raw_openai_key and is_placeholder_openai_key(raw_openai_key):
        errors.append("App OpenAI key looks like a placeholder. Set APP_OPENAI_API_KEY or a real OPENAI_API_KEY.")
    if not has_configured_smtp_delivery() and not has_configured_telegram_delivery():
        errors.append("Missing SMTP delivery settings and Telegram delivery fallback is unavailable")

    for name in (
        "PROSPECT_REDDIT_LIMIT_PER_TERM",
        "PROSPECT_MAX_MATCHES",
        "PROSPECT_MIN_SCORE",
        "PROSPECT_OPENAI_MAX_OUTPUT_TOKENS",
        "PROSPECT_PERIODIC_INTERVAL_MINUTES",
        "PROSPECT_PERIODIC_MAX_RUNS",
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


def build_usage_log_from_env() -> ProspectUsageLog | None:
    enabled = os.getenv("PROSPECT_TRACK_USAGE", "true").strip().lower() != "false"
    if not enabled:
        return None
    path = Path(os.getenv("PROSPECT_USAGE_LOG_FILE", "var/prospect_usage_log.jsonl").strip() or "var/prospect_usage_log.jsonl")
    return ProspectUsageLog(path)


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


def get_app_openai_api_key() -> str:
    return get_first_configured_env(*APP_OPENAI_ENV_NAMES)
