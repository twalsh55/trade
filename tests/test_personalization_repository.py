from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from psycopg import OperationalError

from src.adapters.persistence import postgres_personalization_repository as repo_module
from src.adapters.persistence.postgres_personalization_repository import (
    PostgresPersonalizationRepository,
    _row_to_alert_history_entry,
    _row_to_dashboard_settings,
)
from src.adapters.persistence.runtime import build_personalization_repository
from src.application.account import AlertHistoryEntry, UserDashboardSettings


def make_settings() -> UserDashboardSettings:
    return UserDashboardSettings(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        universe=["SPY", "QQQ"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        lookback_years=4,
        telegram_enabled=True,
    )


def make_alert() -> AlertHistoryEntry:
    return AlertHistoryEntry(
        occurred_at=datetime(2024, 5, 6, 12, 30, tzinfo=UTC),
        category="settings",
        severity="info",
        title="Updated",
        message="Dashboard settings changed.",
    )


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None) -> None:
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.executed: list[tuple[str, dict[str, object] | None]] = []

    def execute(self, query: str, params: dict[str, object] | None = None) -> None:
        self.executed.append((query, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_row_mappers_convert_database_shapes() -> None:
    settings_row = {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "universe": ["SPY", "QQQ"],
        "benchmark": "SPY",
        "vix_symbol": "^VIX",
        "risk_proxy": "HYG",
        "short_yield_symbol": "^IRX",
        "long_yield_symbol": "^TNX",
        "lookback_years": 4,
        "telegram_enabled": True,
    }
    alert_row = {
        "occurred_at": "2024-05-06T12:30:00+00:00",
        "category": "settings",
        "severity": "info",
        "title": "Updated",
        "message": "Saved.",
    }

    settings = _row_to_dashboard_settings(settings_row)
    alert = _row_to_alert_history_entry(alert_row)

    assert settings.user_id == UUID("11111111-1111-1111-1111-111111111111")
    assert settings.universe == ["SPY", "QQQ"]
    assert alert.title == "Updated"
    assert alert.occurred_at == datetime(2024, 5, 6, 12, 30, tzinfo=UTC)


def test_postgres_personalization_repository_ensure_schema(monkeypatch) -> None:
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: connection)

    repository = PostgresPersonalizationRepository("postgres://example")
    repository.ensure_schema()

    assert len(cursor.executed) == 3
    assert "user_dashboard_settings" in cursor.executed[0][0]
    assert "alert_history" in cursor.executed[1][0]
    assert connection.committed is True


def test_postgres_personalization_repository_get_and_save_settings(monkeypatch) -> None:
    missing_connection = FakeConnection(FakeCursor(fetchone_result=None))
    existing_connection = FakeConnection(
        FakeCursor(
            fetchone_result={
                "user_id": UUID("11111111-1111-1111-1111-111111111111"),
                "universe": ["SPY", "QQQ"],
                "benchmark": "SPY",
                "vix_symbol": "^VIX",
                "risk_proxy": "HYG",
                "short_yield_symbol": "^IRX",
                "long_yield_symbol": "^TNX",
                "lookback_years": 4,
                "telegram_enabled": True,
            }
        )
    )
    saved_row = {
        "user_id": UUID("11111111-1111-1111-1111-111111111111"),
        "universe": ["SPY", "QQQ"],
        "benchmark": "SPY",
        "vix_symbol": "^VIX",
        "risk_proxy": "HYG",
        "short_yield_symbol": "^IRX",
        "long_yield_symbol": "^TNX",
        "lookback_years": 4,
        "telegram_enabled": True,
    }
    saved_connection = FakeConnection(FakeCursor(fetchone_result=saved_row))
    calls = [missing_connection, existing_connection, saved_connection]
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: calls.pop(0))

    repository = PostgresPersonalizationRepository("postgres://example")
    assert repository.get_dashboard_settings(make_settings().user_id) is None
    assert repository.get_dashboard_settings(make_settings().user_id) == make_settings()

    saved = repository.save_dashboard_settings(make_settings())
    assert saved == make_settings()
    assert saved_connection.committed is True
    assert saved_connection.cursor_instance.executed[0][1]["universe"] == ["SPY", "QQQ"]


def test_postgres_personalization_repository_save_settings_requires_returned_row(monkeypatch) -> None:
    connection = FakeConnection(FakeCursor(fetchone_result=None))
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: connection)

    repository = PostgresPersonalizationRepository("postgres://example")

    with pytest.raises(RuntimeError, match="Settings upsert did not return a row."):
        repository.save_dashboard_settings(make_settings())


def test_postgres_personalization_repository_alert_history_methods(monkeypatch) -> None:
    rows = [
        {
            "occurred_at": datetime(2024, 5, 6, 12, 30, tzinfo=UTC),
            "category": "settings",
            "severity": "info",
            "title": "Updated",
            "message": "Saved.",
        }
    ]
    list_connection = FakeConnection(FakeCursor(fetchall_result=rows))
    append_connection = FakeConnection(FakeCursor())
    calls = [list_connection, append_connection]
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: calls.pop(0))

    repository = PostgresPersonalizationRepository("postgres://example")
    entries = repository.list_alert_history(make_settings().user_id, limit=5)
    assert entries[0].message == "Saved."

    repository.append_alert_history(make_settings().user_id, make_alert())
    assert append_connection.committed is True
    assert append_connection.cursor_instance.executed[0][1]["title"] == "Updated"


def test_build_personalization_repository_uses_in_memory_without_database(monkeypatch) -> None:
    build_personalization_repository.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    repository = build_personalization_repository()

    assert repository.__class__.__name__ == "InMemoryPersonalizationRepository"


def test_build_personalization_repository_builds_postgres_repo(monkeypatch) -> None:
    build_personalization_repository.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    captured: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, database_url: str) -> None:
            captured["database_url"] = database_url

        def ensure_schema(self) -> None:
            captured["ensure_schema"] = True

    monkeypatch.setattr("src.adapters.persistence.runtime.PostgresPersonalizationRepository", FakeRepository)

    repository = build_personalization_repository()

    assert repository.__class__.__name__ == "FakeRepository"
    assert captured["database_url"] == "postgres://example"
    assert captured["ensure_schema"] is True


def test_build_personalization_repository_surfaces_connectivity_errors(monkeypatch) -> None:
    build_personalization_repository.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgres://example")

    class FakeRepository:
        def __init__(self, database_url: str) -> None:
            self.database_url = database_url

        def ensure_schema(self) -> None:
            raise OperationalError("dns failed")

    monkeypatch.setattr("src.adapters.persistence.runtime.PostgresPersonalizationRepository", FakeRepository)

    with pytest.raises(RuntimeError, match="Personalization database is unavailable"):
        build_personalization_repository()
