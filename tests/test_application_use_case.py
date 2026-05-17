from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pandas as pd
import pytest

from src.application.account import UserDashboardSettings
from src.application.crm import (
    AddLeadFollowUpNoteUseCase,
    CalendarEventInput,
    CompleteLeadFollowUpUseCase,
    DesignLeadFollowUpEmailUseCase,
    EmailThreadMessageInput,
    SyncMailboxConnectionUseCase,
    GetLeadFollowUpOverviewUseCase,
    IngestCalendarEventUseCase,
    IngestLeadEmailThreadUseCase,
    SnoozeLeadFollowUpUseCase,
    _build_email_ask_line,
    _build_email_close_line,
    _build_email_context_line,
    _build_email_intro,
    _build_email_proof_line,
    _build_email_rationale,
    _build_email_signoff,
    _build_email_subject,
    _build_relationship_context_summary,
    _build_last_30_days_summary,
    _build_meeting_prep_summary,
    _build_recent_upload_summary,
    _resolve_upcoming_meeting,
    _build_upload_follow_through_hint,
    _build_reconnect_message_hint,
    _build_reconnect_next_move,
    _build_reconnect_why_now,
    _build_recent_changes_summary,
    _build_relationship_timing_nudge,
    _build_thread_memory_summary,
    _build_thread_next_touch_hint,
    _build_thread_open_loop,
    _build_thread_relationship_pulse,
    _build_thread_carry_forward_hint,
    _build_thread_continuity_memory,
    _build_thread_unresolved_hint,
    _build_thread_recent_change_hint,
    _build_thread_continuity_span,
    _build_ambient_memory_summary,
    _compute_relationship_health_score,
    _describe_upload_source,
    _derive_company_from_email,
    _derive_name_from_email,
    _ensure_sentence,
    _health_label,
    _merge_email_thread_into_follow_up,
    _next_occurrence,
    _normalize_email_length,
    _normalize_email_message,
    _normalize_email_objective,
    _normalize_email_tone,
    _require_follow_up,
    _relationship_state,
    _resolve_follow_up_from_latest_email,
    _resolve_thread_counterpart,
    _sentence_case,
    _truncate_sentence,
)
from src.adapters.crm.oauth_mailbox_provider import MailboxProviderError, OAuthMailboxProviderAdapter
from src.application.dashboard import build_default_dashboard_settings
from src.adapters.crm.in_memory_follow_up_repository import InMemoryLeadFollowUpRepository
from src.application.use_cases import BuildCrashDashboardUseCase
from src.domain.auth import User
from src.domain.crm import LeadEmailThreadSummary, LeadFollowUp, LeadRelationshipReminder, LeadTimelineEntry, MailboxConnection
from src.domain.crm import CalendarConnection
from src.domain.models import DashboardConfig


class StubMarketData:
    def __init__(self, close: pd.DataFrame) -> None:
        self.close = close
        self.calls: list[tuple[list[str], date, date]] = []

    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        self.calls.append((tickers, start_date, end_date))
        return self.close


class StubLeadFollowUpRepository:
    def __init__(self) -> None:
        self.completed: list[tuple[str, datetime]] = []
        self.snoozed: list[tuple[str, datetime]] = []
        self.notes: list[tuple[str, str, datetime]] = []
        self.imported: list[tuple[str, ...]] = []

    def list_lead_follow_ups(self, user: User):  # type: ignore[no-untyped-def]
        return []

    def complete_lead_follow_up(self, user: User, follow_up_id: str, completed_at: datetime) -> None:
        self.completed.append((follow_up_id, completed_at))

    def snooze_lead_follow_up(self, user: User, follow_up_id: str, next_follow_up_at: datetime) -> None:
        self.snoozed.append((follow_up_id, next_follow_up_at))

    def append_note_to_lead_follow_up(self, user: User, follow_up_id: str, note_body: str, noted_at: datetime) -> None:
        self.notes.append((follow_up_id, note_body, noted_at))

    def import_lead_follow_ups(self, user: User, follow_ups):  # type: ignore[no-untyped-def]
        self.imported.append(tuple(item.id for item in follow_ups))
        return len(follow_ups)


def make_user() -> User:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    return User(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        auth_provider="clerk",
        auth_issuer="https://example.clerk.accounts.dev",
        auth_subject="user_123",
        stripe_customer_id=None,
        email="user@example.com",
        given_name="Ada",
        family_name="Lovelace",
        display_name="Ada Lovelace",
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


def build_follow_up(
    *,
    now: datetime,
    lead_name: str = "Test Lead",
    company_name: str = "Example Co",
    stage: str = "Discovery",
    priority: str = "medium",
    next_step: str = "Send a quick recap",
    notes: str = "Shared spreadsheet-heavy workflow pain.",
    email_address: str = "lead@example.com",
    referral_source_name: str = "",
    last_contacted_at: datetime | None = None,
    next_follow_up_at: datetime | None = None,
    timeline: tuple[LeadTimelineEntry, ...] = (),
    reminders: tuple[LeadRelationshipReminder, ...] = (),
    threads: tuple[LeadEmailThreadSummary, ...] = (),
    relationship_state: str = "",
    last_meaningful_interaction_at: datetime | None = None,
) -> LeadFollowUp:
    return LeadFollowUp(
        id="lead-test",
        lead_name=lead_name,
        company_name=company_name,
        owner_name="Ada Lovelace",
        stage=stage,
        priority=priority,
        contact_channel="email",
        last_contacted_at=last_contacted_at,
        next_follow_up_at=next_follow_up_at or now,
        next_step=next_step,
        notes=notes,
        timeline=timeline,
        email_address=email_address,
        referral_source_name=referral_source_name,
        relationship_reminders=reminders,
        recent_email_threads=threads,
        relationship_state=relationship_state,
        last_meaningful_interaction_at=last_meaningful_interaction_at,
    )


def test_use_case_executes_and_deduplicates_tickers() -> None:
    dates = pd.bdate_range("2020-01-01", periods=320)
    close = pd.DataFrame(
        {
            "SPY": range(320),
            "QQQ": range(100, 420),
            "^VIX": range(20, 340),
            "HYG": range(50, 370),
            "^IRX": range(60, 380),
            "^TNX": range(70, 390),
        },
        index=dates,
    ).astype(float)
    market_data = StubMarketData(close)
    use_case = BuildCrashDashboardUseCase(market_data=market_data)
    config = DashboardConfig(
        universe=["SPY", "QQQ", "SPY"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        start_date=date(2020, 1, 1),
        end_date=date(2021, 3, 31),
    )

    result = use_case.execute(config)

    tickers, start_date, end_date = market_data.calls[0]
    assert tickers == ["HYG", "QQQ", "SPY", "^IRX", "^TNX", "^VIX"]
    assert start_date == config.start_date
    assert end_date == config.end_date
    assert result.close_data.equals(close)
    assert result.metrics["price"] == float(close["SPY"].iloc[-1])
    assert result.regime
    assert result.actions


def test_use_case_raises_when_market_data_is_missing() -> None:
    market_data = StubMarketData(pd.DataFrame())
    use_case = BuildCrashDashboardUseCase(market_data=market_data)
    config = DashboardConfig(
        universe=["QQQ"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        start_date=date(2020, 1, 1),
        end_date=date(2020, 12, 31),
    )

    try:
        use_case.execute(config)
    except ValueError as exc:
        assert str(exc) == "Could not load market data. Check ticker symbols or network connectivity."
    else:
        raise AssertionError("Expected missing data to raise ValueError")


def test_crm_follow_up_action_use_cases_delegate_with_expected_times() -> None:
    repository = StubLeadFollowUpRepository()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    user = make_user()

    complete = CompleteLeadFollowUpUseCase(repository=repository, now=lambda: now).execute(user, "lead-1")
    assert complete.follow_up_id == "lead-1"
    assert complete.action == "complete"
    assert repository.completed == [("lead-1", now)]

    snooze = SnoozeLeadFollowUpUseCase(repository=repository, now=lambda: now).execute(user, "lead-2", 24)
    assert snooze.follow_up_id == "lead-2"
    assert snooze.action == "snooze"
    assert repository.snoozed == [("lead-2", datetime(2024, 5, 7, 12, 30, tzinfo=UTC))]

    note = AddLeadFollowUpNoteUseCase(repository=repository, now=lambda: now).execute(user, "lead-3", "Need tighter rollout framing.")
    assert note.follow_up_id == "lead-3"
    assert note.action == "note"
    assert repository.notes == [("lead-3", "Need tighter rollout framing.", now)]


def test_add_lead_follow_up_note_requires_non_empty_body() -> None:
    repository = StubLeadFollowUpRepository()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)

    try:
        AddLeadFollowUpNoteUseCase(repository=repository, now=lambda: now).execute(make_user(), "lead-1", "   ")
    except ValueError as exc:
        assert str(exc) == "Note body is required."
    else:
        raise AssertionError("Expected ValueError for empty note")


def test_oauth_mailbox_refresh_requires_reconnect_when_refresh_token_is_missing() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    adapter = OAuthMailboxProviderAdapter(now=lambda: now)
    connection = MailboxConnection(
        id="mailbox-gmail-test",
        provider="gmail",
        email_address="ada@example.com",
        display_name="Ada Lovelace",
        status="connected",
        connected_at=now - timedelta(days=2),
        connection_mode="oauth",
        access_token="expired-access-token",
        refresh_token="",
        token_expires_at=now - timedelta(minutes=5),
    )

    with pytest.raises(MailboxProviderError) as exc_info:
        adapter.refresh_connection(connection)

    assert str(exc_info.value) == "Reconnect this inbox so Brivoly can keep holding relationship memory quietly."


def test_mailbox_sync_marks_connection_for_reconnect_when_provider_refresh_fails() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    user = make_user()
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    repository.save_mailbox_connection(
        user,
        MailboxConnection(
            id="mailbox-gmail-oauth",
            provider="gmail",
            email_address="ada@example.com",
            display_name="Ada Lovelace",
            status="connected",
            connected_at=now - timedelta(days=2),
            connection_mode="oauth",
            access_token="expired-access-token",
            refresh_token="refresh-token",
            token_expires_at=now - timedelta(minutes=5),
            background_sync_enabled=True,
        ),
    )

    class FailingMailboxProvider:
        def build_authorization_url(self, provider: str, redirect_uri: str, state: str) -> str:
            raise AssertionError("not used")

        def exchange_authorization_code(
            self,
            provider: str,
            code: str,
            redirect_uri: str,
            existing_connection=None,
        ):  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

        def refresh_connection(self, connection: MailboxConnection) -> MailboxConnection:
            raise RuntimeError("Reconnect this inbox so Brivoly can keep holding relationship memory quietly.")

        def ensure_watch_subscription(self, connection: MailboxConnection) -> MailboxConnection:
            raise AssertionError("not used")

        def pull_thread_updates(self, connection: MailboxConnection, max_results: int = 10):  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

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
        ):  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

    with pytest.raises(RuntimeError) as exc_info:
        SyncMailboxConnectionUseCase(
            repository=repository,
            now=lambda: now,
            mailbox_provider=FailingMailboxProvider(),
        ).execute(user, "mailbox-gmail-oauth")

    assert str(exc_info.value) == "Reconnect this inbox so Brivoly can keep holding relationship memory quietly."
    [saved_connection] = repository.list_mailbox_connections(user)
    assert saved_connection.status == "needs_reauth"
    assert saved_connection.reauth_required is True
    assert saved_connection.health_note == "Reconnect this inbox so Brivoly can keep holding relationship memory quietly."


def test_design_lead_follow_up_email_uses_lead_context_and_business_profile() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()
    settings = build_default_dashboard_settings(user.id, telegram_enabled=False)
    settings = UserDashboardSettings(
        user_id=settings.user_id,
        universe=settings.universe,
        benchmark=settings.benchmark,
        vix_symbol=settings.vix_symbol,
        risk_proxy=settings.risk_proxy,
        short_yield_symbol=settings.short_yield_symbol,
        long_yield_symbol=settings.long_yield_symbol,
        lookback_years=settings.lookback_years,
        telegram_enabled=settings.telegram_enabled,
        business_name="Northstar Studio",
        business_website="https://northstar.example",
        outbound_sender_name="Ada from Northstar",
        profile_alias="ada",
        business_logo_data_url=settings.business_logo_data_url,
        onboarding_profile_deferred=settings.onboarding_profile_deferred,
        crm_ai_prompt=settings.crm_ai_prompt,
        crm_preferred_import_formats=settings.crm_preferred_import_formats,
        crm_image_intake_channels=settings.crm_image_intake_channels,
        crm_image_intake_notes=settings.crm_image_intake_notes,
        preferred_language=settings.preferred_language,
        preferred_locale=settings.preferred_locale,
        data_retention_days=settings.data_retention_days,
        allow_ai_processing=settings.allow_ai_processing,
        privacy_consent_version=settings.privacy_consent_version,
        privacy_consent_granted_at=settings.privacy_consent_granted_at,
    )

    draft = DesignLeadFollowUpEmailUseCase(
        repository=repository,
        settings_loader=lambda authenticated_user: settings,
    ).execute(
        user,
        "lead-riverbridge",
        objective="follow_up",
        tone="warm",
        length="medium",
    )

    assert draft.follow_up_id == "lead-riverbridge"
    assert "proposal" in draft.subject.lower()
    assert "Northstar Studio" in draft.body
    assert "Follow up on proposal review" in draft.body
    assert "Ada from Northstar" in draft.body
    assert draft.rationale


def test_follow_up_overview_enriches_relationship_intelligence() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    overview = GetLeadFollowUpOverviewUseCase(repository=repository, now=lambda: now).execute(make_user())

    amber = next(item for item in overview.items if item.id == "lead-amber-studio")
    lattice = next(item for item in overview.items if item.id == "lead-lattice")
    cedar = next(item for item in overview.items if item.id == "lead-cedar")

    assert lattice.last_meaningful_interaction_at is not None
    assert lattice.referral_source_name == "Nina at Harbor Circle"
    assert any(reminder.kind == "referral" for reminder in amber.relationship_reminders)
    assert any(reminder.kind == "birthday" for reminder in lattice.relationship_reminders)
    assert cedar.dormant is True
    assert cedar.relationship_state in {"drifting", "stale", "at_risk"}
    assert cedar.relationship_health_score < 75
    assert amber.relationship_timing_nudge
    assert amber.relationship_context_summary
    assert amber.relationship_recent_changes_summary
    assert "shared upload link" in amber.relationship_recent_upload_summary
    assert amber.relationship_upload_follow_through_hint
    assert amber.relationship_last_30_days_summary
    assert amber.relationship_meeting_prep_summary
    assert amber.relationship_reconnect_why_now
    assert amber.relationship_reconnect_next_move
    assert amber.relationship_reconnect_message_hint
    assert amber.recent_email_threads[0].memory_summary
    assert amber.recent_email_threads[0].next_touch_hint
    assert amber.recent_email_threads[0].open_loop
    assert amber.recent_email_threads[0].relationship_pulse
    assert amber.recent_email_threads[0].continuity_span
    assert amber.recent_email_threads[0].recent_change_hint
    assert amber.recent_email_threads[0].carry_forward_hint
    assert amber.recent_email_threads[0].unresolved_hint
    assert amber.recent_email_threads[0].continuity_memory
    assert overview.relationship_summary is not None
    assert overview.relationship_summary.stale_count >= 1
    assert overview.relationship_summary.referral_reminder_count >= 1
    assert overview.relationship_summary.milestone_reminder_count >= 1
    assert overview.relationship_summary.warm_intro_connections
    assert overview.pipeline_summary is not None
    assert any(stage.stage == "Proposal" for stage in overview.pipeline_summary.stage_summaries)
    assert any(stage.high_priority_count >= 1 for stage in overview.pipeline_summary.stage_summaries)
    assert overview.ambient_memory_summary is not None
    assert overview.ambient_memory_summary.continuity_state in {"warm", "waiting", "attention_needed", "paused", "disconnected"}
    assert overview.ambient_memory_summary.continuity_summary
    assert overview.ambient_memory_summary.event_ready_mailbox_count >= 0
    assert overview.ambient_memory_summary.warm_calendar_count >= 0
    assert isinstance(overview.ambient_memory_summary.suggested_action_label, str)
    assert isinstance(overview.ambient_memory_summary.suggested_action_route, str)
    assert isinstance(overview.ambient_memory_summary.suggested_action_focus, str)
    assert isinstance(overview.ambient_memory_summary.suggested_action_note, str)
    assert isinstance(overview.ambient_memory_summary.warm_source_labels, tuple)
    assert isinstance(overview.ambient_memory_summary.quiet_source_labels, tuple)
    assert isinstance(overview.ambient_memory_summary.attention_source_labels, tuple)
    assert isinstance(overview.ambient_memory_summary.paused_source_labels, tuple)


def test_ambient_memory_summary_routes_calendar_only_waiting_state_to_calendar_memory() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)

    summary = _build_ambient_memory_summary(
        mailbox_connections=[],
        calendar_connections=[
            CalendarConnection(
                id="calendar-1",
                provider="google_calendar",
                calendar_address="ada@northstar.example",
                display_name="Northstar schedule",
                status="connected",
                connected_at=now - timedelta(days=5),
                last_sync_at=now - timedelta(hours=4),
                last_event_ingested_at=None,
                background_sync_enabled=True,
            )
        ],
    )

    assert summary.continuity_state == "waiting"
    assert summary.suggested_action_label == "Check calendars"
    assert summary.suggested_action_route == "/clientos/inbox?connections=calendar"
    assert summary.suggested_action_focus == "calendar"
    assert "meeting event" in summary.suggested_action_note


def test_ingest_lead_email_thread_auto_updates_relationship_memory() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()

    overview = IngestLeadEmailThreadUseCase(repository=repository, now=lambda: now).execute(
        user,
        source="gmail",
        thread_id="thread-priya-followup",
        messages=[
            EmailThreadMessageInput(
                message_id="msg-1",
                sent_at=now,
                direction="inbound",
                from_email="priya@latticelane.com",
                from_name="Priya Nair",
                to_emails=("ada@example.com",),
                subject="Re: spreadsheet workflow question",
                body_text="Still using Sheets first. Happy to look at examples next week.",
                snippet="Still using Sheets first. Happy to look at examples next week.",
            )
        ],
    )

    lead = next(item for item in overview.items if item.email_address == "priya@latticelane.com")
    assert lead.contact_channel == "email"
    assert lead.priority == "high"
    assert lead.next_step == "Reply to Priya Nair's latest email."
    assert lead.recent_email_threads
    assert lead.recent_email_threads[0].needs_reply is True
    assert "Sheets first" in lead.recent_email_threads[0].memory_summary
    assert "Reply to Priya Nair" in lead.recent_email_threads[0].next_touch_hint
    assert "Sheets first" in lead.recent_email_threads[0].open_loop
    assert "waiting on you" in lead.recent_email_threads[0].relationship_pulse
    assert "Single-message thread" in lead.recent_email_threads[0].continuity_span
    assert any(entry.id == "email-msg-1" for entry in lead.timeline)
    assert overview.inbox_summary is not None
    assert overview.inbox_summary.needs_reply_count >= 1


def test_ingest_lead_email_thread_auto_creates_contact_when_unknown() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()

    overview = IngestLeadEmailThreadUseCase(repository=repository, now=lambda: now).execute(
        user,
        source="outlook",
        thread_id="thread-new-contact",
        messages=[
            EmailThreadMessageInput(
                message_id="msg-new-1",
                sent_at=now,
                direction="inbound",
                from_email="maria@seabreezecreative.com",
                from_name="Maria Costa",
                to_emails=("ada@example.com",),
                subject="Need a simpler client follow-up system",
                body_text="We keep losing track of who owes the next reply.",
                snippet="We keep losing track of who owes the next reply.",
            )
        ],
    )

    lead = next(item for item in overview.items if item.email_address == "maria@seabreezecreative.com")
    assert lead.stage == "Inbox"
    assert lead.lead_name == "Maria Costa"
    assert lead.company_name == "Seabreezecreative"
    assert overview.inbox_summary is not None
    assert overview.inbox_summary.auto_created_contact_count >= 1


def test_crm_helper_branches_cover_thread_memory_and_timing_paths() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)
    reply_thread = LeadEmailThreadSummary(
        thread_id="thread-1",
        source="gmail",
        subject="Reply needed",
        counterpart_name="Amber",
        counterpart_email="amber@example.com",
        last_message_at=now,
        last_message_direction="inbound",
        message_count=1,
        snippet="",
        needs_reply=True,
        waiting_on_contact=False,
    )
    waiting_thread = LeadEmailThreadSummary(
        thread_id="thread-2",
        source="gmail",
        subject="Waiting",
        counterpart_name="Marcus",
        counterpart_email="marcus@example.com",
        last_message_at=now,
        last_message_direction="outbound",
        message_count=1,
        snippet="",
        needs_reply=False,
        waiting_on_contact=True,
    )
    quiet_thread = LeadEmailThreadSummary(
        thread_id="thread-3",
        source="gmail",
        subject="Quiet",
        counterpart_name="Jordan",
        counterpart_email="jordan@example.com",
        last_message_at=now.replace(day=1),
        last_message_direction="outbound",
        message_count=1,
        snippet="",
        needs_reply=False,
        waiting_on_contact=False,
    )
    active_thread = LeadEmailThreadSummary(
        thread_id="thread-4",
        source="gmail",
        subject="Active",
        counterpart_name="Priya",
        counterpart_email="priya@example.com",
        last_message_at=now - timedelta(days=1),
        last_message_direction="inbound",
        message_count=4,
        snippet="",
        needs_reply=False,
        waiting_on_contact=False,
    )
    light_thread = LeadEmailThreadSummary(
        thread_id="thread-5",
        source="gmail",
        subject="Light",
        counterpart_name="Lee",
        counterpart_email="lee@example.com",
        last_message_at=now - timedelta(days=1),
        last_message_direction="outbound",
        message_count=2,
        snippet="",
        needs_reply=False,
        waiting_on_contact=False,
    )
    reply_snippet_thread = replace(reply_thread, snippet="pricing concern came up again")
    waiting_snippet_thread = replace(waiting_thread, snippet="sent revised onboarding recap")
    active_snippet_thread = replace(active_thread, snippet="they approved the revised scope")
    long_reply_thread = replace(active_snippet_thread, message_count=5, needs_reply=True)
    long_waiting_thread = replace(waiting_snippet_thread, message_count=4, waiting_on_contact=True)

    next_step_lead = build_follow_up(now=now, next_step="check in next week", notes="", threads=(reply_thread,))
    notes_lead = build_follow_up(now=now, next_step="   ", notes="notes only", threads=(waiting_thread,))
    empty_lead = build_follow_up(now=now, next_step="   ", notes="   ", threads=(quiet_thread,))
    upload_context_lead = build_follow_up(
        now=now,
        next_step="   ",
        notes="   ",
        timeline=(LeadTimelineEntry(id="upload-1", occurred_at=now, kind="import", channel="magic_link", summary="sent annotated scope screenshot"),),
        threads=(light_thread,),
    )
    upload_for_next_step = replace(
        build_follow_up(now=now, next_step="check in next week", notes="", threads=()),
        timeline=(LeadTimelineEntry(id="upload-next-step", occurred_at=now, kind="import", channel="magic_link", summary="shared annotated budget screenshot"),),
    )
    upload_waiting_lead = replace(
        notes_lead,
        timeline=(LeadTimelineEntry(id="upload-waiting", occurred_at=now, kind="import", channel="magic_link", summary="shared marked-up scope image"),),
    )
    stale_upload_follow_up = build_follow_up(
        now=now,
        next_step="   ",
        notes="   ",
        timeline=(LeadTimelineEntry(id="upload-stale", occurred_at=now - timedelta(days=4), kind="import", channel="custom", summary="latest capture"),),
        threads=(),
    )
    reconnect_upload_follow_up = build_follow_up(
        now=now,
        next_step="   ",
        notes="   ",
        timeline=(LeadTimelineEntry(id="upload-reconnect", occurred_at=now - timedelta(days=1), kind="import", channel="magic_link", summary="shared revised launch notes"),),
        threads=(),
        relationship_state="stale",
    )

    assert _build_thread_memory_summary(next_step_lead, reply_thread) == "This thread is tied to Check in next week."
    assert _build_thread_memory_summary(notes_lead, waiting_thread) == "Notes only."
    assert _build_thread_memory_summary(empty_lead, quiet_thread) == "Brivoly has not captured enough thread context yet."

    assert _build_thread_open_loop(next_step_lead, reply_thread) == "Check in next week."
    assert _build_thread_open_loop(notes_lead, waiting_thread) == "Notes only."
    assert _build_thread_open_loop(empty_lead, quiet_thread) == "Brivoly has not isolated the open loop here yet."
    assert "annotated scope screenshot" in _build_thread_open_loop(upload_context_lead, light_thread)

    assert "Reply to Amber." in _build_thread_next_touch_hint(next_step_lead, reply_thread, now)
    assert "Hold steady for now." in _build_thread_next_touch_hint(notes_lead, waiting_thread, now)
    assert _build_thread_next_touch_hint(empty_lead, quiet_thread, now) == "Reconnect with Jordan. This thread has gone quiet."
    assert _build_thread_next_touch_hint(build_follow_up(now=now, threads=(), next_step="send the recap"), quiet_thread, now.replace(day=3)) == "Send the recap."
    assert _build_thread_next_touch_hint(build_follow_up(now=now, threads=(), next_step="   "), quiet_thread, now.replace(day=3)) == "Keep this relationship warm with a light check-in."
    assert "waiting on you" in _build_thread_relationship_pulse(next_step_lead, reply_thread, now)
    assert "waiting on Marcus" in _build_thread_relationship_pulse(notes_lead, waiting_thread, now)
    assert "has been quiet" in _build_thread_relationship_pulse(empty_lead, quiet_thread, now)
    assert "active back-and-forth" in _build_thread_relationship_pulse(build_follow_up(now=now, threads=(active_thread,)), active_thread, now)
    assert "still light" in _build_thread_relationship_pulse(upload_context_lead, light_thread, now)
    assert "Single-message thread" in _build_thread_continuity_span(reply_thread, now)
    assert "2-message exchange" in _build_thread_continuity_span(light_thread, now)
    assert "4-message thread" in _build_thread_continuity_span(active_thread, now)
    assert "New since your last touch" in _build_thread_recent_change_hint(next_step_lead, reply_snippet_thread, now)
    assert "Last thing you sent" in _build_thread_recent_change_hint(notes_lead, waiting_snippet_thread, now)
    assert "Most recent turn" in _build_thread_recent_change_hint(empty_lead, active_snippet_thread, now)
    assert "Fresh context around this thread" in _build_thread_recent_change_hint(upload_context_lead, light_thread, now)
    assert "Something shifted recently." in _build_thread_recent_change_hint(
        replace(empty_lead, relationship_recent_changes_summary="Something shifted recently."),
        quiet_thread,
        now,
    )
    assert "Still orbiting" in _build_thread_recent_change_hint(next_step_lead, reply_thread, now)
    assert "Not much shifted here" in _build_thread_recent_change_hint(empty_lead, quiet_thread, now)
    assert "Carry this forward" in _build_thread_carry_forward_hint(empty_lead, active_snippet_thread)
    assert "If they reply" in _build_thread_carry_forward_hint(build_follow_up(now=now, next_step="send the recap", threads=(waiting_thread,)), waiting_thread)
    assert "Ground your reply" in _build_thread_carry_forward_hint(next_step_lead, reply_snippet_thread)
    assert "Weave in the new client context" in _build_thread_carry_forward_hint(upload_context_lead, light_thread)
    context_only_lead = replace(empty_lead, relationship_context_summary="Pricing concerns and rollout timing")
    assert "Carry forward the context around" in _build_thread_carry_forward_hint(context_only_lead, quiet_thread)
    assert _build_thread_carry_forward_hint(empty_lead, quiet_thread) == ""
    assert "Still waiting on your reply" in _build_thread_unresolved_hint(next_step_lead, reply_snippet_thread)
    assert "Your reply should move" in _build_thread_unresolved_hint(next_step_lead, reply_thread)
    assert "If they come back, restart from" in _build_thread_unresolved_hint(notes_lead, waiting_snippet_thread)
    assert "If they reply, come back to" in _build_thread_unresolved_hint(build_follow_up(now=now, next_step="send the recap", notes="   ", threads=(waiting_thread,)), waiting_thread)
    assert "This thread already has enough context" in _build_thread_unresolved_hint(empty_lead, active_snippet_thread)
    assert "Keep the new client context tied to this thread" in _build_thread_unresolved_hint(upload_context_lead, light_thread)
    assert "Carry forward what changed" in _build_thread_unresolved_hint(replace(empty_lead, relationship_recent_changes_summary="Something shifted recently."), quiet_thread)
    assert _build_thread_unresolved_hint(empty_lead, quiet_thread) == ""
    assert "Longer thread to re-enter" in _build_thread_continuity_memory(next_step_lead, long_reply_thread)
    assert "restart there instead of rebuilding the thread" in _build_thread_continuity_memory(notes_lead, long_waiting_thread)
    assert "Thread through-line: Something shifted recently." in _build_thread_continuity_memory(
        replace(empty_lead, relationship_recent_changes_summary="Something shifted recently."),
        active_thread,
    )
    assert "Thread through-line: Send the recap." in _build_thread_continuity_memory(
        build_follow_up(now=now, next_step="send the recap", notes="   ", threads=(active_thread,)),
        active_thread,
    )
    assert _build_thread_continuity_memory(empty_lead, quiet_thread) == ""
    assert "Best next touch from this new context" in _build_upload_follow_through_hint(upload_for_next_step, now)
    assert "use the new client context in your next check-in" in _build_upload_follow_through_hint(upload_waiting_lead, now)
    assert "Use this new client context while it is still fresh" in _build_upload_follow_through_hint(upload_context_lead, now)
    assert "Keep this new client context in view" in _build_upload_follow_through_hint(stale_upload_follow_up, now)
    assert "easiest reason to reopen the relationship" in _build_upload_follow_through_hint(reconnect_upload_follow_up, now)


def test_crm_helper_branches_cover_relationship_summaries() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)
    timeline = (
        LeadTimelineEntry(id="t1", occurred_at=now, kind="email", channel="email", summary="sent a recap"),
        LeadTimelineEntry(id="t2", occurred_at=now.replace(day=16), kind="call", channel="phone", summary="discussed rollout"),
    )
    reminder = LeadRelationshipReminder(kind="birthday", title="Birthday", message="reach out before the birthday", due_at=now)
    lead = build_follow_up(
        now=now,
        stage="proposal",
        timeline=timeline,
        reminders=(reminder,),
        threads=(
            LeadEmailThreadSummary(
                thread_id="thread",
                source="gmail",
                subject="Proposal",
                counterpart_name="Taylor",
                counterpart_email="taylor@example.com",
                last_message_at=now.replace(day=15),
                last_message_direction="outbound",
                message_count=2,
                snippet="pricing is the main question",
                needs_reply=False,
                waiting_on_contact=True,
            ),
        ),
        relationship_state="drifting",
        last_meaningful_interaction_at=now.replace(day=15),
    )

    assert "waiting on them" in _build_relationship_timing_nudge(lead, now)
    assert "Brivoly logged an email update" in _build_recent_changes_summary(lead, now)
    assert "Over the last 30 days" in _build_last_30_days_summary(lead, now)
    assert "The last meaningful discussion centered on" in _build_meeting_prep_summary(lead, now)

    negotiation = build_follow_up(now=now, stage="negotiation", relationship_state="warm")
    proposal = build_follow_up(now=now, stage="proposal", relationship_state="warm", threads=(), last_meaningful_interaction_at=now.replace(day=14))
    stale = build_follow_up(now=now, stage="discovery", relationship_state="stale")
    at_risk = build_follow_up(now=now, stage="discovery", relationship_state="at_risk")
    drifting = build_follow_up(now=now, stage="discovery", relationship_state="drifting")
    reminded = build_follow_up(now=now, stage="discovery", relationship_state="warm", reminders=(reminder,))
    active = build_follow_up(now=now, stage="discovery", relationship_state="warm", reminders=())

    assert "active discussion" in _build_relationship_timing_nudge(negotiation, now)
    assert "Proposal sent" in _build_relationship_timing_nudge(proposal, now)
    assert "have not meaningfully reconnected" in _build_relationship_timing_nudge(stale, now)
    assert _build_relationship_timing_nudge(at_risk, now) == "This relationship may be going cold."
    assert _build_relationship_timing_nudge(drifting, now) == "A light follow-up soon would help keep momentum."
    assert _build_relationship_timing_nudge(reminded, now) == "Reach out before the birthday."
    assert _build_relationship_timing_nudge(active, now) == "Things are active here. Brivoly is keeping the context ready."

    assert _build_recent_changes_summary(build_follow_up(now=now, next_step="ping again"), now) == "No major relationship changes were captured recently."
    assert _build_last_30_days_summary(build_follow_up(now=now, timeline=(), threads=()), now) == "There has not been much relationship activity in the last 30 days."
    assert _build_meeting_prep_summary(build_follow_up(now=now, timeline=(), threads=(), next_step="   ", notes="   "), now) == "Brivoly does not have enough context yet to prep this meeting."
    assert _build_upload_follow_through_hint(build_follow_up(now=now, timeline=(), threads=()), now) == ""
    assert _resolve_upcoming_meeting(build_follow_up(now=now, next_step="review the onboarding meeting", threads=()), now)[0] == now


def test_crm_helper_branches_cover_reconnect_guidance() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)
    reminder = LeadRelationshipReminder(kind="referral", title="Referral", message="send Nina an update", due_at=now)
    reminder_lead = build_follow_up(now=now, relationship_state="warm", reminders=(reminder,), referral_source_name="Nina")
    stale_lead = build_follow_up(now=now, relationship_state="stale", last_meaningful_interaction_at=now - timedelta(days=30))
    stale_without_context = build_follow_up(now=now, relationship_state="stale", last_meaningful_interaction_at=None)
    stale_without_company = replace(stale_without_context, company_name="   ")
    at_risk_lead = build_follow_up(now=now, relationship_state="at_risk", next_step="check in next week")
    drifting_lead = build_follow_up(now=now, relationship_state="drifting")
    plain_lead = build_follow_up(now=now, relationship_state="warm", reminders=(), last_meaningful_interaction_at=None, next_step="   ")
    plain_without_company = replace(plain_lead, company_name="   ")
    bare_company_lead = build_follow_up(now=now, relationship_state="warm", reminders=(), last_meaningful_interaction_at=None, next_step="   ", notes="")
    bare_no_company_lead = replace(bare_company_lead, company_name="   ")
    timeline_only_lead = replace(
        plain_without_company,
        timeline=(LeadTimelineEntry(id="timeline-only", occurred_at=now - timedelta(days=3), kind="email", channel="email", summary="shared updated rollout notes"),),
    )
    waiting_thread = LeadEmailThreadSummary(
        thread_id="thread-reconnect",
        source="gmail",
        subject="Checking in",
        counterpart_name="Jordan",
        counterpart_email="jordan@example.com",
        last_message_at=now - timedelta(days=9),
        last_message_direction="outbound",
        message_count=2,
        snippet="lighter pilot option before busy season",
        needs_reply=False,
        waiting_on_contact=True,
    )
    thread_lead = build_follow_up(now=now, relationship_state="drifting", threads=(waiting_thread,))

    assert "last meaningful touch" in _build_reconnect_why_now(stale_lead, now)
    assert "quiet with Example Co" in _build_reconnect_why_now(stale_without_context, now)
    assert "gentle restart would help" in _build_reconnect_why_now(stale_without_company, now)
    assert "could go cold" in _build_reconnect_why_now(at_risk_lead, now)
    assert "momentum is starting to fade" in _build_reconnect_why_now(drifting_lead, now)
    assert _build_reconnect_why_now(reminder_lead, now) == "Send Nina an update."
    assert _build_reconnect_why_now(plain_lead, now) == "Brivoly is keeping a low-pressure reconnect path ready."
    assert "brief check-in with Example Co" in _build_reconnect_why_now(bare_company_lead, now)
    assert "brief low-pressure check-in" in _build_reconnect_why_now(bare_no_company_lead, now)
    assert "holding context around Shared updated rollout notes" in _build_reconnect_why_now(timeline_only_lead, now)
    assert _build_reconnect_why_now(replace(build_follow_up(now=now, relationship_state="at_risk", next_step="   "), relationship_timing_nudge=""), now) == "Momentum is slipping and this relationship could go cold without a light touch."
    assert _build_reconnect_why_now(build_follow_up(now=now, relationship_state="drifting", notes="", next_step="   ", last_meaningful_interaction_at=None), now) == "The relationship is still warm enough to reopen naturally, but momentum is starting to fade."

    assert "referencing Nina" in _build_reconnect_next_move(reminder_lead, now)
    assert "Pick back up from the last note" in _build_reconnect_next_move(thread_lead, now)
    assert "Restart around the last open thread" in _build_reconnect_next_move(build_follow_up(now=now, threads=(replace(waiting_thread, waiting_on_contact=False),)), now)
    assert _build_reconnect_next_move(build_follow_up(now=now, next_step="send a lighter pilot option", threads=()), now) == "Send a lighter pilot option."
    assert "last meaningful touch" in _build_reconnect_next_move(build_follow_up(now=now, next_step="   ", last_meaningful_interaction_at=now - timedelta(days=12), threads=()), now)
    assert "where things stand with Example Co" in _build_reconnect_next_move(plain_lead, now)
    assert "keep it easy" in _build_reconnect_next_move(bare_company_lead, now)
    assert _build_reconnect_next_move(plain_without_company, now) == "Keep it simple: acknowledge the gap, offer context, and make the next move easy."
    assert "acknowledge the gap lightly" in _build_reconnect_next_move(bare_no_company_lead, now)
    assert "saved context around shared updated rollout notes" in _build_reconnect_next_move(timeline_only_lead, now).lower()

    assert "introduction from Nina" in _build_reconnect_message_hint(reminder_lead, now)
    assert "lighter pilot option" in _build_reconnect_message_hint(thread_lead, now)
    context_lead = build_follow_up(now=now, next_step="   ", notes="   ")
    context_lead = replace(context_lead, relationship_context_summary="Pricing concerns and rollout timing")
    assert "Pricing concerns and rollout timing" in _build_reconnect_message_hint(context_lead, now)
    assert "12 days ago" in _build_reconnect_message_hint(build_follow_up(now=now, next_step="   ", last_meaningful_interaction_at=now - timedelta(days=12)), now)
    assert "check in on Example Co and see if now is a good time to pick this back up" in _build_reconnect_message_hint(bare_company_lead, now)
    assert "check back in on Example Co" in _build_reconnect_message_hint(plain_lead, now)
    assert "check back in and see if this is worth picking up again" in _build_reconnect_message_hint(plain_without_company, now)
    assert "Wanted to circle back on shared updated rollout notes" in _build_reconnect_message_hint(timeline_only_lead, now)
    assert "check in briefly and see if now is a good time to pick this back up" in _build_reconnect_message_hint(bare_no_company_lead, now)


def test_crm_helper_branches_cover_email_ingest_validation_and_email_variants() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    use_case = IngestLeadEmailThreadUseCase(repository=repository, now=lambda: now)
    user = make_user()

    with pytest.raises(ValueError, match="thread_id is required."):
        use_case.execute(user, source="gmail", thread_id="   ", messages=[EmailThreadMessageInput(message_id="1", sent_at=now, direction="inbound", from_email="a@example.com", from_name="", to_emails=("user@example.com",), subject="", body_text="", snippet="")])
    with pytest.raises(ValueError, match="At least one email message is required."):
        use_case.execute(user, source="gmail", thread_id="thread", messages=[])

    with pytest.raises(ValueError, match="Unsupported email objective."):
        _normalize_email_objective("bad")
    with pytest.raises(ValueError, match="Unsupported email tone."):
        _normalize_email_tone("bad")
    with pytest.raises(ValueError, match="Unsupported email length."):
        _normalize_email_length("long")
    with pytest.raises(ValueError, match="Each email message needs a message_id."):
        _normalize_email_message(EmailThreadMessageInput(message_id=" ", sent_at=now, direction="inbound", from_email="a@example.com", from_name="", to_emails=("x@example.com",), subject="", body_text="", snippet=""))
    with pytest.raises(ValueError, match="direction 'inbound' or 'outbound'"):
        _normalize_email_message(EmailThreadMessageInput(message_id="1", sent_at=now, direction="sideways", from_email="a@example.com", from_name="", to_emails=("x@example.com",), subject="", body_text="", snippet=""))
    with pytest.raises(ValueError, match="from_email"):
        _normalize_email_message(EmailThreadMessageInput(message_id="1", sent_at=now, direction="inbound", from_email=" ", from_name="", to_emails=("x@example.com",), subject="", body_text="", snippet=""))
    with pytest.raises(ValueError, match="recipient email"):
        _normalize_email_message(EmailThreadMessageInput(message_id="1", sent_at=now, direction="inbound", from_email="a@example.com", from_name="", to_emails=("",), subject="", body_text="", snippet=""))

    outbound = _normalize_email_message(
        EmailThreadMessageInput(message_id="1", sent_at=now, direction=" outbound ", from_email="ME@EXAMPLE.COM", from_name="Ada", to_emails=(" prospect@example.com ",), subject=" ", body_text="Body text", snippet="")
    )
    assert outbound.subject == "(no subject)"
    assert outbound.from_email == "me@example.com"
    assert outbound.snippet == "Body text"
    assert _resolve_thread_counterpart(user, [outbound]) == ("prospect@example.com", "Ada")
    assert _resolve_thread_counterpart(user, [EmailThreadMessageInput(message_id="1", sent_at=now, direction="outbound", from_email="me@example.com", from_name="", to_emails=("user@example.com",), subject="Subj", body_text="", snippet="")]) == ("", "")

    lead = build_follow_up(now=now, stage="Proposal", notes="spreadsheet process")
    due_at, next_step, priority = _resolve_follow_up_from_latest_email(lead=lead, counterpart_name="Taylor", latest_message=outbound, current_time=now)
    assert due_at > now
    assert "Follow up if Taylor does not reply" in next_step
    assert priority == "medium"
    due_now, reply_step, reply_priority = _resolve_follow_up_from_latest_email(
        lead=lead,
        counterpart_name="Taylor",
        latest_message=EmailThreadMessageInput(message_id="2", sent_at=now, direction="inbound", from_email="taylor@example.com", from_name="Taylor", to_emails=("user@example.com",), subject="Subj", body_text="", snippet=""),
        current_time=now,
    )
    assert due_now == now
    assert reply_priority == "high"
    assert "Reply to Taylor's latest email." == reply_step

    assert _derive_name_from_email("") == ""
    assert _derive_name_from_email("ada.lovelace@example.com") == "Ada Lovelace"
    assert _derive_company_from_email("no-at-symbol") == "Inbox contact"
    assert _derive_company_from_email("person@!!!.com") == "Inbox contact"

    assert _build_email_subject(lead, objective="recap") == "Recap and next steps for Example Co"
    assert _build_email_subject(lead, objective="revive") == "Test Lead, should we restart this?"
    assert _build_email_subject(lead, objective="close_loop") == "Should I close the loop on Example Co?"
    assert _build_email_subject(lead, objective="follow_up") == "Quick follow-up on the Example Co proposal"
    assert "crisp recap" in _build_email_intro(lead, business_name="Brivoly", objective="recap", tone="warm")
    assert "top of your inbox" in _build_email_intro(lead, business_name="Brivoly", objective="revive", tone="warm")
    assert "one last time" in _build_email_intro(lead, business_name="Brivoly", objective="close_loop", tone="warm")
    assert "where things stand" in _build_email_intro(lead, business_name="Brivoly", objective="follow_up", tone="direct")
    assert "strong fit here" in _build_email_intro(lead, business_name="Brivoly", objective="follow_up", tone="confident")
    assert "while the context is still fresh" in _build_email_intro(lead, business_name="Brivoly", objective="follow_up", tone="warm")

    empty_context_lead = build_follow_up(now=now, next_step="reply tomorrow", notes="   ", timeline=())
    assert "close the loop cleanly" in _build_email_context_line(lead, objective="close_loop", tone="warm")
    assert "important next move" in _build_email_context_line(empty_context_lead, objective="recap", tone="warm")
    assert "main thing still on my list" in _build_email_context_line(empty_context_lead, objective="follow_up", tone="warm")
    assert "That still feels like the right place" in _build_email_context_line(lead, objective="follow_up", tone="confident")
    assert _build_email_ask_line(lead, objective="recap", tone="warm").startswith("From here, I suggest we")
    assert _build_email_ask_line(lead, objective="revive", tone="warm").startswith("If this is still relevant")
    assert _build_email_ask_line(lead, objective="close_loop", tone="warm") == "If you want to keep it moving, just reply and I will take it from there."
    assert _build_email_ask_line(lead, objective="follow_up", tone="direct").startswith("If you are still interested")
    assert _build_email_ask_line(lead, objective="follow_up", tone="confident").startswith("The fastest way")
    assert _build_email_ask_line(lead, objective="follow_up", tone="warm").startswith("If helpful")
    assert "rollout light" in _build_email_proof_line(lead, business_name="Brivoly")
    assert "spreadsheet-first process" in _build_email_proof_line(build_follow_up(now=now, stage="Discovery", notes="spreadsheet overload"), business_name="Brivoly")
    assert "low-lift" in _build_email_proof_line(build_follow_up(now=now, stage="Discovery", notes="plain notes"), business_name="Brivoly")
    assert _build_email_close_line(objective="close_loop", tone="warm") == "Either way, a quick yes, no, or later would be perfect."
    assert _build_email_close_line(objective="follow_up", tone="direct") == "A quick reply is enough and I can handle the rest."
    assert _build_email_close_line(objective="follow_up", tone="confident") == "If the timing works, I can keep this moving without much back-and-forth."
    assert _build_email_close_line(objective="follow_up", tone="warm") == "Happy to keep it easy from here."
    assert _build_email_signoff(sender_name="Ada", website="https://example.com") == "Best,\nAda\nhttps://example.com"
    assert _build_email_signoff(sender_name="Ada", website="") == "Best,\nAda"
    assert "Softened the ask" in " ".join(_build_email_rationale(lead, objective="close_loop", tone="warm", business_name="Brivoly"))
    assert "restart" in " ".join(_build_email_rationale(lead, objective="revive", tone="confident", business_name="Brivoly"))
    assert "human and low-pressure" in " ".join(_build_email_rationale(lead, objective="follow_up", tone="warm", business_name="Brivoly"))

    with pytest.raises(KeyError):
        _require_follow_up([], "missing")
    assert _ensure_sentence("") == "reply with the easiest next step"
    assert _ensure_sentence("Hello") == "Hello."
    assert _ensure_sentence("Hello!") == "Hello!"
    assert _truncate_sentence("short", 20) == "short."
    assert _truncate_sentence("one two three four five six seven eight nine", 20).endswith("...")
    assert _sentence_case("") == ""


def test_crm_helper_branches_cover_remaining_health_context_and_merge_paths() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)
    user = make_user()

    assert _compute_relationship_health_score(build_follow_up(now=now, next_follow_up_at=now - timedelta(days=14), next_step=""), now - timedelta(days=10), now) >= 0
    assert _compute_relationship_health_score(build_follow_up(now=now, next_follow_up_at=now - timedelta(days=7)), now - timedelta(days=15), now) >= 0
    assert _compute_relationship_health_score(build_follow_up(now=now, next_follow_up_at=now - timedelta(days=1)), now - timedelta(days=22), now) >= 0
    assert _health_label(49) == "at_risk"
    assert _relationship_state(40, False, build_follow_up(now=now, next_follow_up_at=now), now) == "at_risk"
    assert _relationship_state(72, False, build_follow_up(now=now, next_follow_up_at=now), now) == "warm"
    assert _build_relationship_context_summary(build_follow_up(now=now, notes="   ", timeline=(), threads=())) == "Brivoly has not captured enough relationship context yet."
    upload_follow_up = build_follow_up(
        now=now,
        notes="Imported from note image",
        timeline=(
            LeadTimelineEntry(
                id="upload-1",
                occurred_at=now - timedelta(days=1),
                kind="import",
                channel="magic_link",
                summary="Imported from magic link image. Owner: Ada Lovelace. Stage: Discovery.",
            ),
        ),
    )
    assert "the shared upload link" in _build_recent_upload_summary(upload_follow_up, now)
    assert "Notes captured: Imported from note image." in _build_recent_upload_summary(upload_follow_up, now)
    assert "Imported from magic link image" in _build_relationship_context_summary(upload_follow_up)
    assert "Latest client-sent context" in _build_meeting_prep_summary(upload_follow_up, now)
    assert "Best next touch from this new context" in _build_upload_follow_through_hint(upload_follow_up, now)
    assert "Best use of it right now" in _build_meeting_prep_summary(upload_follow_up, now)
    upload_follow_up_without_next_step = replace(upload_follow_up, next_step="   ")
    assert "Walk in ready to reference the new client context first" in _build_meeting_prep_summary(upload_follow_up_without_next_step, now)
    duplicate_note_follow_up = build_follow_up(
        now=now,
        notes="Imported from phone-note.jpg",
        timeline=(
            LeadTimelineEntry(
                id="upload-dup",
                occurred_at=now,
                kind="import",
                channel="custom",
                summary="Imported from phone-note.jpg",
            ),
        ),
    )
    assert _build_recent_upload_summary(duplicate_note_follow_up, now).endswith("Imported from phone-note.jpg.")
    plain_note_follow_up = build_follow_up(
        now=now,
        notes="Client sent three screenshots after the call",
        timeline=(
            LeadTimelineEntry(
                id="upload-plain",
                occurred_at=now,
                kind="import",
                channel="custom",
                summary="uploaded context from note.png",
            ),
        ),
    )
    assert _build_recent_upload_summary(plain_note_follow_up, now).endswith("Uploaded context from note.png.")
    assert _build_recent_upload_summary(build_follow_up(now=now, timeline=()), now) == ""
    assert _describe_upload_source("image", "Imported from note.png") == "an uploaded image"
    assert _describe_upload_source("telegram", "Imported from mobile upload") == "a shared mobile upload"
    assert _describe_upload_source("csv_upload", "Imported from CSV upload") == "an imported client file"
    assert _describe_upload_source("custom", "Imported from latest file.csv") == "an imported client file"
    assert _describe_upload_source("custom", "Imported from latest capture", "Imported from magic link image") == "the shared upload link"
    assert _describe_upload_source("custom", "Imported from magic link image") == "the shared upload link"
    assert _describe_upload_source("custom", "Imported from latest capture") == "a recent upload"
    assert _next_occurrence(date(2024, 2, 29), date(2025, 1, 1)) is None
    assert _next_occurrence(date(2024, 2, 29), date(2024, 3, 1)) is None

    use_case = IngestLeadEmailThreadUseCase(repository=InMemoryLeadFollowUpRepository(now=lambda: now), now=lambda: now)
    with pytest.raises(ValueError, match="could not identify the external contact"):
        use_case.execute(
            user,
            source="gmail",
            thread_id="thread-no-counterpart",
            messages=[
                EmailThreadMessageInput(
                    message_id="m1",
                    sent_at=now,
                    direction="outbound",
                    from_email="user@example.com",
                    from_name="Ada",
                    to_emails=("user@example.com",),
                    subject="Subj",
                    body_text="Body",
                    snippet="Body",
                )
            ],
        )

    existing_entry = LeadTimelineEntry(id="email-m1", occurred_at=now, kind="email", channel="gmail", summary="Old")
    merged = _merge_email_thread_into_follow_up(
        build_follow_up(now=now, email_address="", timeline=(existing_entry,)),
        user=user,
        source="gmail",
        thread_id="thread-dup",
        counterpart_email="friend@example.com",
        counterpart_name="Friend",
        messages=[
            EmailThreadMessageInput(
                message_id="m1",
                sent_at=now,
                direction="outbound",
                from_email="user@example.com",
                from_name="Ada",
                to_emails=("friend@example.com",),
                subject="Checking in",
                body_text="Body",
                snippet="Body",
            )
        ],
        current_time=now,
    )
    assert len(merged.timeline) == 1
    assert merged.email_address == "friend@example.com"

    merged_without_email = _merge_email_thread_into_follow_up(
        build_follow_up(now=now, email_address="", timeline=()),
        user=user,
        source="gmail",
        thread_id="thread-empty-email",
        counterpart_email="",
        counterpart_name="Friend",
        messages=[
            EmailThreadMessageInput(
                message_id="m2",
                sent_at=now,
                direction="outbound",
                from_email="user@example.com",
                from_name="Ada",
                to_emails=("friend@example.com",),
                subject="Checking in",
                body_text="Body",
                snippet="Body",
            )
        ],
        current_time=now,
    )
    assert merged_without_email.email_address == ""
    assert _build_email_subject(build_follow_up(now=now, stage="Discovery"), objective="follow_up") == "Quick follow-up for Example Co"


def test_ingest_calendar_event_use_case_promotes_upcoming_meeting() -> None:
    now = datetime(2024, 5, 17, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()
    connect_use_case = IngestCalendarEventUseCase(repository=repository, now=lambda: now)

    overview = connect_use_case.execute(
        user,
        source="google_calendar",
        event=CalendarEventInput(
            event_id="meeting-1",
            title="Weekly rollout review",
            starts_at=now + timedelta(days=1),
            attendee_emails=("amber@northstarstudio.com",),
            notes="Review the onboarding screenshots before meeting.",
        ),
    )

    amber = next(item for item in overview.items if item.id == "lead-amber-studio")
    assert amber.relationship_upcoming_meeting_at == (now + timedelta(days=1))
    assert "Weekly rollout review" in amber.relationship_upcoming_meeting_label
    assert amber.next_step == "Prepare for Weekly rollout review."
