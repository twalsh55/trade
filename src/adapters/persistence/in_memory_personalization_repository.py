from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from src.application.account import AlertHistoryEntry, UserDashboardSettings


class InMemoryPersonalizationRepository:
    def __init__(self) -> None:
        self._settings: dict[UUID, UserDashboardSettings] = {}
        self._alerts: dict[UUID, list[AlertHistoryEntry]] = {}

    def get_dashboard_settings(self, user_id: UUID) -> UserDashboardSettings | None:
        settings = self._settings.get(user_id)
        if settings is None:
            return None
        return replace(settings, universe=list(settings.universe))

    def save_dashboard_settings(self, settings: UserDashboardSettings) -> UserDashboardSettings:
        stored = replace(settings, universe=list(settings.universe))
        self._settings[stored.user_id] = stored
        return replace(stored, universe=list(stored.universe))

    def list_alert_history(self, user_id: UUID, limit: int) -> list[AlertHistoryEntry]:
        alerts = self._alerts.get(user_id)
        if alerts is None:
            return [
                AlertHistoryEntry(
                    occurred_at=datetime(2024, 5, 6, 12, 30),
                    category="system",
                    severity="info",
                    title="Alert history not persisted yet",
                    message="This feed currently comes from an in-memory adapter and will reset on restart.",
                )
            ][:limit]
        return [replace(entry) for entry in alerts[:limit]]

    def append_alert_history(self, user_id: UUID, entry: AlertHistoryEntry) -> None:
        entries = self._alerts.setdefault(user_id, [])
        entries.insert(0, replace(entry))
