from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

import pandas as pd

from src.domain.auth import ExternalIdentity, User
from src.domain.crm import (
    CalendarConnection,
    LeadFollowUp,
    LeadImportClarification,
    MailboxConnection,
    MailboxSendReceipt,
    MailboxThreadSnapshot,
)
from src.domain.prospecting import ProspectDraft, ProspectMatch, ProspectTokenUsage, SocialPost

if TYPE_CHECKING:
    from src.application.account import AlertHistoryEntry, UserDashboardSettings
    from src.application.billing import BillingOverview
    from src.application.founder_code import FounderCodeRequest
    from src.application.operator_briefing import ProductUpdateRecord, ProspectRunRecord


class MarketDataPort(Protocol):
    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Return close prices indexed by date with ticker columns."""


class AuthProviderPort(Protocol):
    def authenticate_session_token(self, session_token: str) -> ExternalIdentity:
        """Validate a provider session token and return a normalized identity."""


class UserRepositoryPort(Protocol):
    def upsert_authenticated_user(self, identity: ExternalIdentity) -> User:
        """Create or update the internal user record for an authenticated identity."""

    def get_user_by_id(self, user_id: UUID) -> User | None:
        """Return one internal user by id, if it exists."""


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


class LeadFollowUpRepositoryPort(Protocol):
    def list_lead_follow_ups(self, user: User) -> list[LeadFollowUp]:
        """Return the current open lead follow-up queue for the authenticated user."""

    def complete_lead_follow_up(self, user: User, follow_up_id: str, completed_at: datetime) -> None:
        """Mark a lead follow-up complete."""

    def snooze_lead_follow_up(self, user: User, follow_up_id: str, next_follow_up_at: datetime) -> None:
        """Move the next follow-up time forward."""

    def append_note_to_lead_follow_up(self, user: User, follow_up_id: str, note_body: str, noted_at: datetime) -> None:
        """Append an internal note to a lead follow-up timeline."""

    def import_lead_follow_ups(self, user: User, follow_ups: list[LeadFollowUp]) -> int:
        """Insert imported follow-ups and return how many were stored."""

    def clear_lead_follow_ups(self, user: User) -> None:
        """Remove all stored relationship memory for one user."""

    def list_mailbox_connections(self, user: User) -> list[MailboxConnection]:
        """Return connected inbox accounts for the authenticated user."""

    def save_mailbox_connection(self, user: User, connection: MailboxConnection) -> MailboxConnection:
        """Persist one inbox connection and return the stored value."""

    def delete_mailbox_connection(self, user: User, connection_id: str) -> None:
        """Remove one inbox connection for the authenticated user."""

    def list_calendar_connections(self, user: User) -> list[CalendarConnection]:
        """Return connected calendar accounts for the authenticated user."""

    def save_calendar_connection(self, user: User, connection: CalendarConnection) -> CalendarConnection:
        """Persist one calendar connection and return the stored value."""

    def delete_calendar_connection(self, user: User, connection_id: str) -> None:
        """Remove one calendar connection for the authenticated user."""


class MailboxProviderPort(Protocol):
    def build_authorization_url(self, provider: str, redirect_uri: str, state: str) -> str:
        """Return the provider authorization URL for a mailbox OAuth flow."""

    def exchange_authorization_code(
        self,
        provider: str,
        code: str,
        redirect_uri: str,
        existing_connection: MailboxConnection | None = None,
    ) -> MailboxConnection:
        """Exchange a provider auth code and return a durable mailbox connection."""

    def refresh_connection(self, connection: MailboxConnection) -> MailboxConnection:
        """Refresh a connection token if needed and return the updated connection."""

    def ensure_watch_subscription(self, connection: MailboxConnection) -> MailboxConnection:
        """Register or renew provider-side watch coverage when supported."""

    def pull_thread_updates(self, connection: MailboxConnection, max_results: int = 10) -> list[MailboxThreadSnapshot]:
        """Return recent mailbox thread snapshots for one connected account."""

    def send_message(
        self,
        connection: MailboxConnection,
        *,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
        reply_to_external_message_id: str | None = None,
    ) -> MailboxSendReceipt:
        """Send one outbound note through the provider and return a receipt."""


class CRMImageIntakePort(Protocol):
    def extract_spreadsheet_rows_from_image(
        self,
        prompt: str,
        preferred_formats: list[str],
        file_name: str,
        file_bytes: bytes,
    ) -> str:
        """Extract CRM-shaped rows from an uploaded note image and return CSV content."""


class CRMSpreadsheetAssistPort(Protocol):
    def suggest_field_mapping(
        self,
        prompt: str,
        preferred_formats: list[str],
        source_label: str,
        headers: list[str],
        sample_rows: list[dict[str, str]],
        clarification_answers: dict[str, str] | None = None,
    ) -> tuple[dict[str, str | None], LeadImportClarification | None]:
        """Suggest CRM field mappings and optional clarification prompts for messy spreadsheet headers."""


class SocialLeadSourcePort(Protocol):
    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        """Return recent social posts for a search term."""


class ProspectDraftingPort(Protocol):
    def draft_promotional_replies(
        self,
        app_summary: str,
        matches: tuple[ProspectMatch, ...],
        app_url: str | None = None,
    ) -> list[ProspectDraft]:
        """Return a suggested non-posted reply for each shortlisted match."""

    def get_last_usage(self) -> ProspectTokenUsage | None:
        """Return usage information for the most recent drafting request, if available."""


class EmailDeliveryPort(Protocol):
    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        """Send a plain-text email."""


class ProspectRunHistoryPort(Protocol):
    def append_prospect_run(self, run: ProspectRunRecord) -> None:
        """Persist one prospect run record."""

    def list_prospect_runs(self, since: datetime) -> list[ProspectRunRecord]:
        """Return prospect runs at or after the given timestamp."""


class ProductUpdateLogPort(Protocol):
    def append_product_update(self, update: ProductUpdateRecord) -> None:
        """Persist one product update note."""

    def list_product_updates(self, since: datetime) -> list[ProductUpdateRecord]:
        """Return product updates at or after the given timestamp."""


class FounderCodeRequestPort(Protocol):
    def create_request(
        self,
        source_chat_id: str,
        command_text: str,
        guidance: str | None,
        created_at: datetime,
    ) -> FounderCodeRequest:
        """Persist one founder code request and return the stored record."""

    def list_requests(self, since: datetime | None, limit: int) -> list[FounderCodeRequest]:
        """Return founder code requests ordered from oldest to newest."""
