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
class LeadEmailThreadSummary:
    thread_id: str
    subject: str
    counterpart_name: str
    counterpart_email: str
    last_message_at: datetime
    last_message_direction: str
    message_count: int
    snippet: str
    needs_reply: bool
    waiting_on_contact: bool
    last_message_id: str = ""
    last_external_message_id: str = ""
    memory_summary: str = ""
    next_touch_hint: str = ""
    open_loop: str = ""
    relationship_pulse: str = ""
    continuity_span: str = ""
    recent_change_hint: str = ""
    carry_forward_hint: str = ""
    unresolved_hint: str = ""
    continuity_memory: str = ""


@dataclass(frozen=True)
class LeadRelationshipSummary:
    active_count: int
    warm_count: int
    drifting_count: int
    stale_count: int
    at_risk_count: int
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
class LeadInboxSummary:
    connected_contact_count: int
    active_thread_count: int
    needs_reply_count: int
    waiting_on_contact_count: int
    stale_thread_count: int
    auto_created_contact_count: int


@dataclass(frozen=True)
class MailboxConnection:
    id: str
    provider: str
    email_address: str
    display_name: str
    status: str
    connected_at: datetime
    connection_mode: str = "manual"
    external_account_id: str = ""
    access_token: str = ""
    refresh_token: str = ""
    token_expires_at: datetime | None = None
    scope: str = ""
    sync_cursor: str = ""
    last_sync_at: datetime | None = None
    last_sync_status: str = ""
    last_sync_error: str = ""
    last_synced_thread_count: int = 0
    sent_message_count: int = 0
    background_sync_enabled: bool = True
    last_watch_event_at: datetime | None = None
    watch_event_count: int = 0
    watch_status: str = "inactive"
    watch_expires_at: datetime | None = None
    reauth_required: bool = False
    health_note: str = ""
    last_sent_at: datetime | None = None


@dataclass(frozen=True)
class MailboxThreadMessage:
    message_id: str
    sent_at: datetime
    direction: str
    from_email: str
    from_name: str
    to_emails: tuple[str, ...]
    subject: str
    body_text: str
    snippet: str
    external_message_id: str = ""


@dataclass(frozen=True)
class MailboxThreadSnapshot:
    source: str
    thread_id: str
    messages: tuple[MailboxThreadMessage, ...]


@dataclass(frozen=True)
class MailboxSendReceipt:
    connection: MailboxConnection
    thread_id: str
    message: MailboxThreadMessage


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
    email_address: str = ""
    referral_source_name: str = ""
    birthday: date | None = None
    company_milestone_name: str = ""
    company_milestone_date: date | None = None
    last_meaningful_interaction_at: datetime | None = None
    relationship_health_score: int = 0
    relationship_health_label: str = ""
    relationship_state: str = ""
    relationship_timing_nudge: str = ""
    relationship_context_summary: str = ""
    relationship_recent_changes_summary: str = ""
    relationship_recent_upload_summary: str = ""
    relationship_upload_follow_through_hint: str = ""
    relationship_last_30_days_summary: str = ""
    relationship_meeting_prep_summary: str = ""
    relationship_upcoming_meeting_at: datetime | None = None
    relationship_upcoming_meeting_label: str = ""
    relationship_upcoming_meeting_source: str = ""
    relationship_reconnect_why_now: str = ""
    relationship_reconnect_next_move: str = ""
    relationship_reconnect_message_hint: str = ""
    dormant: bool = False
    relationship_reminders: tuple[LeadRelationshipReminder, ...] = ()
    recent_email_threads: tuple[LeadEmailThreadSummary, ...] = ()


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
    inbox_summary: LeadInboxSummary | None = None


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
class MailboxSyncResult:
    connection: MailboxConnection
    synced_threads: int
    created_contacts: int
    updated_relationships: int
    overview: LeadFollowUpOverview


@dataclass(frozen=True)
class MailboxSendResult:
    connection: MailboxConnection
    follow_up_id: str
    thread_id: str
    sent_at: datetime
    overview: LeadFollowUpOverview


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
