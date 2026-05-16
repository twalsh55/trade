from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from src.adapters.crm.in_memory_follow_up_repository import InMemoryLeadFollowUpRepository
from src.adapters.crm import runtime as crm_runtime
from src.domain.auth import User


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

    repository.complete_lead_follow_up(user, "lead-amber-studio", now)
    assert all(item.id != "lead-amber-studio" for item in repository.list_lead_follow_ups(user))

    with pytest.raises(KeyError):
        repository.complete_lead_follow_up(user, "missing-id", now)

    with pytest.raises(KeyError):
        repository.snooze_lead_follow_up(user, "missing-id", now)

    with pytest.raises(KeyError):
        repository.append_note_to_lead_follow_up(user, "missing-id", "note", now)


def test_build_lead_follow_up_repository_returns_singleton() -> None:
    crm_runtime._repository = None
    first = crm_runtime.build_lead_follow_up_repository()
    second = crm_runtime.build_lead_follow_up_repository()
    assert first is second
