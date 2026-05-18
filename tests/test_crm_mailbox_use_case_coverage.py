from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.adapters.crm.in_memory_follow_up_repository import InMemoryLeadFollowUpRepository
from src.application.crm import (
    BeginMailboxOAuthUseCase,
    CalendarEventInput,
    CompleteMailboxOAuthUseCase,
    ConnectCalendarUseCase,
    ConnectMailboxUseCase,
    DisconnectCalendarConnectionUseCase,
    EmailThreadMessageInput,
    EnsureMailboxWatchUseCase,
    EraseRelationshipMemoryUseCase,
    GetLeadFollowUpOverviewUseCase,
    IngestCalendarEventUseCase,
    ProcessMailboxWatchEventUseCase,
    SendLeadFollowUpEmailUseCase,
    SyncMailboxConnectionUseCase,
    _build_ambient_memory_summary,
    _build_mailbox_send_continuity_note,
    _build_mailbox_sync_body,
    _build_mailbox_sync_subject,
    _resolve_upcoming_meeting,
    _ensure_mailbox_connection_sendable,
    _mailbox_watch_renewal_due,
    _mark_mailbox_attention_needed,
    _require_calendar_connection,
    _require_mailbox_connection,
    _resolve_mailbox_sync_cursor,
)
from src.domain.auth import User
from src.domain.crm import CalendarConnection, LeadEmailThreadSummary, MailboxConnection, MailboxThreadMessage, MailboxThreadSnapshot


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


def make_mailbox_connection(
    *,
    provider: str = "gmail",
    connection_mode: str = "manual",
    status: str = "connected",
    background_sync_enabled: bool = True,
    email_address: str | None = None,
    external_account_id: str = "acct-123",
    watch_status: str = "inactive",
    watch_expires_at: datetime | None = None,
    last_sync_at: datetime | None = None,
    last_watch_event_at: datetime | None = None,
    reauth_required: bool = False,
    health_note: str = "",
) -> MailboxConnection:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    return MailboxConnection(
        id=f"mailbox-{provider}-test",
        provider=provider,
        email_address=email_address or ("ada@example.com" if provider == "gmail" else "ada@outlook.example"),
        display_name="Ada Lovelace",
        status=status,
        connected_at=now - timedelta(days=2),
        connection_mode=connection_mode,
        background_sync_enabled=background_sync_enabled,
        access_token="access-token",
        refresh_token="refresh-token",
        token_expires_at=now + timedelta(hours=1),
        external_account_id=external_account_id,
        watch_status=watch_status,
        watch_expires_at=watch_expires_at,
        last_sync_at=last_sync_at,
        last_watch_event_at=last_watch_event_at,
        reauth_required=reauth_required,
        health_note=health_note,
    )


def make_calendar_connection(
    *,
    provider: str = "google_calendar",
    status: str = "connected",
    background_sync_enabled: bool = True,
    last_sync_at: datetime | None = None,
    last_event_ingested_at: datetime | None = None,
    health_note: str = "",
) -> CalendarConnection:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    return CalendarConnection(
        id=f"calendar-{provider}-test",
        provider=provider,
        calendar_address="ada@example.com",
        display_name="Ada Calendar",
        status=status,
        connected_at=now - timedelta(days=2),
        background_sync_enabled=background_sync_enabled,
        last_sync_at=last_sync_at,
        last_sync_status="",
        last_sync_error="",
        last_event_ingested_at=last_event_ingested_at,
        health_note=health_note,
    )


def test_ambient_memory_summary_covers_attention_paused_waiting_and_disconnected() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    attention_mailbox = make_mailbox_connection(status="needs_reauth", reauth_required=True)
    paused_calendar = make_calendar_connection(background_sync_enabled=False)
    waiting_mailbox = make_mailbox_connection(connection_mode="manual", last_sync_at=now)
    warm_calendar = make_calendar_connection(last_sync_at=now, last_event_ingested_at=now)

    attention_summary = _build_ambient_memory_summary(
        [attention_mailbox],
        [],
    )
    paused_summary = _build_ambient_memory_summary(
        [],
        [paused_calendar],
    )
    waiting_summary = _build_ambient_memory_summary(
        [waiting_mailbox],
        [],
    )
    paused_mailbox_summary = _build_ambient_memory_summary(
        [make_mailbox_connection(background_sync_enabled=False)],
        [],
    )
    attention_calendar_summary = _build_ambient_memory_summary(
        [],
        [make_calendar_connection(status="needs_reauth", health_note="Reconnect calendar")],
    )
    warm_summary = _build_ambient_memory_summary(
        [],
        [warm_calendar],
    )
    disconnected_summary = _build_ambient_memory_summary([], [])

    assert attention_summary.continuity_state == "attention_needed"
    assert attention_summary.suggested_action_label == "Check inboxes"
    assert paused_summary.continuity_state == "paused"
    assert paused_summary.suggested_action_label == "Resume meeting memory"
    assert paused_mailbox_summary.suggested_action_label == "Resume inbox memory"
    assert waiting_summary.continuity_state == "waiting"
    assert waiting_summary.suggested_action_label == "Open inbox"
    assert warm_summary.continuity_state == "warm"
    assert attention_calendar_summary.suggested_action_label == "Check calendars"
    assert disconnected_summary.continuity_state == "disconnected"
    assert disconnected_summary.suggested_action_label == "Connect one source"


def test_calendar_mailbox_connect_and_disconnect_use_cases_cover_validation_paths() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()

    with pytest.raises(ValueError, match="Unsupported calendar provider"):
        ConnectCalendarUseCase(repository=repository, now=lambda: now).execute(
            user,
            provider="ical",
            calendar_address="ada@example.com",
            display_name="Ada",
        )
    with pytest.raises(ValueError, match="valid calendar address"):
        ConnectCalendarUseCase(repository=repository, now=lambda: now).execute(
            user,
            provider="google_calendar",
            calendar_address="not-an-email",
            display_name="Ada",
        )

    calendar_connection = ConnectCalendarUseCase(
        repository=repository,
        now=lambda: now,
    ).execute(
        user,
        provider="google_calendar",
        calendar_address="ada@example.com",
        display_name="",
    )
    assert calendar_connection.display_name == "Ada"

    repository.save_calendar_connection(
        user,
        replace(calendar_connection, background_sync_enabled=False),
    )
    second = ConnectCalendarUseCase(repository=repository, now=lambda: now).execute(
        user,
        provider="google_calendar",
        calendar_address="ada@example.com",
        display_name="Ada Calendar",
    )
    assert second.id == calendar_connection.id
    assert second.background_sync_enabled is False

    with pytest.raises(KeyError):
        DisconnectCalendarConnectionUseCase(repository=repository).execute(user, "missing-calendar")

    DisconnectCalendarConnectionUseCase(repository=repository).execute(user, calendar_connection.id)
    assert repository.list_calendar_connections(user) == []

    with pytest.raises(ValueError, match="Unsupported mailbox provider"):
        ConnectMailboxUseCase(repository=repository, now=lambda: now).execute(
            user,
            provider="imap",
            email_address="ada@example.com",
            display_name="Ada",
        )
    with pytest.raises(ValueError, match="valid mailbox email address"):
        ConnectMailboxUseCase(repository=repository, now=lambda: now).execute(
            user,
            provider="gmail",
            email_address="bad",
            display_name="Ada",
        )

    mailbox_connection = ConnectMailboxUseCase(repository=repository, now=lambda: now).execute(
        user,
        provider="gmail",
        email_address="ada@example.com",
        display_name="",
    )
    assert mailbox_connection.display_name == "Ada"


def test_erase_relationship_memory_use_case_clears_connections_when_requested() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()
    repository.save_mailbox_connection(user, make_mailbox_connection())
    repository.save_calendar_connection(user, make_calendar_connection())

    with pytest.raises(ValueError, match="Unsupported privacy erase scope"):
        EraseRelationshipMemoryUseCase(repository=repository).execute(
            user,
            scope="unknown",
        )

    EraseRelationshipMemoryUseCase(repository=repository).execute(
        user,
        scope="all_memory",
    )
    assert repository.list_lead_follow_ups(user) == []
    assert repository.list_mailbox_connections(user) == []
    assert repository.list_calendar_connections(user) == []


def test_mailbox_watch_oauth_use_cases_cover_matching_and_failure_paths() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()
    oauth_connection = repository.save_mailbox_connection(
        user,
        make_mailbox_connection(
            provider="gmail",
            connection_mode="oauth",
            external_account_id="acct-123",
        ),
    )

    class FakeMailboxProvider:
        def build_authorization_url(self, provider: str, redirect_uri: str, state: str) -> str:
            return f"https://example.test/oauth/{provider}?redirect_uri={redirect_uri}&state={state}"

        def exchange_authorization_code(
            self,
            provider: str,
            code: str,
            redirect_uri: str,
            existing_connection: MailboxConnection | None = None,
        ) -> MailboxConnection:
            del code, redirect_uri
            return replace(
                existing_connection or oauth_connection,
                provider=provider,
                connection_mode="oauth",
                status="connected",
            )

        def ensure_watch_subscription(self, connection: MailboxConnection) -> MailboxConnection:
            return replace(
                connection,
                watch_status="active",
                watch_expires_at=now + timedelta(hours=4),
            )

        def refresh_connection(self, connection: MailboxConnection) -> MailboxConnection:
            return connection

        def pull_thread_updates(self, connection: MailboxConnection, max_results: int = 10):  # type: ignore[no-untyped-def]
            del max_results
            message = MailboxThreadMessage(
                message_id="msg-1",
                external_message_id="<msg-1@example.com>",
                sent_at=now,
                direction="inbound",
                from_email="lead@example.com",
                from_name="Lead",
                to_emails=(connection.email_address,),
                subject="Checking in",
                body_text="Wanted to keep this moving.",
                snippet="Wanted to keep this moving.",
            )
            return [MailboxThreadSnapshot(source=connection.provider, thread_id="thread-1", messages=(message,))]

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
        ):
            del to_email, to_name, subject, body, reply_to_external_message_id
            message = MailboxThreadMessage(
                message_id="sent-1",
                external_message_id="<sent-1@example.com>",
                sent_at=now,
                direction="outbound",
                from_email=connection.email_address,
                from_name=connection.display_name,
                to_emails=("lead@example.com",),
                subject="Hello",
                body_text="World",
                snippet="World",
            )
            return type(
                "Receipt",
                (),
                {
                    "connection": connection,
                    "thread_id": thread_id or "provider-thread",
                    "message": message,
                    "continuity_note": "Sent back into the same provider thread.",
                },
            )()

    assert BeginMailboxOAuthUseCase(FakeMailboxProvider()).execute(
        provider="gmail",
        redirect_uri="https://app.example/callback",
        state="state-123",
    ).startswith("https://example.test/oauth/gmail")
    with pytest.raises(ValueError, match="Unsupported mailbox provider"):
        BeginMailboxOAuthUseCase(FakeMailboxProvider()).execute(
            provider="imap",
            redirect_uri="https://app.example/callback",
            state="state-123",
        )
    with pytest.raises(ValueError, match="redirect_uri is required"):
        BeginMailboxOAuthUseCase(FakeMailboxProvider()).execute(
            provider="gmail",
            redirect_uri=" ",
            state="state-123",
        )
    with pytest.raises(ValueError, match="state is required"):
        BeginMailboxOAuthUseCase(FakeMailboxProvider()).execute(
            provider="gmail",
            redirect_uri="https://app.example/callback",
            state=" ",
        )

    with pytest.raises(ValueError, match="Unsupported mailbox provider"):
        CompleteMailboxOAuthUseCase(repository=repository, mailbox_provider=FakeMailboxProvider()).execute(
            user,
            provider="imap",
            code="code",
            redirect_uri="https://app.example/callback",
        )

    completed = CompleteMailboxOAuthUseCase(
        repository=repository,
        mailbox_provider=FakeMailboxProvider(),
    ).execute(
        user,
        provider="gmail",
        code="code",
        redirect_uri="https://app.example/callback",
    )
    assert completed.watch_status == "active"

    class WatchFailingProvider(FakeMailboxProvider):
        def ensure_watch_subscription(self, connection: MailboxConnection) -> MailboxConnection:
            raise RuntimeError("watch failed")

    completed_without_watch = CompleteMailboxOAuthUseCase(
        repository=repository,
        mailbox_provider=WatchFailingProvider(),
    ).execute(
        user,
        provider="gmail",
        code="code",
        redirect_uri="https://app.example/callback",
    )
    assert completed_without_watch.status == "connected"

    watched = ProcessMailboxWatchEventUseCase(
        repository=repository,
        now=lambda: now,
        mailbox_provider=FakeMailboxProvider(),
    ).execute(
        user,
        provider="gmail",
        connection_id=oauth_connection.id,
    )
    assert watched.connection.watch_event_count == 1
    assert watched.connection.last_watch_event_at == now

    watched_by_account = ProcessMailboxWatchEventUseCase(
        repository=repository,
        now=lambda: now,
        mailbox_provider=FakeMailboxProvider(),
    ).execute(
        user,
        provider="gmail",
        external_account_id="acct-123",
    )
    assert watched_by_account.connection.watch_event_count >= 1

    watched_by_email = ProcessMailboxWatchEventUseCase(
        repository=repository,
        now=lambda: now,
        mailbox_provider=FakeMailboxProvider(),
    ).execute(
        user,
        provider="gmail",
        email_address="ada@example.com",
    )
    assert watched_by_email.connection.email_address == "ada@example.com"

    with pytest.raises(KeyError):
        ProcessMailboxWatchEventUseCase(
            repository=repository,
            now=lambda: now,
            mailbox_provider=FakeMailboxProvider(),
        ).execute(user, provider="gmail", external_account_id="missing")


def test_ensure_watch_sync_send_and_helper_paths_are_covered() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()
    manual_connection = repository.save_mailbox_connection(
        user,
        make_mailbox_connection(provider="gmail", connection_mode="manual"),
    )
    oauth_connection = repository.save_mailbox_connection(
        user,
        make_mailbox_connection(
            provider="outlook",
            connection_mode="oauth",
            email_address="ada@outlook.example",
            watch_status="active",
            watch_expires_at=now + timedelta(minutes=30),
        ),
    )

    ensured_manual = EnsureMailboxWatchUseCase(repository=repository, mailbox_provider=None).execute(
        user,
        manual_connection.id,
    )
    assert ensured_manual.watch_status == "inactive"

    with pytest.raises(ValueError, match="integration is not configured"):
        EnsureMailboxWatchUseCase(repository=repository, mailbox_provider=None).execute(
            user,
            oauth_connection.id,
        )

    class FailingProvider:
        def ensure_watch_subscription(self, connection: MailboxConnection) -> MailboxConnection:
            raise RuntimeError("oauth expired")

    with pytest.raises(RuntimeError, match="oauth expired"):
        EnsureMailboxWatchUseCase(
            repository=repository,
            mailbox_provider=FailingProvider(),  # type: ignore[arg-type]
        ).execute(user, oauth_connection.id)
    saved_oauth = next(item for item in repository.list_mailbox_connections(user) if item.id == oauth_connection.id)
    assert saved_oauth.status == "needs_reauth"

    with pytest.raises(ValueError, match="integration is not configured"):
        SyncMailboxConnectionUseCase(
            repository=repository,
            now=lambda: now,
            mailbox_provider=None,
        ).execute(user, oauth_connection.id)

    manual_sync = SyncMailboxConnectionUseCase(
        repository=repository,
        now=lambda: now,
        mailbox_provider=None,
    ).execute(user, manual_connection.id)
    assert manual_sync.synced_threads >= 1

    empty_repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    empty_repository.clear_lead_follow_ups(user)
    empty_repository.save_mailbox_connection(
        user,
        make_mailbox_connection(provider="gmail", connection_mode="manual"),
    )
    empty_sync = SyncMailboxConnectionUseCase(
        repository=empty_repository,
        now=lambda: now,
        mailbox_provider=None,
    ).execute(user, "mailbox-gmail-test")
    assert empty_sync.synced_threads == 1

    with pytest.raises(ValueError, match="Email subject is required"):
        SendLeadFollowUpEmailUseCase(repository=repository, now=lambda: now).execute(
            user,
            "lead-riverbridge",
            subject=" ",
            body="Hello",
        )
    with pytest.raises(ValueError, match="Email body is required"):
        SendLeadFollowUpEmailUseCase(repository=repository, now=lambda: now).execute(
            user,
            "lead-riverbridge",
            subject="Hello",
            body=" ",
        )
    with pytest.raises(KeyError, match="missing"):
        SendLeadFollowUpEmailUseCase(repository=repository, now=lambda: now).execute(
            user,
            "lead-riverbridge",
            subject="Hello",
            body="Body",
            connection_id="missing",
        )

    no_email_repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    lead_without_email = next(
        item for item in no_email_repository.list_lead_follow_ups(user) if item.id == "lead-riverbridge"
    )
    no_email_repository.import_lead_follow_ups(user, [replace(lead_without_email, email_address="")])
    with pytest.raises(ValueError, match="does not have an email address"):
        SendLeadFollowUpEmailUseCase(repository=no_email_repository, now=lambda: now).execute(
            user,
            "lead-riverbridge",
            subject="Hello",
            body="Body",
        )

    no_connection_repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    with pytest.raises(ValueError, match="Connect a mailbox before sending"):
        SendLeadFollowUpEmailUseCase(repository=no_connection_repository, now=lambda: now).execute(
            user,
            "lead-riverbridge",
            subject="Hello",
            body="Body",
        )

    repository.save_mailbox_connection(
        user,
        replace(manual_connection, status="attention_needed", health_note="Needs care"),
    )
    with pytest.raises(ValueError, match="needs attention"):
        SendLeadFollowUpEmailUseCase(repository=repository, now=lambda: now).execute(
            user,
            "lead-riverbridge",
            subject="Hello",
            body="Body",
            connection_id=manual_connection.id,
        )

    connected_manual = repository.save_mailbox_connection(
        user,
        replace(manual_connection, status="connected"),
    )
    sent = SendLeadFollowUpEmailUseCase(repository=repository, now=lambda: now).execute(
        user,
        "lead-riverbridge",
        subject="Hello",
        body="Body",
        connection_id=connected_manual.id,
    )
    assert sent.connection.sent_message_count == connected_manual.sent_message_count + 1

    lead = next(item for item in repository.list_lead_follow_ups(user) if item.id == "lead-riverbridge")
    thread = replace(
        lead.recent_email_threads[0],
        source="gmail",
        thread_id="gmail-thread",
        last_external_message_id="<msg@example.com>",
    )
    repository.import_lead_follow_ups(user, [replace(lead, recent_email_threads=(thread,))])

    class SendingProvider:
        def send_message(self, connection: MailboxConnection, **kwargs):  # type: ignore[no-untyped-def]
            message = MailboxThreadMessage(
                message_id="sent-1",
                external_message_id="<sent-1@example.com>",
                sent_at=now,
                direction="outbound",
                from_email=connection.email_address,
                from_name=connection.display_name,
                to_emails=("riverbridge@example.com",),
                subject=kwargs["subject"],
                body_text=kwargs["body"],
                snippet=kwargs["body"][:280],
            )
            return type(
                "Receipt",
                (),
                {
                    "connection": connection,
                    "thread_id": "gmail-thread",
                    "message": message,
                    "continuity_note": "",
                },
            )()

    oauth_ready = repository.save_mailbox_connection(
        user,
        replace(
            oauth_connection,
            provider="outlook",
            status="connected",
            connection_mode="oauth",
        ),
    )
    sent_with_mismatch = SendLeadFollowUpEmailUseCase(
        repository=repository,
        now=lambda: now,
        mailbox_provider=SendingProvider(),  # type: ignore[arg-type]
    ).execute(
        user,
        "lead-riverbridge",
        subject="Hello again",
        body="Body",
        connection_id=oauth_ready.id,
        thread_id="gmail-thread",
    )
    assert "attached to the Gmail thread" in sent_with_mismatch.continuity_note

    with pytest.raises(ValueError, match="integration is not configured"):
        SendLeadFollowUpEmailUseCase(
            repository=repository,
            now=lambda: now,
            mailbox_provider=None,
        ).execute(
            user,
            "lead-riverbridge",
            subject="Hello again",
            body="Body",
            connection_id=oauth_ready.id,
            thread_id="gmail-thread",
        )

    class FailingSender:
        def send_message(self, connection: MailboxConnection, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("oauth send failed")

    with pytest.raises(RuntimeError, match="oauth send failed"):
        SendLeadFollowUpEmailUseCase(
            repository=repository,
            now=lambda: now,
            mailbox_provider=FailingSender(),  # type: ignore[arg-type]
        ).execute(
            user,
            "lead-riverbridge",
            subject="Hello again",
            body="Body",
            connection_id=oauth_ready.id,
            thread_id="gmail-thread",
        )

    with pytest.raises(ValueError, match="mailbox connection id is required"):
        _require_mailbox_connection([], "")
    with pytest.raises(KeyError):
        _require_mailbox_connection([], "missing")
    with pytest.raises(ValueError, match="calendar connection id is required"):
        _require_calendar_connection([], "")
    with pytest.raises(KeyError):
        _require_calendar_connection([], "missing")
    with pytest.raises(ValueError, match="Reconnect this mailbox"):
        _ensure_mailbox_connection_sendable(replace(connected_manual, status="needs_reauth", reauth_required=True))
    assert _mailbox_watch_renewal_due(
        replace(
            oauth_ready,
            provider="gmail",
            watch_status="active",
            watch_expires_at=now + timedelta(minutes=30),
        )
    ) is True
    assert _mailbox_watch_renewal_due(replace(connected_manual, connection_mode="manual")) is False
    assert _mailbox_watch_renewal_due(replace(oauth_ready, provider="outlook")) is False
    attention_needed = _mark_mailbox_attention_needed(connected_manual, "oauth token expired")
    assert attention_needed.status == "needs_reauth"
    assert _resolve_mailbox_sync_cursor(
        [
            MailboxThreadSnapshot(
                source="gmail",
                thread_id="thread-1",
                messages=(
                    MailboxThreadMessage(
                        message_id="msg-1",
                        external_message_id="<msg-1@example.com>",
                        sent_at=now,
                        direction="inbound",
                        from_email="lead@example.com",
                        from_name="Lead",
                        to_emails=("ada@example.com",),
                        subject="Hello",
                        body_text="Body",
                        snippet="Body",
                    ),
                ),
            )
        ],
        now,
    ) == now.isoformat()
    assert _build_mailbox_sync_subject(lead).strip()
    assert _build_mailbox_sync_body(lead, "inbound").strip()
    assert _build_mailbox_sync_body(lead, "outbound").strip()
    assert _build_mailbox_sync_subject(replace(lead, recent_email_threads=(), company_name="Riverbridge")) == "Checking in on Riverbridge"
    assert _build_mailbox_sync_subject(replace(lead, recent_email_threads=(), company_name="")) == f"Checking in with {lead.lead_name}"
    assert (
        _build_mailbox_send_continuity_note(
            base_note="",
            selected_thread=thread,
            connection=oauth_ready,
        ).startswith("This note went out through")
    )


def test_calendar_ingest_validation_and_dto_helper_paths() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()
    repository.save_calendar_connection(user, make_calendar_connection())

    with pytest.raises(ValueError, match="Unsupported calendar provider"):
        IngestCalendarEventUseCase(repository=repository, now=lambda: now).execute(
            user,
            source="ical",
            connection_id=None,
            event=CalendarEventInput(
                event_id="evt-1",
                title="Kickoff",
                starts_at=now,
                attendee_emails=("lead@example.com",),
                notes="Prep",
            ),
        )
    with pytest.raises(ValueError, match="event_id is required"):
        IngestCalendarEventUseCase(repository=repository, now=lambda: now).execute(
            user,
            source="google_calendar",
            connection_id=None,
            event=CalendarEventInput(
                event_id=" ",
                title="Kickoff",
                starts_at=now,
                attendee_emails=("lead@example.com",),
                notes="Prep",
            ),
        )
    with pytest.raises(ValueError, match="title is required"):
        IngestCalendarEventUseCase(repository=repository, now=lambda: now).execute(
            user,
            source="google_calendar",
            connection_id=None,
            event=CalendarEventInput(
                event_id="evt-1",
                title=" ",
                starts_at=now,
                attendee_emails=("lead@example.com",),
                notes="Prep",
            ),
        )
    with pytest.raises(ValueError, match="At least one attendee email is required"):
        IngestCalendarEventUseCase(repository=repository, now=lambda: now).execute(
            user,
            source="google_calendar",
            connection_id=None,
            event=CalendarEventInput(
                event_id="evt-1",
                title="Kickoff",
                starts_at=now,
                attendee_emails=("bad",),
                notes="Prep",
            ),
        )

    overview = GetLeadFollowUpOverviewUseCase(repository=repository, now=lambda: now).execute(user)
    assert overview.items


def test_resolve_upcoming_meeting_covers_long_range_and_thread_subject_paths() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    sample = repository.list_lead_follow_ups(make_user())[0]

    far_future = replace(sample, next_follow_up_at=now + timedelta(days=30))
    assert _resolve_upcoming_meeting(far_future, now) == (None, "", "")

    thread_based = replace(
        sample,
        next_follow_up_at=now + timedelta(days=3),
        next_step="Follow up soon",
        recent_email_threads=(
            LeadEmailThreadSummary(
                source="gmail",
                thread_id="thread-1",
                subject="Call tomorrow about rollout",
                counterpart_email="lead@example.com",
                counterpart_name="Lead",
                last_message_at=now,
                last_message_direction="inbound",
                snippet="Preview",
                message_count=1,
                needs_reply=True,
                waiting_on_contact=False,
            ),
        ),
    )
    resolved = _resolve_upcoming_meeting(thread_based, now)
    assert resolved[0] == thread_based.next_follow_up_at
    assert resolved[2] == "email thread"


def test_sync_mailbox_connection_skips_empty_thread_snapshots() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()
    connection = repository.save_mailbox_connection(
        user,
        MailboxConnection(
            id="mailbox-gmail-oauth",
            provider="gmail",
            email_address="ada@example.com",
            display_name="Ada Lovelace",
            status="connected",
            connected_at=now,
            connection_mode="oauth",
            access_token="access-token",
            refresh_token="refresh-token",
            token_expires_at=now + timedelta(hours=1),
        ),
    )

    class EmptySnapshotProvider:
        def refresh_connection(self, mailbox_connection: MailboxConnection) -> MailboxConnection:
            return mailbox_connection

        def ensure_watch_subscription(self, mailbox_connection: MailboxConnection) -> MailboxConnection:
            return mailbox_connection

        def pull_thread_updates(self, mailbox_connection: MailboxConnection, max_results: int = 10) -> list[MailboxThreadSnapshot]:
            del mailbox_connection, max_results
            return [
                MailboxThreadSnapshot(
                    source="gmail",
                    thread_id="thread-empty",
                    messages=(),
                )
            ]

    result = SyncMailboxConnectionUseCase(
        repository=repository,
        mailbox_provider=EmptySnapshotProvider(),
        now=lambda: now,
    ).execute(user, connection.id)

    assert result.synced_threads == 0
