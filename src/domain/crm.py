from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LeadTimelineEntry:
    id: str
    occurred_at: datetime
    kind: str
    channel: str
    summary: str


@dataclass(frozen=True)
class LeadFollowUp:
    id: str
    lead_name: str
    company_name: str
    stage: str
    priority: str
    contact_channel: str
    last_contacted_at: datetime | None
    next_follow_up_at: datetime
    next_step: str
    notes: str
    timeline: tuple[LeadTimelineEntry, ...]


@dataclass(frozen=True)
class LeadFollowUpActionResult:
    follow_up_id: str
    action: str
    effective_at: datetime


@dataclass(frozen=True)
class LeadFollowUpOverview:
    generated_at: datetime
    total_open: int
    due_today: int
    overdue: int
    high_priority: int
    items: list[LeadFollowUp]
