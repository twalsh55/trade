from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

import pandas as pd

from src.domain.auth import ExternalIdentity, User

if TYPE_CHECKING:
    from src.application.account import AlertHistoryEntry, UserDashboardSettings


class MarketDataPort(Protocol):
    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Return close prices indexed by date with ticker columns."""


class AuthProviderPort(Protocol):
    def authenticate_session_token(self, session_token: str) -> ExternalIdentity:
        """Validate a provider session token and return a normalized identity."""


class UserRepositoryPort(Protocol):
    def upsert_authenticated_user(self, identity: ExternalIdentity) -> User:
        """Create or update the internal user record for an authenticated identity."""


class UserDashboardSettingsPort(Protocol):
    def get_dashboard_settings(self, user_id: UUID) -> UserDashboardSettings | None:
        """Return saved dashboard settings for a user, if any."""

    def save_dashboard_settings(self, settings: UserDashboardSettings) -> UserDashboardSettings:
        """Persist dashboard settings for a user and return the stored value."""


class AlertHistoryPort(Protocol):
    def list_alert_history(self, user_id: UUID, limit: int) -> list[AlertHistoryEntry]:
        """Return recent alert history for a user ordered from newest to oldest."""

    def append_alert_history(self, user_id: UUID, entry: AlertHistoryEntry) -> None:
        """Append an alert history entry for a user."""
