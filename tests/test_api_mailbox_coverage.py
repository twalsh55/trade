from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import src.adapters.api.app as api_app_module
from src.adapters.api.app import ApiDependencies, _build_mailbox_oauth_state, _validate_mailbox_oauth_state, _validate_mailbox_watch_secret, create_app
from src.adapters.crm.in_memory_follow_up_repository import InMemoryLeadFollowUpRepository
from src.domain.crm import MailboxConnection
from tests.test_api_app import FakeAuthUseCase, FakeMailboxProvider, FakeUserRepository, make_dashboard_result, make_user


def make_client(
    *,
    repository: InMemoryLeadFollowUpRepository | None = None,
    mailbox_provider=None,
    user_repository=None,
) -> TestClient:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    user = make_user()
    app = create_app(
        ApiDependencies(
            auth_use_case_factory=lambda: FakeAuthUseCase(user=user),
            market_data_factory=lambda: None,
            personalization_repository_factory=lambda: __import__("src.adapters.persistence.in_memory_personalization_repository", fromlist=["InMemoryPersonalizationRepository"]).InMemoryPersonalizationRepository(),
            lead_follow_up_repository_factory=lambda: repository or InMemoryLeadFollowUpRepository(now=lambda: now),
            mailbox_provider_factory=lambda: mailbox_provider or FakeMailboxProvider(),
            billing_port_factory=lambda: None,
            user_repository_factory=lambda: user_repository or FakeUserRepository(user=user),
            now=lambda: now,
        )
    )
    return TestClient(app)


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_mailbox_oauth_state_and_watch_secret_helpers_cover_validation_branches(monkeypatch) -> None:
    user = make_user()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)

    monkeypatch.delenv("CRM_INTAKE_SECRET", raising=False)
    monkeypatch.delenv("INTERNAL_CRON_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="state-signing secret"):
        _build_mailbox_oauth_state(user, "gmail", now)
    with pytest.raises(ValueError, match="state-signing secret"):
        _validate_mailbox_oauth_state(user, "gmail", "bad", now)

    monkeypatch.setenv("CRM_INTAKE_SECRET", "crm-secret")
    state = _build_mailbox_oauth_state(user, "gmail", now)
    _validate_mailbox_oauth_state(user, "gmail", state, now)

    with pytest.raises(ValueError, match="invalid"):
        _validate_mailbox_oauth_state(user, "gmail", "bad", now)
    invalid_timestamp_state = f"{user.id}:gmail:not-a-timestamp:signature"
    with pytest.raises(ValueError, match="invalid"):
        _validate_mailbox_oauth_state(user, "gmail", invalid_timestamp_state, now)
    with pytest.raises(ValueError, match="current account"):
        other_user = make_user()
        object.__setattr__(other_user, "id", UUID(int=other_user.id.int + 1))
        _validate_mailbox_oauth_state(other_user, "gmail", state, now)
    with pytest.raises(ValueError, match="this provider"):
        _validate_mailbox_oauth_state(user, "outlook", state, now)
    with pytest.raises(ValueError, match="verification failed"):
        _validate_mailbox_oauth_state(user, "gmail", state[:-1] + "0", now)
    with pytest.raises(ValueError, match="expired"):
        _validate_mailbox_oauth_state(user, "gmail", state, now + timedelta(hours=2))

    monkeypatch.setenv("MAILBOX_WATCH_WEBHOOK_SECRET", "watch-secret")
    _validate_mailbox_watch_secret("watch-secret")
    with pytest.raises(api_app_module.HTTPException) as exc_info:
        _validate_mailbox_watch_secret("wrong")
    assert exc_info.value.status_code == 401


def test_account_privacy_and_mailbox_watch_routes_cover_error_paths(monkeypatch) -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    client = make_client(repository=repository)

    confirm_response = client.post(
        "/api/account/privacy/erase",
        headers=auth_headers(),
        json={"confirm": False, "scope": "relationship_memory"},
    )
    assert confirm_response.status_code == 422

    class ValueErrorRepository(InMemoryLeadFollowUpRepository):
        def clear_lead_follow_ups(self, user):  # type: ignore[no-untyped-def]
            raise ValueError("erase failed")

    failing_erase_client = make_client(repository=ValueErrorRepository(now=lambda: now))
    scope_response = failing_erase_client.post(
        "/api/account/privacy/erase",
        headers=auth_headers(),
        json={"confirm": True, "scope": "relationship_memory"},
    )
    assert scope_response.status_code == 422

    success_response = client.post(
        "/api/account/privacy/erase",
        headers=auth_headers(),
        json={"confirm": True, "scope": "relationship_memory"},
    )
    assert success_response.status_code == 200
    assert success_response.json() == {"erased": True, "scope": "relationship_memory"}

    monkeypatch.setenv("MAILBOX_WATCH_WEBHOOK_SECRET", "watch-secret")
    invalid_secret = client.post(
        "/api/crm/inbox/watch-events/gmail",
        headers={api_app_module.MAILBOX_WATCH_SECRET_HEADER: "wrong"},
        json={"connection_id": "mailbox-gmail-oauth"},
    )
    assert invalid_secret.status_code == 401

    unavailable_app = create_app(
        ApiDependencies(
            auth_use_case_factory=lambda: FakeAuthUseCase(user=make_user()),
            market_data_factory=lambda: None,
            personalization_repository_factory=lambda: __import__("src.adapters.persistence.in_memory_personalization_repository", fromlist=["InMemoryPersonalizationRepository"]).InMemoryPersonalizationRepository(),
            lead_follow_up_repository_factory=lambda: object(),
            mailbox_provider_factory=lambda: FakeMailboxProvider(),
            billing_port_factory=lambda: None,
            user_repository_factory=lambda: None,
            now=lambda: now,
        )
    )
    unavailable_client = TestClient(unavailable_app)
    unavailable_response = unavailable_client.post(
        "/api/crm/inbox/watch-events/gmail",
        headers={api_app_module.MAILBOX_WATCH_SECRET_HEADER: "watch-secret"},
        json={"connection_id": "mailbox-gmail-oauth"},
    )
    assert unavailable_response.status_code == 503

    not_found_response = client.post(
        "/api/crm/inbox/watch-events/gmail",
        headers={api_app_module.MAILBOX_WATCH_SECRET_HEADER: "watch-secret"},
        json={"connection_id": "missing"},
    )
    assert not_found_response.status_code == 404

    class WatchLoopRepository(InMemoryLeadFollowUpRepository):
        def list_mailbox_connection_user_ids(self):  # type: ignore[no-untyped-def]
            return [make_user().id, UUID(int=make_user().id.int + 1)]

    class WatchValueErrorRepository(WatchLoopRepository):
        def list_mailbox_connections(self, user):  # type: ignore[no-untyped-def]
            if user.id == make_user().id:
                return [
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
                    )
                ]
            return []

    class FailingWatchProvider(FakeMailboxProvider):
        def refresh_connection(self, connection: MailboxConnection) -> MailboxConnection:
            raise ValueError("watch processing failed")

    watch_value_error_client = make_client(
        repository=WatchValueErrorRepository(now=lambda: now),
        mailbox_provider=FailingWatchProvider(),
        user_repository=FakeUserRepository(user=make_user()),
    )
    watch_value_error = watch_value_error_client.post(
        "/api/crm/inbox/watch-events/gmail",
        headers={api_app_module.MAILBOX_WATCH_SECRET_HEADER: "watch-secret"},
        json={"connection_id": "mailbox-gmail-oauth"},
    )
    assert watch_value_error.status_code == 422

    first_user = make_user()
    second_user = make_user()
    object.__setattr__(second_user, "id", UUID("22222222-2222-2222-2222-222222222222"))

    class WatchBranchRepository(InMemoryLeadFollowUpRepository):
        def list_mailbox_connection_user_ids(self):  # type: ignore[no-untyped-def]
            return [UUID("33333333-3333-3333-3333-333333333333"), first_user.id, second_user.id]

        def list_mailbox_connections(self, user):  # type: ignore[no-untyped-def]
            if user.id == second_user.id:
                return [
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
                    )
                ]
            return []

    class BranchUserRepository:
        def get_user_by_id(self, user_id: UUID):  # type: ignore[no-untyped-def]
            if user_id == first_user.id:
                return first_user
            if user_id == second_user.id:
                return second_user
            return None

    watch_branch_client = make_client(
        repository=WatchBranchRepository(now=lambda: now),
        mailbox_provider=FakeMailboxProvider(),
        user_repository=BranchUserRepository(),
    )
    watch_branch_response = watch_branch_client.post(
        "/api/crm/inbox/watch-events/gmail",
        headers={api_app_module.MAILBOX_WATCH_SECRET_HEADER: "watch-secret"},
        json={"connection_id": "mailbox-gmail-oauth"},
    )
    assert watch_branch_response.status_code == 200
    assert watch_branch_response.json()["connection"]["id"] == "mailbox-gmail-oauth"


def test_calendar_and_mailbox_routes_cover_validation_and_missing_connection_paths(monkeypatch) -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    user = make_user()
    repository.save_mailbox_connection(
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
    client = make_client(repository=repository)

    bad_calendar = client.post(
        "/api/crm/calendars/connect",
        headers=auth_headers(),
        json={"provider": "google_calendar", "calendar_address": "bad", "display_name": "Ada"},
    )
    assert bad_calendar.status_code == 422

    missing_calendar_delete = client.delete(
        "/api/crm/calendars/missing",
        headers=auth_headers(),
    )
    assert missing_calendar_delete.status_code == 404

    missing_calendar_patch = client.patch(
        "/api/crm/calendars/missing",
        headers=auth_headers(),
        json={"background_sync_enabled": True},
    )
    assert missing_calendar_patch.status_code == 404

    bad_calendar_event = client.post(
        "/api/crm/calendars/events",
        headers=auth_headers(),
        json={
            "provider": "google_calendar",
            "event_id": "evt-1",
            "title": "Kickoff",
            "starts_at": now.isoformat(),
            "attendee_emails": ["bad"],
            "notes": "Prep",
        },
    )
    assert bad_calendar_event.status_code == 422

    monkeypatch.delenv("CRM_INTAKE_SECRET", raising=False)
    monkeypatch.delenv("INTERNAL_CRON_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    oauth_start_unavailable = client.post(
        "/api/crm/inbox/mailboxes/oauth/start",
        headers=auth_headers(),
        json={"provider": "gmail"},
    )
    assert oauth_start_unavailable.status_code == 422

    monkeypatch.setenv("CRM_INTAKE_SECRET", "crm-secret")
    bad_oauth_complete = client.post(
        "/api/crm/inbox/mailboxes/oauth/complete",
        headers=auth_headers(),
        json={"provider": "gmail", "code": "auth-code", "state": "bad"},
    )
    assert bad_oauth_complete.status_code == 422

    bad_mailbox_connect = client.post(
        "/api/crm/inbox/mailboxes/connect",
        headers=auth_headers(),
        json={"provider": "gmail", "email_address": "bad", "display_name": "Ada"},
    )
    assert bad_mailbox_connect.status_code == 422

    missing_mailbox_patch = client.patch(
        "/api/crm/inbox/mailboxes/missing",
        headers=auth_headers(),
        json={"background_sync_enabled": True},
    )
    assert missing_mailbox_patch.status_code == 404

    missing_mailbox_delete = client.delete(
        "/api/crm/inbox/mailboxes/missing",
        headers=auth_headers(),
    )
    assert missing_mailbox_delete.status_code == 404


def test_mailbox_watch_sync_and_send_routes_cover_error_paths() -> None:
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

    class FailingMailboxProvider(FakeMailboxProvider):
        def ensure_watch_subscription(self, connection: MailboxConnection) -> MailboxConnection:
            raise RuntimeError("oauth expired")

    watch_client = make_client(repository=repository, mailbox_provider=FailingMailboxProvider())
    renew_response = watch_client.post(
        f"/api/crm/inbox/mailboxes/{connection.id}/watch",
        headers=auth_headers(),
    )
    assert renew_response.status_code == 422

    class ValueErrorWatchProvider(FakeMailboxProvider):
        def ensure_watch_subscription(self, connection: MailboxConnection) -> MailboxConnection:
            raise ValueError("watch config missing")

    renew_value_error_client = make_client(repository=repository, mailbox_provider=ValueErrorWatchProvider())
    renew_value_error = renew_value_error_client.post(
        f"/api/crm/inbox/mailboxes/{connection.id}/watch",
        headers=auth_headers(),
    )
    assert renew_value_error.status_code == 422

    missing_watch = watch_client.post(
        "/api/crm/inbox/mailboxes/missing/watch",
        headers=auth_headers(),
    )
    assert missing_watch.status_code == 404

    sync_response = watch_client.post(
        f"/api/crm/inbox/mailboxes/{connection.id}/sync",
        headers=auth_headers(),
    )
    assert sync_response.status_code == 422

    missing_sync = watch_client.post(
        "/api/crm/inbox/mailboxes/missing/sync",
        headers=auth_headers(),
    )
    assert missing_sync.status_code == 404

    send_missing_followup = watch_client.post(
        "/api/crm/followups/missing/send",
        headers=auth_headers(),
        json={
            "connection_id": connection.id,
            "thread_id": "thread-1",
            "subject": "Hello",
            "body": "World",
        },
    )
    assert send_missing_followup.status_code == 404

    send_missing_connection = watch_client.post(
        "/api/crm/followups/lead-riverbridge/send",
        headers=auth_headers(),
        json={
            "connection_id": "missing",
            "thread_id": "thread-1",
            "subject": "Hello",
            "body": "World",
        },
    )
    assert send_missing_connection.status_code == 404

    class FailingSendProvider(FakeMailboxProvider):
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
            del connection, to_email, to_name, subject, body, thread_id, reply_to_external_message_id
            raise RuntimeError("provider send failed")

    send_client = make_client(repository=repository, mailbox_provider=FailingSendProvider())
    send_value_error = send_client.post(
        "/api/crm/followups/lead-riverbridge/send",
        headers=auth_headers(),
        json={
            "connection_id": connection.id,
            "thread_id": "thread-1",
            "subject": "Hello",
            "body": "World",
        },
    )
    assert send_value_error.status_code == 422
