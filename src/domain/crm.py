from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class LeadTimelineEntry:
    id: str
    occurred_at: datetime
    kind: str
    channel: str
    summary: str


@dataclass(frozen=True)
class LeadRelationshipReminder:
    kind: str
    title: str
    message: str
    due_at: datetime | None


@dataclass(frozen=True)
class LeadWarmIntroConnection:
    source_name: str
    target_lead_id: str
    target_lead_name: str
    target_company_name: str
    owner_name: str


@dataclass(frozen=True)
class LeadRelationshipSummary:
    healthy_count: int
    watch_count: int
    at_risk_count: int
    dormant_count: int
    referral_reminder_count: int
    milestone_reminder_count: int
    warm_intro_connections: list[LeadWarmIntroConnection]


@dataclass(frozen=True)
class LeadPipelineStageSummary:
    stage: str
    lead_count: int
    overdue_count: int
    due_this_week_count: int
    high_priority_count: int
    dormant_count: int


@dataclass(frozen=True)
class LeadPipelineSummary:
    stage_summaries: list[LeadPipelineStageSummary]


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
    referral_source_name: str = ""
    birthday: date | None = None
    company_milestone_name: str = ""
    company_milestone_date: date | None = None
    last_meaningful_interaction_at: datetime | None = None
    relationship_health_score: int = 0
    relationship_health_label: str = ""
    dormant: bool = False
    relationship_reminders: tuple[LeadRelationshipReminder, ...] = ()


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
    relationship_summary: LeadRelationshipSummary | None = None
    pipeline_summary: LeadPipelineSummary | None = None


@dataclass(frozen=True)
class LeadFollowUpEmailDraft:
    follow_up_id: str
    objective: str
    tone: str
    length: str
    subject: str
    body: str
    rationale: tuple[str, ...]


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
    priority: str
    contact_channel: str
    next_follow_up_at: datetime | None
    next_step: str
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
