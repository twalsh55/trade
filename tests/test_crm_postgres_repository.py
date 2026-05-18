from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from src.adapters.crm import postgres_follow_up_repository as repo_module
from src.adapters.crm.in_memory_follow_up_repository import build_seed_follow_ups
from src.adapters.crm.postgres_follow_up_repository import (
    PostgresLeadFollowUpRepository,
    _coerce_payload,
    _json_default,
    _parse_date,
    _parse_datetime,
    _payload_to_follow_up,
)
from src.domain.auth import User
from src.domain.crm import CalendarConnection, LeadRelationshipReminder, MailboxConnection


def make_user(*, anonymous: bool = False) -> User:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    return User(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        auth_provider="anonymous" if anonymous else "clerk",
        auth_issuer="https://example.clerk.accounts.dev",
        auth_subject="guest-crm" if anonymous else "user_123",
        stripe_customer_id=None,
        email=None if anonymous else "user@example.com",
        given_name="Guest" if anonymous else "Ada",
        family_name=None if anonymous else "Lovelace",
        display_name="Guest" if anonymous else "Ada Lovelace",
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


class FakeCursor:
    def __init__(self, *, fetchone_result=None, fetchall_result=None, rowcount: int = 0) -> None:
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.rowcount = rowcount
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


def test_postgres_lead_follow_up_repository_ensure_schema(monkeypatch) -> None:
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: connection)

    repository = PostgresLeadFollowUpRepository("postgres://example")
    repository.ensure_schema()

    assert len(cursor.executed) == 6
    assert "crm_lead_follow_up" in cursor.executed[0][0]
    assert "crm_lead_follow_up_user_updated_idx" in cursor.executed[1][0]
    assert "crm_mailbox_connection" in cursor.executed[2][0]
    assert "crm_mailbox_connection_user_updated_idx" in cursor.executed[3][0]
    assert "crm_calendar_connection" in cursor.executed[4][0]
    assert "crm_calendar_connection_user_updated_idx" in cursor.executed[5][0]
    assert connection.committed is True


def test_postgres_lead_follow_up_repository_round_trips_follow_ups(monkeypatch) -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    seed_item = build_seed_follow_ups(now)[0]
    upsert_connection = FakeConnection(FakeCursor())
    list_connection = FakeConnection(
        FakeCursor(
            fetchall_result=[
                {
                    "payload": json.dumps(asdict(seed_item), default=_json_default),
                }
            ]
        )
    )
    calls = [upsert_connection, list_connection]
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: calls.pop(0))

    repository = PostgresLeadFollowUpRepository("postgres://example", now=lambda: now)
    assert repository.import_lead_follow_ups(make_user(), [seed_item]) == 1
    items = repository.list_lead_follow_ups(make_user())

    assert items == [seed_item]
    assert upsert_connection.committed is True
    assert "INSERT INTO crm_lead_follow_up" in upsert_connection.cursor_instance.executed[0][0]


def test_postgres_lead_follow_up_repository_supports_complete_snooze_and_notes(monkeypatch) -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    user = make_user()
    item = build_seed_follow_ups(now)[1]

    snooze_load = FakeConnection(FakeCursor(fetchone_result={"payload": json.dumps(asdict(item), default=_json_default)}))
    snooze_save = FakeConnection(FakeCursor())
    note_load = FakeConnection(FakeCursor(fetchone_result={"payload": json.dumps(asdict(item), default=_json_default)}))
    note_save = FakeConnection(FakeCursor())
    delete_ok = FakeConnection(FakeCursor(rowcount=1))
    delete_missing = FakeConnection(FakeCursor(rowcount=0))
    missing_load = FakeConnection(FakeCursor(fetchone_result=None))
    calls = [snooze_load, snooze_save, note_load, note_save, delete_ok, delete_missing, missing_load]
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: calls.pop(0))

    repository = PostgresLeadFollowUpRepository("postgres://example", now=lambda: now)
    repository.snooze_lead_follow_up(user, item.id, now)
    repository.append_note_to_lead_follow_up(user, item.id, "Needs a lighter rollout framing.", now)
    repository.complete_lead_follow_up(user, item.id, now)

    snooze_payload = json.loads(snooze_save.cursor_instance.executed[0][1]["payload"])  # type: ignore[index]
    note_payload = json.loads(note_save.cursor_instance.executed[0][1]["payload"])  # type: ignore[index]
    assert snooze_payload["next_follow_up_at"] == now.isoformat()
    assert note_payload["notes"] == "Needs a lighter rollout framing."
    assert note_payload["timeline"][0]["kind"] == "internal_note"

    with pytest.raises(KeyError):
        repository.complete_lead_follow_up(user, item.id, now)

    with pytest.raises(KeyError):
        repository.snooze_lead_follow_up(user, item.id, now)


def test_postgres_lead_follow_up_repository_bootstraps_anonymous_guest_data(monkeypatch) -> None:
    repository = PostgresLeadFollowUpRepository("postgres://example", now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    captured: list[object] = []
    monkeypatch.setattr(repository, "_list_lead_follow_ups_for_user", lambda user_id: [] if not captured else list(captured))  # type: ignore[method-assign]
    monkeypatch.setattr(
        repository,
        "import_lead_follow_ups",
        lambda user, follow_ups: captured.extend(follow_ups) or len(follow_ups),
    )

    items = repository.list_lead_follow_ups(make_user(anonymous=True))

    assert len(items) == 4
    assert items[0].id == "lead-amber-studio"


def test_postgres_lead_follow_up_repository_does_not_bootstrap_non_anonymous_users(monkeypatch) -> None:
    repository = PostgresLeadFollowUpRepository("postgres://example")
    monkeypatch.setattr(repository, "_list_lead_follow_ups_for_user", lambda user_id: [])  # type: ignore[method-assign]

    items = repository.list_lead_follow_ups(make_user())

    assert items == []


def test_payload_helpers_cover_supported_and_invalid_shapes() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    item = build_seed_follow_ups(now)[0]
    item_with_reminder = replace(
        item,
        relationship_reminders=(
            LeadRelationshipReminder(
                kind="birthday",
                title="Birthday reminder",
                message="Send a thoughtful note.",
                due_at=now,
            ),
        ),
    )
    payload_json = json.dumps(asdict(item_with_reminder), default=_json_default)
    payload_dict = json.loads(payload_json)

    restored = _payload_to_follow_up(_coerce_payload(payload_json))
    restored_from_dict = _payload_to_follow_up(_coerce_payload(payload_dict))

    assert restored == item_with_reminder
    assert restored_from_dict == item_with_reminder
    assert _parse_datetime(now.isoformat()) == now
    assert _parse_datetime(now) == now
    assert _parse_datetime(None) is None
    assert _parse_date(date(2024, 5, 6).isoformat()) == date(2024, 5, 6)
    assert _parse_date(date(2024, 5, 6)) == date(2024, 5, 6)
    assert _parse_date(None) is None

    with pytest.raises(TypeError):
        _json_default(object())

    with pytest.raises(TypeError):
        _coerce_payload(123)


def test_postgres_lead_follow_up_repository_mailbox_and_calendar_connection_methods(monkeypatch) -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    user = make_user()
    mailbox = MailboxConnection(
        id="mailbox-gmail-test",
        provider="gmail",
        email_address="ada@example.com",
        display_name="Ada Lovelace",
        status="connected",
        connected_at=now,
        connection_mode="manual",
    )
    calendar = CalendarConnection(
        id="calendar-google-test",
        provider="google_calendar",
        calendar_address="ada@example.com",
        display_name="Ada Calendar",
        status="connected",
        connected_at=now,
    )
    list_mailboxes = FakeConnection(
        FakeCursor(
            fetchall_result=[{"payload": json.dumps(asdict(mailbox), default=_json_default)}]
        )
    )
    clear_followups = FakeConnection(FakeCursor())
    save_mailbox = FakeConnection(FakeCursor())
    delete_mailbox = FakeConnection(FakeCursor(rowcount=1))
    delete_mailbox_missing = FakeConnection(FakeCursor(rowcount=0))
    list_calendars = FakeConnection(
        FakeCursor(
            fetchall_result=[{"payload": json.dumps(asdict(calendar), default=_json_default)}]
        )
    )
    save_calendar = FakeConnection(FakeCursor())
    delete_calendar = FakeConnection(FakeCursor(rowcount=1))
    delete_calendar_missing = FakeConnection(FakeCursor(rowcount=0))
    list_user_ids = FakeConnection(FakeCursor(fetchall_result=[(str(user.id),)]))
    calls = [
        list_mailboxes,
        clear_followups,
        save_mailbox,
        delete_mailbox,
        delete_mailbox_missing,
        list_calendars,
        save_calendar,
        delete_calendar,
        delete_calendar_missing,
        list_user_ids,
    ]
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: calls.pop(0))

    repository = PostgresLeadFollowUpRepository("postgres://example", now=lambda: now)

    assert repository.list_mailbox_connections(user) == [mailbox]
    repository.clear_lead_follow_ups(user)
    assert clear_followups.committed is True
    assert repository.save_mailbox_connection(user, mailbox) == mailbox
    repository.delete_mailbox_connection(user, mailbox.id)
    with pytest.raises(KeyError):
        repository.delete_mailbox_connection(user, mailbox.id)

    assert repository.list_calendar_connections(user) == [calendar]
    assert repository.save_calendar_connection(user, calendar) == calendar
    repository.delete_calendar_connection(user, calendar.id)
    with pytest.raises(KeyError):
        repository.delete_calendar_connection(user, calendar.id)

    assert repository.list_mailbox_connection_user_ids() == [user.id]
