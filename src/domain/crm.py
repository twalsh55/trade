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
    owner_name: str
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


@dataclass(frozen=True)
class LeadImportIssue:
    row_number: int
    severity: str
    field: str | None
    message: str


@dataclass(frozen=True)
class LeadImportPreviewRow:
    row_number: int
    lead_name: str
    company_name: str
    owner_name: str
    stage: str
    next_follow_up_at: datetime | None
    notes: str
    duplicate: bool
    issues: tuple[LeadImportIssue, ...]


@dataclass(frozen=True)
class LeadImportHeaderMapping:
    original_header: str
    suggested_field: str | None
    mapped_field: str | None


@dataclass(frozen=True)
class LeadImportClarificationOption:
    value: str
    label: str


@dataclass(frozen=True)
class LeadImportClarificationQuestion:
    id: str
    prompt: str
    choices: tuple[LeadImportClarificationOption, ...]


@dataclass(frozen=True)
class LeadImportClarification:
    assistant_message: str
    required: bool
    questions: tuple[LeadImportClarificationQuestion, ...]


@dataclass(frozen=True)
class LeadImportPreview:
    source_type: str
    source_label: str
    normalized_headers: list[str]
    header_mappings: list[LeadImportHeaderMapping]
    available_fields: list[str]
    total_rows: int
    importable_rows: int
    duplicate_rows: int
    invalid_rows: int
    rows: list[LeadImportPreviewRow]
    issues: list[LeadImportIssue]
    clarification: LeadImportClarification | None = None


@dataclass(frozen=True)
class LeadImportCommitResult:
    imported_count: int
    skipped_duplicates: int
    skipped_invalid: int
    overview: LeadFollowUpOverview
