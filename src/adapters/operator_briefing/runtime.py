from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from src.adapters.notifications.smtp_email_notifier import SMTPEmailNotifier
from src.adapters.persistence.file_operator_insights_repository import FileOperatorInsightsRepository
from src.application.operator_briefing import (
    DEFAULT_OPERATOR_BRIEFING_GOAL,
    DailyOperatorBriefingConfig,
    OperatorBriefing,
    ProductUpdateRecord,
    ProspectRunRecord,
    RunDailyOperatorBriefingUseCase,
    ShortlistedIdeaRecord,
)
from src.application.prospecting import ProspectingDigest

DEFAULT_RECIPIENT = "tom.mg.walsh@gmail.com"


def build_operator_briefing_config_from_env() -> DailyOperatorBriefingConfig:
    default_recipient = os.getenv("PROSPECT_EMAIL_RECIPIENT", DEFAULT_RECIPIENT).strip() or DEFAULT_RECIPIENT
    return DailyOperatorBriefingConfig(
        recipient_email=os.getenv("OPERATOR_BRIEFING_RECIPIENT", default_recipient).strip() or default_recipient,
        lookback_hours=parse_positive_int("OPERATOR_BRIEFING_LOOKBACK_HOURS", default=24),
        goal=os.getenv("OPERATOR_BRIEFING_GOAL", DEFAULT_OPERATOR_BRIEFING_GOAL).strip() or DEFAULT_OPERATOR_BRIEFING_GOAL,
    )


def build_operator_insights_repository_from_env() -> FileOperatorInsightsRepository:
    prospect_runs_path = Path(
        os.getenv("PROSPECT_RUN_LOG_FILE", "var/prospect_run_log.jsonl").strip() or "var/prospect_run_log.jsonl"
    )
    product_updates_path = Path(
        os.getenv("PRODUCT_UPDATE_LOG_FILE", "product_updates.jsonl").strip() or "product_updates.jsonl"
    )
    return FileOperatorInsightsRepository(prospect_runs_path=prospect_runs_path, product_updates_path=product_updates_path)


def run_daily_operator_briefing_job() -> OperatorBriefing:
    return run_operator_briefing_job(trigger_label="daily schedule")


def run_operator_briefing_job(trigger_label: str = "scheduled update") -> OperatorBriefing:
    config = build_operator_briefing_config_from_env()
    repository = build_operator_insights_repository_from_env()
    config = replace(config, trigger_label=trigger_label)
    return RunDailyOperatorBriefingUseCase(
        prospect_history=repository,
        product_updates=repository,
        email_delivery=build_email_notifier_from_env(),
    ).execute(config)


def append_prospect_digest_to_history(digest: ProspectingDigest) -> None:
    repository = build_operator_insights_repository_from_env()
    repository.append_prospect_run(_digest_to_run_record(digest))


def append_product_update_note(update: ProductUpdateRecord) -> None:
    repository = build_operator_insights_repository_from_env()
    repository.append_product_update(update)


def collect_operator_briefing_config_errors() -> list[str]:
    errors: list[str] = []
    for name in ("OPERATOR_BRIEFING_LOOKBACK_HOURS",):
        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            continue
        try:
            if int(raw_value) <= 0:
                errors.append(f"{name} must be greater than zero")
        except ValueError:
            errors.append(f"{name} must be an integer")
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"):
        if not os.getenv(name, "").strip():
            errors.append(f"Missing {name}")
    return errors


def _digest_to_run_record(digest: ProspectingDigest) -> ProspectRunRecord:
    return ProspectRunRecord(
        generated_at=digest.generated_at,
        profile=digest.profile,
        scanned_post_count=digest.scanned_post_count,
        shortlisted_count=digest.shortlisted_count,
        shortlisted_ideas=tuple(
            ShortlistedIdeaRecord(
                source=item.post.source,
                matched_query=item.matched_query,
                score=item.score,
                reasons=item.reasons,
                description=item.suggested_reply,
                observed_signal=_build_observed_signal(item.post.title, item.post.body),
            )
            for item in digest.shortlisted_posts
        ),
        token_usage=digest.token_usage,
    )


def _build_observed_signal(title: str, body: str) -> str:
    text = " ".join(part.strip() for part in (title, body) if part.strip()).strip()
    if len(text) <= 180:
        return text
    return text[:177].rstrip() + "..."


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
