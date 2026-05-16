from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable

from src.application.ports import LeadFollowUpRepositoryPort
from src.domain.auth import User
from src.domain.crm import LeadFollowUp, LeadFollowUpActionResult, LeadFollowUpOverview


class GetLeadFollowUpOverviewUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User) -> LeadFollowUpOverview:
        current_time = self.now()
        items = self.repository.list_lead_follow_ups(user)
        ordered_items = sorted(items, key=lambda item: (item.next_follow_up_at, item.priority != "high", item.lead_name))
        current_date = current_time.date()

        return LeadFollowUpOverview(
            generated_at=current_time,
            total_open=len(ordered_items),
            due_today=sum(1 for item in ordered_items if item.next_follow_up_at.date() == current_date),
            overdue=sum(1 for item in ordered_items if item.next_follow_up_at < current_time),
            high_priority=sum(1 for item in ordered_items if item.priority == "high"),
            items=[_clone_follow_up(item) for item in ordered_items],
        )


def _clone_follow_up(item: LeadFollowUp) -> LeadFollowUp:
    return replace(item)


class CompleteLeadFollowUpUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User, follow_up_id: str) -> LeadFollowUpActionResult:
        completed_at = self.now()
        self.repository.complete_lead_follow_up(user, follow_up_id, completed_at)
        return LeadFollowUpActionResult(
            follow_up_id=follow_up_id,
            action="complete",
            effective_at=completed_at,
        )


class SnoozeLeadFollowUpUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User, follow_up_id: str, snooze_hours: int) -> LeadFollowUpActionResult:
        effective_at = self.now()
        self.repository.snooze_lead_follow_up(user, follow_up_id, effective_at + timedelta(hours=snooze_hours))
        return LeadFollowUpActionResult(
            follow_up_id=follow_up_id,
            action="snooze",
            effective_at=effective_at,
        )


class AddLeadFollowUpNoteUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User, follow_up_id: str, note_body: str) -> LeadFollowUpActionResult:
        normalized_note = note_body.strip()
        if not normalized_note:
            raise ValueError("Note body is required.")
        effective_at = self.now()
        self.repository.append_note_to_lead_follow_up(user, follow_up_id, normalized_note, effective_at)
        return LeadFollowUpActionResult(
            follow_up_id=follow_up_id,
            action="note",
            effective_at=effective_at,
        )
