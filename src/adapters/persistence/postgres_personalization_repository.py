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
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
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
                        telegram_enabled
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
                        telegram_enabled
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
    )


def _row_to_alert_history_entry(row: dict[str, object]) -> AlertHistoryEntry:
    return AlertHistoryEntry(
        occurred_at=row["occurred_at"] if isinstance(row["occurred_at"], datetime) else datetime.fromisoformat(str(row["occurred_at"])),
        category=str(row["category"]),
        severity=str(row["severity"]),
        title=str(row["title"]),
        message=str(row["message"]),
    )
