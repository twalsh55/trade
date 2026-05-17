from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable
from uuid import UUID

from src.application.ports import AlertHistoryPort, UserDashboardSettingsPort
from src.domain.auth import User


@dataclass(frozen=True)
class UserDashboardSettings:
    user_id: UUID
    universe: list[str]
    benchmark: str
    vix_symbol: str
    risk_proxy: str
    short_yield_symbol: str
    long_yield_symbol: str
    lookback_years: int
    telegram_enabled: bool
    business_name: str
    business_website: str
    outbound_sender_name: str
    profile_alias: str
    business_logo_data_url: str
    onboarding_profile_deferred: bool
    crm_ai_prompt: str
    crm_preferred_import_formats: list[str]
    crm_image_intake_channels: list[str]
    crm_image_intake_notes: str
    preferred_language: str
    preferred_locale: str
    data_retention_days: int
    allow_ai_processing: bool
    privacy_consent_version: str
    privacy_consent_granted_at: datetime | None


@dataclass(frozen=True)
class AlertHistoryEntry:
    occurred_at: datetime
    category: str
    severity: str
    title: str
    message: str


class GetUserDashboardSettingsUseCase:
    def __init__(
        self,
        repository: UserDashboardSettingsPort,
        default_factory: Callable[[UUID], UserDashboardSettings],
    ) -> None:
        self.repository = repository
        self.default_factory = default_factory

    def execute(self, user: User) -> UserDashboardSettings:
        stored = self.repository.get_dashboard_settings(user.id)
        if stored is not None:
            return stored
        return self.default_factory(user.id)


class UpdateUserDashboardSettingsUseCase:
    def __init__(self, repository: UserDashboardSettingsPort) -> None:
        self.repository = repository

    def execute(self, user: User, settings: UserDashboardSettings) -> UserDashboardSettings:
        from src.application.dashboard import normalize_dashboard_settings

        normalized = normalize_dashboard_settings(replace(settings, user_id=user.id))
        return self.repository.save_dashboard_settings(normalized)


class ListAlertHistoryUseCase:
    def __init__(self, repository: AlertHistoryPort) -> None:
        self.repository = repository

    def execute(self, user: User, limit: int = 20) -> list[AlertHistoryEntry]:
        return self.repository.list_alert_history(user.id, limit)
