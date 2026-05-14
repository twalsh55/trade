from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

import pandas as pd

from src.domain.auth import ExternalIdentity, User
from src.domain.prospecting import ProspectMatch, SocialPost

if TYPE_CHECKING:
    from src.application.account import AlertHistoryEntry, UserDashboardSettings
    from src.application.billing import BillingOverview


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


class BillingPort(Protocol):
    def get_billing_overview(self, user: User) -> BillingOverview:
        """Return billing status for the authenticated user."""

    def create_checkout_session(self, user: User, return_url: str | None = None) -> str:
        """Create a Stripe Checkout session URL for the authenticated user."""

    def create_portal_session(self, user: User, return_url: str | None = None) -> str:
        """Create a Stripe Billing Portal session URL for the authenticated user."""


class SocialLeadSourcePort(Protocol):
    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        """Return recent social posts for a search term."""


class ProspectDraftingPort(Protocol):
    def draft_promotional_replies(
        self,
        app_summary: str,
        matches: tuple[ProspectMatch, ...],
        app_url: str | None = None,
    ) -> list[str]:
        """Return a suggested non-posted reply for each shortlisted match."""


class EmailDeliveryPort(Protocol):
    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        """Send a plain-text email."""
