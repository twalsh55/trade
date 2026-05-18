from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from psycopg import OperationalError

from src.adapters.crm.in_memory_follow_up_repository import InMemoryLeadFollowUpRepository
from src.adapters.crm import runtime as crm_runtime
from src.adapters.crm.oauth_mailbox_provider import OAuthMailboxProviderAdapter
from src.domain.auth import User
from src.domain.crm import CalendarConnection, MailboxConnection


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


def test_in_memory_lead_follow_up_repository_supports_complete_snooze_and_notes() -> None:
    user = make_user()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)

    items = repository.list_lead_follow_ups(user)
    assert len(items) == 4

    # Returned items are defensive copies, not direct references.
    first = items[0]
    with pytest.raises(FrozenInstanceError):
        first.notes = "mutated"  # type: ignore[misc]
    fresh_items = repository.list_lead_follow_ups(user)
    assert fresh_items[0].notes != "mutated"
    assert fresh_items[0].timeline

    repository.snooze_lead_follow_up(user, "lead-riverbridge", datetime(2024, 5, 7, 12, 30, tzinfo=UTC))
    riverbridge = next(item for item in repository.list_lead_follow_ups(user) if item.id == "lead-riverbridge")
    assert riverbridge.next_follow_up_at == datetime(2024, 5, 7, 12, 30, tzinfo=UTC)

    repository.append_note_to_lead_follow_up(user, "lead-riverbridge", "Needs a lighter rollout framing.", now)
    riverbridge = next(item for item in repository.list_lead_follow_ups(user) if item.id == "lead-riverbridge")
    assert riverbridge.notes == "Needs a lighter rollout framing."
    assert riverbridge.timeline[0].kind == "internal_note"
    assert riverbridge.timeline[0].summary == "Needs a lighter rollout framing."
    assert riverbridge.owner_name == "Ada Lovelace"

    repository.complete_lead_follow_up(user, "lead-amber-studio", now)
    assert all(item.id != "lead-amber-studio" for item in repository.list_lead_follow_ups(user))

    with pytest.raises(KeyError):
        repository.complete_lead_follow_up(user, "missing-id", now)

    with pytest.raises(KeyError):
        repository.snooze_lead_follow_up(user, "missing-id", now)

    with pytest.raises(KeyError):
        repository.append_note_to_lead_follow_up(user, "missing-id", "note", now)

    imported = replace(
        riverbridge,
        id="lead-imported",
        lead_name="Taylor Brooks",
        company_name="Beacon Ridge",
        owner_name="Samir Patel",
    )
    assert repository.import_lead_follow_ups(user, [imported]) == 1
    imported_row = next(item for item in repository.list_lead_follow_ups(user) if item.id == "lead-imported")
    assert imported_row.owner_name == "Samir Patel"

    mailbox = MailboxConnection(
        id="mailbox-gmail-test",
        provider="gmail",
        email_address="ada@example.com",
        display_name="Ada Lovelace",
        status="connected",
        connected_at=now,
        connection_mode="manual",
    )
    saved_mailbox = repository.save_mailbox_connection(user, mailbox)
    assert repository.list_mailbox_connections(user) == [saved_mailbox]
    repository.delete_mailbox_connection(user, mailbox.id)
    assert repository.list_mailbox_connections(user) == []
    with pytest.raises(KeyError):
        repository.delete_mailbox_connection(user, mailbox.id)

    calendar = CalendarConnection(
        id="calendar-google-test",
        provider="google_calendar",
        calendar_address="ada@example.com",
        display_name="Ada Calendar",
        status="connected",
        connected_at=now,
    )
    saved_calendar = repository.save_calendar_connection(user, calendar)
    assert repository.list_calendar_connections(user) == [saved_calendar]
    repository.delete_calendar_connection(user, calendar.id)
    assert repository.list_calendar_connections(user) == []
    with pytest.raises(KeyError):
        repository.delete_calendar_connection(user, calendar.id)

    repository.clear_lead_follow_ups(user)
    assert repository.list_lead_follow_ups(user) == []
    assert repository.list_mailbox_connection_user_ids() == []


def test_build_lead_follow_up_repository_returns_singleton(monkeypatch) -> None:
    crm_runtime.build_lead_follow_up_repository.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    first = crm_runtime.build_lead_follow_up_repository()
    second = crm_runtime.build_lead_follow_up_repository()
    assert first is second
    crm_runtime.build_lead_follow_up_repository.cache_clear()


def test_build_lead_follow_up_repository_uses_postgres_when_database_url_is_set(monkeypatch) -> None:
    crm_runtime.build_lead_follow_up_repository.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgres://example")

    class FakeRepository:
        def __init__(self, database_url: str) -> None:
            self.database_url = database_url
            self.ensured = False

        def ensure_schema(self) -> None:
            self.ensured = True

    monkeypatch.setattr(crm_runtime, "PostgresLeadFollowUpRepository", FakeRepository)

    repository = crm_runtime.build_lead_follow_up_repository()

    assert repository.database_url == "postgres://example"
    assert repository.ensured is True
    crm_runtime.build_lead_follow_up_repository.cache_clear()


def test_build_lead_follow_up_repository_raises_clear_error_when_crm_database_is_unavailable(monkeypatch) -> None:
    crm_runtime.build_lead_follow_up_repository.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgres://example")

    class BrokenRepository:
        def __init__(self, database_url: str) -> None:
            self.database_url = database_url

        def ensure_schema(self) -> None:
            raise OperationalError("down")

    monkeypatch.setattr(crm_runtime, "PostgresLeadFollowUpRepository", BrokenRepository)

    with pytest.raises(RuntimeError, match="CRM database is unavailable"):
        crm_runtime.build_lead_follow_up_repository()
    crm_runtime.build_lead_follow_up_repository.cache_clear()


def test_build_crm_image_intake_agent_from_env_uses_app_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_OPENAI_API_KEY", "app-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = crm_runtime.build_crm_image_intake_agent_from_env()

    assert agent.api_key == "app-key"
    assert agent.model == "gpt-4.1-mini"


def test_build_crm_image_intake_agent_from_env_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="no app OpenAI key is configured"):
        crm_runtime.build_crm_image_intake_agent_from_env()


def test_build_crm_spreadsheet_assist_agent_from_env_uses_app_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_OPENAI_API_KEY", "app-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = crm_runtime.build_crm_spreadsheet_assist_agent_from_env()

    assert agent.api_key == "app-key"
    assert agent.model == "gpt-4.1-mini"


def test_build_crm_spreadsheet_assist_agent_from_env_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="AI spreadsheet header assistance is unavailable"):
        crm_runtime.build_crm_spreadsheet_assist_agent_from_env()


def test_build_mailbox_provider_from_env_returns_oauth_adapter() -> None:
    crm_runtime.build_mailbox_provider_from_env.cache_clear()
    provider = crm_runtime.build_mailbox_provider_from_env()
    assert isinstance(provider, OAuthMailboxProviderAdapter)
    crm_runtime.build_mailbox_provider_from_env.cache_clear()
