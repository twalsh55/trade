from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg import connect
from psycopg.rows import dict_row

from src.adapters.persistence.postgres_user_repository import _parse_uuid
from src.application.account import AlertHistoryEntry, UserDashboardSettings


class PostgresPersonalizationRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def ensure_schema(self) -> None:
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_dashboard_settings (
                        user_id UUID PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
                        universe TEXT[] NOT NULL,
                        benchmark TEXT NOT NULL,
                        vix_symbol TEXT NOT NULL,
                        risk_proxy TEXT NOT NULL,
                        short_yield_symbol TEXT NOT NULL,
                        long_yield_symbol TEXT NOT NULL,
                        lookback_years INTEGER NOT NULL CHECK (lookback_years BETWEEN 1 AND 10),
                        telegram_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        business_name TEXT NOT NULL DEFAULT '',
                        business_website TEXT NOT NULL DEFAULT '',
                        outbound_sender_name TEXT NOT NULL DEFAULT '',
                        profile_alias TEXT NOT NULL DEFAULT '',
                        business_logo_data_url TEXT NOT NULL DEFAULT '',
                        onboarding_profile_deferred BOOLEAN NOT NULL DEFAULT FALSE,
                        crm_ai_prompt TEXT NOT NULL DEFAULT '',
                        crm_preferred_import_formats TEXT[] NOT NULL DEFAULT '{}',
                        crm_image_intake_channels TEXT[] NOT NULL DEFAULT '{}',
                        crm_image_intake_notes TEXT NOT NULL DEFAULT '',
                        preferred_language TEXT NOT NULL DEFAULT 'en',
                        preferred_locale TEXT NOT NULL DEFAULT 'en-US',
                        data_retention_days INTEGER NOT NULL DEFAULT 365,
                        allow_ai_processing BOOLEAN NOT NULL DEFAULT TRUE,
                        privacy_consent_version TEXT NOT NULL DEFAULT 'v1',
                        privacy_consent_granted_at TIMESTAMPTZ NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS business_name TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS business_website TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS outbound_sender_name TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS profile_alias TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS business_logo_data_url TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS onboarding_profile_deferred BOOLEAN NOT NULL DEFAULT FALSE
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS crm_ai_prompt TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS crm_preferred_import_formats TEXT[] NOT NULL DEFAULT '{}'
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS crm_image_intake_channels TEXT[] NOT NULL DEFAULT '{}'
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS crm_image_intake_notes TEXT NOT NULL DEFAULT ''
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS preferred_language TEXT NOT NULL DEFAULT 'en'
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS preferred_locale TEXT NOT NULL DEFAULT 'en-US'
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS data_retention_days INTEGER NOT NULL DEFAULT 365
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS allow_ai_processing BOOLEAN NOT NULL DEFAULT TRUE
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS privacy_consent_version TEXT NOT NULL DEFAULT 'v1'
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE user_dashboard_settings
                    ADD COLUMN IF NOT EXISTS privacy_consent_granted_at TIMESTAMPTZ NULL
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alert_history (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
                        occurred_at TIMESTAMPTZ NOT NULL,
                        category TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS alert_history_user_occurred_at_idx
                    ON alert_history (user_id, occurred_at DESC)
                    """
                )
            connection.commit()

    def get_dashboard_settings(self, user_id: UUID) -> UserDashboardSettings | None:
        with connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        user_id,
                        universe,
                        benchmark,
                        vix_symbol,
                        risk_proxy,
                        short_yield_symbol,
                        long_yield_symbol,
                        lookback_years,
                        telegram_enabled,
                        business_name,
                        business_website,
                        outbound_sender_name,
                        profile_alias,
                        business_logo_data_url,
                        onboarding_profile_deferred,
                        crm_ai_prompt,
                        crm_preferred_import_formats,
                        crm_image_intake_channels,
                        crm_image_intake_notes,
                        preferred_language,
                        preferred_locale,
                        data_retention_days,
                        allow_ai_processing,
                        privacy_consent_version,
                        privacy_consent_granted_at
                    FROM user_dashboard_settings
                    WHERE user_id = %(user_id)s
                    """,
                    {"user_id": user_id},
                )
                row = cursor.fetchone()

        if row is None:
            return None
        return _row_to_dashboard_settings(row)

    def save_dashboard_settings(self, settings: UserDashboardSettings) -> UserDashboardSettings:
        with connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_dashboard_settings (
                        user_id,
                        universe,
                        benchmark,
                        vix_symbol,
                        risk_proxy,
                        short_yield_symbol,
                        long_yield_symbol,
                        lookback_years,
                        telegram_enabled,
                        business_name,
                        business_website,
                        outbound_sender_name,
                        profile_alias,
                        business_logo_data_url,
                        onboarding_profile_deferred,
                        crm_ai_prompt,
                        crm_preferred_import_formats,
                        crm_image_intake_channels,
                        crm_image_intake_notes,
                        preferred_language,
                        preferred_locale,
                        data_retention_days,
                        allow_ai_processing,
                        privacy_consent_version,
                        privacy_consent_granted_at,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %(user_id)s,
                        %(universe)s,
                        %(benchmark)s,
                        %(vix_symbol)s,
                        %(risk_proxy)s,
                        %(short_yield_symbol)s,
                        %(long_yield_symbol)s,
                        %(lookback_years)s,
                        %(telegram_enabled)s,
                        %(business_name)s,
                        %(business_website)s,
                        %(outbound_sender_name)s,
                        %(profile_alias)s,
                        %(business_logo_data_url)s,
                        %(onboarding_profile_deferred)s,
                        %(crm_ai_prompt)s,
                        %(crm_preferred_import_formats)s,
                        %(crm_image_intake_channels)s,
                        %(crm_image_intake_notes)s,
                        %(preferred_language)s,
                        %(preferred_locale)s,
                        %(data_retention_days)s,
                        %(allow_ai_processing)s,
                        %(privacy_consent_version)s,
                        %(privacy_consent_granted_at)s,
                        NOW(),
                        NOW()
                    )
                    ON CONFLICT (user_id) DO UPDATE
                    SET
                        universe = EXCLUDED.universe,
                        benchmark = EXCLUDED.benchmark,
                        vix_symbol = EXCLUDED.vix_symbol,
                        risk_proxy = EXCLUDED.risk_proxy,
                        short_yield_symbol = EXCLUDED.short_yield_symbol,
                        long_yield_symbol = EXCLUDED.long_yield_symbol,
                        lookback_years = EXCLUDED.lookback_years,
                        telegram_enabled = EXCLUDED.telegram_enabled,
                        business_name = EXCLUDED.business_name,
                        business_website = EXCLUDED.business_website,
                        outbound_sender_name = EXCLUDED.outbound_sender_name,
                        profile_alias = EXCLUDED.profile_alias,
                        business_logo_data_url = EXCLUDED.business_logo_data_url,
                        onboarding_profile_deferred = EXCLUDED.onboarding_profile_deferred,
                        crm_ai_prompt = EXCLUDED.crm_ai_prompt,
                        crm_preferred_import_formats = EXCLUDED.crm_preferred_import_formats,
                        crm_image_intake_channels = EXCLUDED.crm_image_intake_channels,
                        crm_image_intake_notes = EXCLUDED.crm_image_intake_notes,
                        preferred_language = EXCLUDED.preferred_language,
                        preferred_locale = EXCLUDED.preferred_locale,
                        data_retention_days = EXCLUDED.data_retention_days,
                        allow_ai_processing = EXCLUDED.allow_ai_processing,
                        privacy_consent_version = EXCLUDED.privacy_consent_version,
                        privacy_consent_granted_at = EXCLUDED.privacy_consent_granted_at,
                        updated_at = NOW()
                    RETURNING
                        user_id,
                        universe,
                        benchmark,
                        vix_symbol,
                        risk_proxy,
                        short_yield_symbol,
                        long_yield_symbol,
                        lookback_years,
                        telegram_enabled,
                        business_name,
                        business_website,
                        outbound_sender_name,
                        profile_alias,
                        business_logo_data_url,
                        onboarding_profile_deferred,
                        crm_ai_prompt,
                        crm_preferred_import_formats,
                        crm_image_intake_channels,
                        crm_image_intake_notes,
                        preferred_language,
                        preferred_locale,
                        data_retention_days,
                        allow_ai_processing,
                        privacy_consent_version,
                        privacy_consent_granted_at
                    """,
                    {
                        "user_id": settings.user_id,
                        "universe": list(settings.universe),
                        "benchmark": settings.benchmark,
                        "vix_symbol": settings.vix_symbol,
                        "risk_proxy": settings.risk_proxy,
                        "short_yield_symbol": settings.short_yield_symbol,
                        "long_yield_symbol": settings.long_yield_symbol,
                        "lookback_years": settings.lookback_years,
                        "telegram_enabled": settings.telegram_enabled,
                        "business_name": settings.business_name,
                        "business_website": settings.business_website,
                        "outbound_sender_name": settings.outbound_sender_name,
                        "profile_alias": settings.profile_alias,
                        "business_logo_data_url": settings.business_logo_data_url,
                        "onboarding_profile_deferred": settings.onboarding_profile_deferred,
                        "crm_ai_prompt": settings.crm_ai_prompt,
                        "crm_preferred_import_formats": list(settings.crm_preferred_import_formats),
                        "crm_image_intake_channels": list(settings.crm_image_intake_channels),
                        "crm_image_intake_notes": settings.crm_image_intake_notes,
                        "preferred_language": settings.preferred_language,
                        "preferred_locale": settings.preferred_locale,
                        "data_retention_days": settings.data_retention_days,
                        "allow_ai_processing": settings.allow_ai_processing,
                        "privacy_consent_version": settings.privacy_consent_version,
                        "privacy_consent_granted_at": settings.privacy_consent_granted_at,
                    },
                )
                row = cursor.fetchone()
            connection.commit()

        if row is None:
            raise RuntimeError("Settings upsert did not return a row.")
        return _row_to_dashboard_settings(row)

    def list_alert_history(self, user_id: UUID, limit: int) -> list[AlertHistoryEntry]:
        with connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        occurred_at,
                        category,
                        severity,
                        title,
                        message
                    FROM alert_history
                    WHERE user_id = %(user_id)s
                    ORDER BY occurred_at DESC
                    LIMIT %(limit)s
                    """,
                    {
                        "user_id": user_id,
                        "limit": limit,
                    },
                )
                rows = cursor.fetchall()

        return [_row_to_alert_history_entry(row) for row in rows]

    def append_alert_history(self, user_id: UUID, entry: AlertHistoryEntry) -> None:
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO alert_history (
                        user_id,
                        occurred_at,
                        category,
                        severity,
                        title,
                        message
                    )
                    VALUES (
                        %(user_id)s,
                        %(occurred_at)s,
                        %(category)s,
                        %(severity)s,
                        %(title)s,
                        %(message)s
                    )
                    """,
                    {
                        "user_id": user_id,
                        "occurred_at": entry.occurred_at,
                        "category": entry.category,
                        "severity": entry.severity,
                        "title": entry.title,
                        "message": entry.message,
                    },
                )
            connection.commit()


def _row_to_dashboard_settings(row: dict[str, object]) -> UserDashboardSettings:
    return UserDashboardSettings(
        user_id=_parse_uuid(row["user_id"]),
        universe=[str(item) for item in row["universe"]] if isinstance(row["universe"], list) else [],
        benchmark=str(row["benchmark"]),
        vix_symbol=str(row["vix_symbol"]),
        risk_proxy=str(row["risk_proxy"]),
        short_yield_symbol=str(row["short_yield_symbol"]),
        long_yield_symbol=str(row["long_yield_symbol"]),
        lookback_years=int(row["lookback_years"]),
        telegram_enabled=bool(row["telegram_enabled"]),
        business_name=str(row.get("business_name") or ""),
        business_website=str(row.get("business_website") or ""),
        outbound_sender_name=str(row.get("outbound_sender_name") or ""),
        profile_alias=str(row.get("profile_alias") or ""),
        business_logo_data_url=str(row.get("business_logo_data_url") or ""),
        onboarding_profile_deferred=bool(row.get("onboarding_profile_deferred")),
        crm_ai_prompt=str(row.get("crm_ai_prompt") or ""),
        crm_preferred_import_formats=[
            str(item) for item in row.get("crm_preferred_import_formats", [])
        ] if isinstance(row.get("crm_preferred_import_formats"), list) else [],
        crm_image_intake_channels=[
            str(item) for item in row.get("crm_image_intake_channels", [])
        ] if isinstance(row.get("crm_image_intake_channels"), list) else [],
        crm_image_intake_notes=str(row.get("crm_image_intake_notes") or ""),
        preferred_language=str(row.get("preferred_language") or "en"),
        preferred_locale=str(row.get("preferred_locale") or "en-US"),
        data_retention_days=int(row.get("data_retention_days") or 365),
        allow_ai_processing=bool(row.get("allow_ai_processing", True)),
        privacy_consent_version=str(row.get("privacy_consent_version") or "v1"),
        privacy_consent_granted_at=row.get("privacy_consent_granted_at") if isinstance(row.get("privacy_consent_granted_at"), datetime) else datetime.fromisoformat(str(row["privacy_consent_granted_at"])) if row.get("privacy_consent_granted_at") else None,
    )


def _row_to_alert_history_entry(row: dict[str, object]) -> AlertHistoryEntry:
    return AlertHistoryEntry(
        occurred_at=row["occurred_at"] if isinstance(row["occurred_at"], datetime) else datetime.fromisoformat(str(row["occurred_at"])),
        category=str(row["category"]),
        severity=str(row["severity"]),
        title=str(row["title"]),
        message=str(row["message"]),
    )
