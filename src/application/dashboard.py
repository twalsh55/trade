from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, timedelta
from uuid import UUID

from src.application.account import UserDashboardSettings
from src.domain.models import DEFAULT_UNIVERSE, DashboardConfig

DEFAULT_LOOKBACK_YEARS = 4
DEFAULT_BENCHMARK = "SPY"
DEFAULT_VIX_SYMBOL = "^VIX"
DEFAULT_RISK_PROXY = "HYG"
DEFAULT_SHORT_YIELD_SYMBOL = "^IRX"
DEFAULT_LONG_YIELD_SYMBOL = "^TNX"
DEFAULT_PREFERRED_LANGUAGE = "en"
DEFAULT_PREFERRED_LOCALE = "en-US"
DEFAULT_DATA_RETENTION_DAYS = 365


def build_default_dashboard_settings(user_id: UUID, *, telegram_enabled: bool) -> UserDashboardSettings:
    return UserDashboardSettings(
        user_id=user_id,
        universe=list(DEFAULT_UNIVERSE),
        benchmark=DEFAULT_BENCHMARK,
        vix_symbol=DEFAULT_VIX_SYMBOL,
        risk_proxy=DEFAULT_RISK_PROXY,
        short_yield_symbol=DEFAULT_SHORT_YIELD_SYMBOL,
        long_yield_symbol=DEFAULT_LONG_YIELD_SYMBOL,
        lookback_years=DEFAULT_LOOKBACK_YEARS,
        telegram_enabled=telegram_enabled,
        business_name="",
        business_website="",
        outbound_sender_name="",
        profile_alias="",
        business_logo_data_url="",
        onboarding_profile_deferred=False,
        crm_ai_prompt="Focus on relationship-memory details from messy spreadsheets, files, and images. Prioritize contact name, company, owner, current relationship state, next touch timing, context notes, and the clearest next step. Preserve evidence when uncertain.",
        crm_preferred_import_formats=["csv", "google_sheets", "spreadsheet_screenshot"],
        crm_image_intake_channels=["upload", "magic_link"],
        crm_image_intake_notes="Default to uploads inside Brivoly, then use the signed handoff link when phone capture is easier.",
        preferred_language=DEFAULT_PREFERRED_LANGUAGE,
        preferred_locale=DEFAULT_PREFERRED_LOCALE,
        data_retention_days=DEFAULT_DATA_RETENTION_DAYS,
        allow_ai_processing=True,
        privacy_consent_version="v1",
        privacy_consent_granted_at=None,
    )


def normalize_dashboard_settings(settings: UserDashboardSettings) -> UserDashboardSettings:
    return replace(
        settings,
        universe=_normalize_universe(settings.universe),
        benchmark=_normalize_symbol(settings.benchmark, DEFAULT_BENCHMARK),
        vix_symbol=_normalize_symbol(settings.vix_symbol, DEFAULT_VIX_SYMBOL),
        risk_proxy=_normalize_symbol(settings.risk_proxy, DEFAULT_RISK_PROXY),
        short_yield_symbol=_normalize_symbol(settings.short_yield_symbol, DEFAULT_SHORT_YIELD_SYMBOL),
        long_yield_symbol=_normalize_symbol(settings.long_yield_symbol, DEFAULT_LONG_YIELD_SYMBOL),
        business_name=_normalize_free_text(settings.business_name),
        business_website=_normalize_free_text(settings.business_website),
        outbound_sender_name=_normalize_free_text(settings.outbound_sender_name),
        profile_alias=_normalize_alias(settings.profile_alias),
        business_logo_data_url=settings.business_logo_data_url.strip(),
        onboarding_profile_deferred=bool(settings.onboarding_profile_deferred)
        and not (_normalize_free_text(settings.business_name) and _normalize_free_text(settings.outbound_sender_name)),
        crm_ai_prompt=settings.crm_ai_prompt.strip(),
        crm_preferred_import_formats=_normalize_import_formats(settings.crm_preferred_import_formats),
        crm_image_intake_channels=_normalize_import_formats(settings.crm_image_intake_channels),
        crm_image_intake_notes=_normalize_free_text(settings.crm_image_intake_notes),
        preferred_language=_normalize_language(settings.preferred_language),
        preferred_locale=_normalize_locale(settings.preferred_locale),
        data_retention_days=_normalize_retention_days(settings.data_retention_days),
        allow_ai_processing=bool(settings.allow_ai_processing),
        privacy_consent_version=_normalize_consent_version(settings.privacy_consent_version),
        privacy_consent_granted_at=_normalize_consent_granted_at(settings.privacy_consent_granted_at),
    )


def build_dashboard_config(settings: UserDashboardSettings, *, end_date: date) -> DashboardConfig:
    normalized = normalize_dashboard_settings(settings)
    return DashboardConfig(
        universe=list(normalized.universe),
        benchmark=normalized.benchmark,
        vix_symbol=normalized.vix_symbol,
        risk_proxy=normalized.risk_proxy,
        short_yield_symbol=normalized.short_yield_symbol,
        long_yield_symbol=normalized.long_yield_symbol,
        start_date=end_date - timedelta(days=365 * normalized.lookback_years),
        end_date=end_date,
    )


def _normalize_universe(universe: list[str]) -> list[str]:
    normalized = [_normalize_symbol(item, "") for item in universe]
    cleaned = [item for item in normalized if item]
    return cleaned or list(DEFAULT_UNIVERSE)


def _normalize_symbol(value: str, fallback: str) -> str:
    normalized = value.upper().strip()
    return normalized or fallback


def _normalize_import_formats(formats: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in formats:
        normalized = item.strip().lower().replace(" ", "_")
        if normalized == "telegram":
            normalized = "magic_link"
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned[:12]


def _normalize_free_text(value: str) -> str:
    return value.strip()


def _normalize_alias(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    return cleaned[:80]


def _normalize_language(value: str) -> str:
    cleaned = value.strip().lower().replace("_", "-")
    return cleaned[:16] or DEFAULT_PREFERRED_LANGUAGE


def _normalize_locale(value: str) -> str:
    cleaned = value.strip().replace("_", "-")
    if not cleaned:
        return DEFAULT_PREFERRED_LOCALE
    parts = [part for part in cleaned.split("-") if part]
    if not parts:
        return DEFAULT_PREFERRED_LOCALE
    language = parts[0].lower()
    region = parts[1].upper() if len(parts) > 1 else ""
    normalized = f"{language}-{region}" if region else language
    return normalized[:24]


def _normalize_retention_days(value: int) -> int:
    return max(30, min(3650, int(value or DEFAULT_DATA_RETENTION_DAYS)))


def _normalize_consent_version(value: str) -> str:
    cleaned = value.strip()[:32]
    return cleaned or "v1"


def _normalize_consent_granted_at(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
