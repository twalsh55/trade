from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import pandas as pd

from src.application.account import AlertHistoryEntry, UserDashboardSettings
from src.application.billing import BillingOverview
from src.domain.auth import User
from src.domain.crm import (
    CalendarConnection,
    LeadEmailThreadSummary,
    LeadFollowUp,
    LeadFollowUpEmailDraft,
    LeadFollowUpOverview,
    LeadInboxSummary,
    MailboxConnection,
    MailboxSendResult,
    MailboxSyncResult,
    LeadPipelineStageSummary,
    LeadPipelineSummary,
    LeadRelationshipReminder,
    LeadRelationshipSummary,
    LeadWarmIntroConnection,
    LeadImportClarification,
    LeadImportClarificationOption,
    LeadImportClarificationQuestion,
    LeadImportCommitResult,
    LeadImportHeaderMapping,
    LeadImportIssue,
    LeadImportPreview,
    LeadImportPreviewRow,
    LeadTimelineEntry,
)
from src.domain.models import DashboardConfig, DashboardResult
from src.domain.services import compute_buyer_participation_series, compute_new_high_ratio_series


@dataclass(frozen=True)
class AuthenticatedUserDTO:
    id: str
    email: str | None
    given_name: str | None
    family_name: str | None
    display_name: str | None
    auth_provider: str
    auth_issuer: str
    auth_subject: str
    created_at: str
    updated_at: str
    last_login_at: str


@dataclass(frozen=True)
class DashboardConfigDTO:
    universe: list[str]
    benchmark: str
    vix_symbol: str
    risk_proxy: str
    short_yield_symbol: str
    long_yield_symbol: str
    start_date: str
    end_date: str


@dataclass(frozen=True)
class IndicatorPercentileDTO:
    name: str
    current: float | None
    p5: float | None
    p50: float | None
    p95: float | None


@dataclass(frozen=True)
class PriceHistoryPointDTO:
    date: str
    price: float
    ma50: float | None
    ma200: float | None


@dataclass(frozen=True)
class MarketBreadthPointDTO:
    date: str
    buyer_participation_20d: float | None
    new_high_ratio_252: float | None


@dataclass(frozen=True)
class DashboardSnapshotDTO:
    config: DashboardConfigDTO
    refreshed_at: str
    regime: str
    risk_score: float
    actions: list[str]
    metrics: dict[str, float]
    risk_components: dict[str, float]
    indicator_percentiles: list[IndicatorPercentileDTO]
    price_history: list[PriceHistoryPointDTO]
    market_breadth_history: list[MarketBreadthPointDTO]


@dataclass(frozen=True)
class UserDashboardSettingsDTO:
    universe: list[str]
    benchmark: str
    vix_symbol: str
    risk_proxy: str
    short_yield_symbol: str
    long_yield_symbol: str
    lookback_years: int
    telegram_enabled: bool
    business_name: str
    business_website: str
    outbound_sender_name: str
    profile_alias: str
    business_logo_data_url: str
    onboarding_profile_deferred: bool
    crm_ai_prompt: str
    crm_preferred_import_formats: list[str]
    crm_image_intake_channels: list[str]
    crm_image_intake_notes: str
    preferred_language: str
    preferred_locale: str
    data_retention_days: int
    allow_ai_processing: bool
    privacy_consent_version: str
    privacy_consent_granted_at: str | None


@dataclass(frozen=True)
class AlertHistoryEntryDTO:
    occurred_at: str
    category: str
    severity: str
    title: str
    message: str


@dataclass(frozen=True)
class BillingOverviewDTO:
    enabled: bool
    customer_id: str | None
    subscription_id: str | None
    subscription_status: str | None
    price_id: str | None
    cancel_at_period_end: bool
    current_period_end: str | None
    checkout_available: bool
    portal_available: bool


@dataclass(frozen=True)
class LeadFollowUpDTO:
    id: str
    lead_name: str
    company_name: str
    owner_name: str
    email_address: str
    stage: str
    priority: str
    contact_channel: str
    last_contacted_at: str | None
    next_follow_up_at: str
    next_step: str
    notes: str
    timeline: list["LeadTimelineEntryDTO"]
    referral_source_name: str
    birthday: str | None
    company_milestone_name: str
    company_milestone_date: str | None
    last_meaningful_interaction_at: str | None
    relationship_health_score: int
    relationship_health_label: str
    relationship_state: str
    relationship_timing_nudge: str
    relationship_context_summary: str
    relationship_recent_changes_summary: str
    relationship_recent_upload_summary: str
    relationship_upload_follow_through_hint: str
    relationship_last_30_days_summary: str
    relationship_meeting_prep_summary: str
    relationship_upcoming_meeting_at: str | None
    relationship_upcoming_meeting_label: str
    relationship_upcoming_meeting_source: str
    relationship_reconnect_why_now: str
    relationship_reconnect_next_move: str
    relationship_reconnect_message_hint: str
    dormant: bool
    relationship_reminders: list["LeadRelationshipReminderDTO"]
    recent_email_threads: list["LeadEmailThreadSummaryDTO"]


@dataclass(frozen=True)
class LeadTimelineEntryDTO:
    id: str
    occurred_at: str
    kind: str
    channel: str
    summary: str


@dataclass(frozen=True)
class LeadRelationshipReminderDTO:
    kind: str
    title: str
    message: str
    due_at: str | None


@dataclass(frozen=True)
class LeadWarmIntroConnectionDTO:
    source_name: str
    target_lead_id: str
    target_lead_name: str
    target_company_name: str
    owner_name: str


@dataclass(frozen=True)
class LeadRelationshipSummaryDTO:
    active_count: int
    warm_count: int
    drifting_count: int
    stale_count: int
    at_risk_count: int
    referral_reminder_count: int
    milestone_reminder_count: int
    warm_intro_connections: list[LeadWarmIntroConnectionDTO]


@dataclass(frozen=True)
class LeadEmailThreadSummaryDTO:
    thread_id: str
    source: str
    subject: str
    counterpart_name: str
    counterpart_email: str
    last_message_id: str
    last_external_message_id: str
    last_message_at: str
    last_message_direction: str
    message_count: int
    snippet: str
    needs_reply: bool
    waiting_on_contact: bool
    memory_summary: str
    next_touch_hint: str
    open_loop: str
    relationship_pulse: str
    continuity_span: str
    recent_change_hint: str
    carry_forward_hint: str
    unresolved_hint: str
    continuity_memory: str


@dataclass(frozen=True)
class LeadPipelineStageSummaryDTO:
    stage: str
    lead_count: int
    overdue_count: int
    due_this_week_count: int
    high_priority_count: int
    dormant_count: int


@dataclass(frozen=True)
class LeadPipelineSummaryDTO:
    stage_summaries: list[LeadPipelineStageSummaryDTO]


@dataclass(frozen=True)
class LeadInboxSummaryDTO:
    connected_contact_count: int
    active_thread_count: int
    needs_reply_count: int
    waiting_on_contact_count: int
    stale_thread_count: int
    auto_created_contact_count: int


@dataclass(frozen=True)
class MailboxConnectionDTO:
    id: str
    provider: str
    email_address: str
    display_name: str
    status: str
    connected_at: str
    connection_mode: str
    external_account_id: str
    token_expires_at: str | None
    scope: str
    sync_cursor: str
    last_sync_at: str | None
    last_sync_status: str
    last_sync_error: str
    last_synced_thread_count: int
    sent_message_count: int
    background_sync_enabled: bool
    last_watch_event_at: str | None
    watch_event_count: int
    watch_status: str
    watch_expires_at: str | None
    reauth_required: bool
    health_note: str
    last_sent_at: str | None


@dataclass(frozen=True)
class CalendarConnectionDTO:
    id: str
    provider: str
    calendar_address: str
    display_name: str
    status: str
    connected_at: str
    connection_mode: str
    external_account_id: str
    last_sync_at: str | None
    last_sync_status: str
    last_sync_error: str
    background_sync_enabled: bool


@dataclass(frozen=True)
class MailboxSyncResultDTO:
    connection: MailboxConnectionDTO
    synced_threads: int
    created_contacts: int
    updated_relationships: int
    overview: "LeadFollowUpOverviewDTO"


@dataclass(frozen=True)
class MailboxSendResultDTO:
    connection: MailboxConnectionDTO
    follow_up_id: str
    thread_id: str
    sent_at: str
    overview: "LeadFollowUpOverviewDTO"


@dataclass(frozen=True)
class LeadFollowUpOverviewDTO:
    generated_at: str
    total_open: int
    due_today: int
    overdue: int
    high_priority: int
    items: list[LeadFollowUpDTO]
    relationship_summary: LeadRelationshipSummaryDTO | None
    pipeline_summary: LeadPipelineSummaryDTO | None
    inbox_summary: LeadInboxSummaryDTO | None


@dataclass(frozen=True)
class LeadFollowUpEmailDraftDTO:
    follow_up_id: str
    objective: str
    tone: str
    length: str
    subject: str
    body: str
    rationale: list[str]


@dataclass(frozen=True)
class LeadImportIssueDTO:
    row_number: int
    severity: str
    field: str | None
    message: str


@dataclass(frozen=True)
class LeadImportPreviewRowDTO:
    row_number: int
    lead_name: str
    company_name: str
    owner_name: str
    stage: str
    priority: str
    contact_channel: str
    next_follow_up_at: str | None
    next_step: str
    notes: str
    duplicate: bool
    issues: list[LeadImportIssueDTO]


@dataclass(frozen=True)
class LeadImportHeaderMappingDTO:
    original_header: str
    suggested_field: str | None
    mapped_field: str | None


@dataclass(frozen=True)
class LeadImportClarificationOptionDTO:
    value: str
    label: str


@dataclass(frozen=True)
class LeadImportClarificationQuestionDTO:
    id: str
    prompt: str
    choices: list[LeadImportClarificationOptionDTO]


@dataclass(frozen=True)
class LeadImportClarificationDTO:
    assistant_message: str
    required: bool
    questions: list[LeadImportClarificationQuestionDTO]


@dataclass(frozen=True)
class LeadImportPreviewDTO:
    source_type: str
    source_label: str
    normalized_headers: list[str]
    header_mappings: list[LeadImportHeaderMappingDTO]
    available_fields: list[str]
    total_rows: int
    importable_rows: int
    duplicate_rows: int
    invalid_rows: int
    rows: list[LeadImportPreviewRowDTO]
    issues: list[LeadImportIssueDTO]
    clarification: LeadImportClarificationDTO | None


@dataclass(frozen=True)
class LeadImportCommitResultDTO:
    imported_count: int
    skipped_duplicates: int
    skipped_invalid: int
    overview: LeadFollowUpOverviewDTO


def build_authenticated_user_dto(user: User) -> AuthenticatedUserDTO:
    return AuthenticatedUserDTO(
        id=str(user.id),
        email=user.email,
        given_name=user.given_name,
        family_name=user.family_name,
        display_name=user.display_name,
        auth_provider=user.auth_provider,
        auth_issuer=user.auth_issuer,
        auth_subject=user.auth_subject,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
        last_login_at=user.last_login_at.isoformat(),
    )


def build_dashboard_snapshot_dto(
    config: DashboardConfig,
    result: DashboardResult,
    refreshed_at: datetime,
) -> DashboardSnapshotDTO:
    benchmark_series = result.close_data[config.benchmark].dropna()
    ma50 = benchmark_series.rolling(50).mean()
    ma200 = benchmark_series.rolling(200).mean()
    buyer_participation = compute_buyer_participation_series(result.close_data).rolling(20).mean()
    new_high_ratio = compute_new_high_ratio_series(result.close_data)

    indicator_percentiles = [
        IndicatorPercentileDTO(
            name=str(row["Indicator"]),
            current=_optional_float(row["Current"]),
            p5=_optional_float(row["P5"]),
            p50=_optional_float(row["P50"]),
            p95=_optional_float(row["P95"]),
        )
        for _, row in result.indicator_percentiles.iterrows()
    ]

    price_history = [
        PriceHistoryPointDTO(
            date=_iso_date(index),
            price=float(price),
            ma50=_optional_float(ma50.loc[index]),
            ma200=_optional_float(ma200.loc[index]),
        )
        for index, price in benchmark_series.items()
    ]

    market_breadth_history = [
        MarketBreadthPointDTO(
            date=_iso_date(index),
            buyer_participation_20d=_optional_float(buyer_participation.loc[index]),
            new_high_ratio_252=_optional_float(new_high_ratio.loc[index]),
        )
        for index in buyer_participation.index.union(new_high_ratio.index)
    ]

    return DashboardSnapshotDTO(
        config=DashboardConfigDTO(
            universe=list(config.universe),
            benchmark=config.benchmark,
            vix_symbol=config.vix_symbol,
            risk_proxy=config.risk_proxy,
            short_yield_symbol=config.short_yield_symbol,
            long_yield_symbol=config.long_yield_symbol,
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
        ),
        refreshed_at=refreshed_at.isoformat(),
        regime=result.regime,
        risk_score=float(result.risk_score),
        actions=list(result.actions),
        metrics={name: float(value) for name, value in result.metrics.items()},
        risk_components={name: float(value) for name, value in result.risk_components.items()},
        indicator_percentiles=indicator_percentiles,
        price_history=price_history,
        market_breadth_history=market_breadth_history,
    )


def dto_to_dict(dto: object) -> dict[str, object]:
    return asdict(dto)


def build_user_dashboard_settings_dto(settings: UserDashboardSettings) -> UserDashboardSettingsDTO:
    return UserDashboardSettingsDTO(
        universe=list(settings.universe),
        benchmark=settings.benchmark,
        vix_symbol=settings.vix_symbol,
        risk_proxy=settings.risk_proxy,
        short_yield_symbol=settings.short_yield_symbol,
        long_yield_symbol=settings.long_yield_symbol,
        lookback_years=settings.lookback_years,
        telegram_enabled=settings.telegram_enabled,
        business_name=settings.business_name,
        business_website=settings.business_website,
        outbound_sender_name=settings.outbound_sender_name,
        profile_alias=settings.profile_alias,
        business_logo_data_url=settings.business_logo_data_url,
        onboarding_profile_deferred=settings.onboarding_profile_deferred,
        crm_ai_prompt=settings.crm_ai_prompt,
        crm_preferred_import_formats=list(settings.crm_preferred_import_formats),
        crm_image_intake_channels=list(settings.crm_image_intake_channels),
        crm_image_intake_notes=settings.crm_image_intake_notes,
        preferred_language=settings.preferred_language,
        preferred_locale=settings.preferred_locale,
        data_retention_days=settings.data_retention_days,
        allow_ai_processing=settings.allow_ai_processing,
        privacy_consent_version=settings.privacy_consent_version,
        privacy_consent_granted_at=settings.privacy_consent_granted_at.isoformat() if settings.privacy_consent_granted_at else None,
    )


def build_alert_history_entry_dto(entry: AlertHistoryEntry) -> AlertHistoryEntryDTO:
    return AlertHistoryEntryDTO(
        occurred_at=entry.occurred_at.isoformat(),
        category=entry.category,
        severity=entry.severity,
        title=entry.title,
        message=entry.message,
    )


def build_billing_overview_dto(overview: BillingOverview) -> BillingOverviewDTO:
    return BillingOverviewDTO(
        enabled=overview.enabled,
        customer_id=overview.customer_id,
        subscription_id=overview.subscription_id,
        subscription_status=overview.subscription_status,
        price_id=overview.price_id,
        cancel_at_period_end=overview.cancel_at_period_end,
        current_period_end=overview.current_period_end.isoformat() if overview.current_period_end else None,
        checkout_available=overview.checkout_available,
        portal_available=overview.portal_available,
    )


def build_lead_follow_up_overview_dto(overview: LeadFollowUpOverview) -> LeadFollowUpOverviewDTO:
    return LeadFollowUpOverviewDTO(
        generated_at=overview.generated_at.isoformat(),
        total_open=overview.total_open,
        due_today=overview.due_today,
        overdue=overview.overdue,
        high_priority=overview.high_priority,
        items=[build_lead_follow_up_dto(item) for item in overview.items],
        relationship_summary=build_lead_relationship_summary_dto(overview.relationship_summary),
        pipeline_summary=build_lead_pipeline_summary_dto(overview.pipeline_summary),
        inbox_summary=build_lead_inbox_summary_dto(overview.inbox_summary),
    )


def build_lead_follow_up_email_draft_dto(draft: LeadFollowUpEmailDraft) -> LeadFollowUpEmailDraftDTO:
    return LeadFollowUpEmailDraftDTO(
        follow_up_id=draft.follow_up_id,
        objective=draft.objective,
        tone=draft.tone,
        length=draft.length,
        subject=draft.subject,
        body=draft.body,
        rationale=list(draft.rationale),
    )


def build_lead_follow_up_dto(item: LeadFollowUp) -> LeadFollowUpDTO:
    return LeadFollowUpDTO(
        id=item.id,
        lead_name=item.lead_name,
        company_name=item.company_name,
        owner_name=item.owner_name,
        email_address=item.email_address,
        stage=item.stage,
        priority=item.priority,
        contact_channel=item.contact_channel,
        last_contacted_at=item.last_contacted_at.isoformat() if item.last_contacted_at else None,
        next_follow_up_at=item.next_follow_up_at.isoformat(),
        next_step=item.next_step,
        notes=item.notes,
        timeline=[build_lead_timeline_entry_dto(entry) for entry in item.timeline],
        referral_source_name=item.referral_source_name,
        birthday=item.birthday.isoformat() if item.birthday else None,
        company_milestone_name=item.company_milestone_name,
        company_milestone_date=item.company_milestone_date.isoformat() if item.company_milestone_date else None,
        last_meaningful_interaction_at=item.last_meaningful_interaction_at.isoformat() if item.last_meaningful_interaction_at else None,
        relationship_health_score=item.relationship_health_score,
        relationship_health_label=item.relationship_health_label,
        relationship_state=item.relationship_state,
        relationship_timing_nudge=item.relationship_timing_nudge,
        relationship_context_summary=item.relationship_context_summary,
        relationship_recent_changes_summary=item.relationship_recent_changes_summary,
        relationship_recent_upload_summary=item.relationship_recent_upload_summary,
        relationship_upload_follow_through_hint=item.relationship_upload_follow_through_hint,
        relationship_last_30_days_summary=item.relationship_last_30_days_summary,
        relationship_meeting_prep_summary=item.relationship_meeting_prep_summary,
        relationship_upcoming_meeting_at=item.relationship_upcoming_meeting_at.isoformat() if item.relationship_upcoming_meeting_at else None,
        relationship_upcoming_meeting_label=item.relationship_upcoming_meeting_label,
        relationship_upcoming_meeting_source=item.relationship_upcoming_meeting_source,
        relationship_reconnect_why_now=item.relationship_reconnect_why_now,
        relationship_reconnect_next_move=item.relationship_reconnect_next_move,
        relationship_reconnect_message_hint=item.relationship_reconnect_message_hint,
        dormant=item.dormant,
        relationship_reminders=[build_lead_relationship_reminder_dto(item) for item in item.relationship_reminders],
        recent_email_threads=[build_lead_email_thread_summary_dto(thread) for thread in item.recent_email_threads],
    )


def build_lead_timeline_entry_dto(entry: LeadTimelineEntry) -> LeadTimelineEntryDTO:
    return LeadTimelineEntryDTO(
        id=entry.id,
        occurred_at=entry.occurred_at.isoformat(),
        kind=entry.kind,
        channel=entry.channel,
        summary=entry.summary,
    )


def build_lead_relationship_reminder_dto(reminder: LeadRelationshipReminder) -> LeadRelationshipReminderDTO:
    return LeadRelationshipReminderDTO(
        kind=reminder.kind,
        title=reminder.title,
        message=reminder.message,
        due_at=reminder.due_at.isoformat() if reminder.due_at else None,
    )


def build_lead_relationship_summary_dto(
    summary: LeadRelationshipSummary | None,
) -> LeadRelationshipSummaryDTO | None:
    if summary is None:
        return None
    return LeadRelationshipSummaryDTO(
        active_count=summary.active_count,
        warm_count=summary.warm_count,
        drifting_count=summary.drifting_count,
        stale_count=summary.stale_count,
        at_risk_count=summary.at_risk_count,
        referral_reminder_count=summary.referral_reminder_count,
        milestone_reminder_count=summary.milestone_reminder_count,
        warm_intro_connections=[build_lead_warm_intro_connection_dto(item) for item in summary.warm_intro_connections],
    )


def build_lead_warm_intro_connection_dto(connection: LeadWarmIntroConnection) -> LeadWarmIntroConnectionDTO:
    return LeadWarmIntroConnectionDTO(
        source_name=connection.source_name,
        target_lead_id=connection.target_lead_id,
        target_lead_name=connection.target_lead_name,
        target_company_name=connection.target_company_name,
        owner_name=connection.owner_name,
    )


def build_lead_pipeline_summary_dto(summary: LeadPipelineSummary | None) -> LeadPipelineSummaryDTO | None:
    if summary is None:
        return None
    return LeadPipelineSummaryDTO(
        stage_summaries=[build_lead_pipeline_stage_summary_dto(item) for item in summary.stage_summaries],
    )


def build_lead_pipeline_stage_summary_dto(stage: LeadPipelineStageSummary) -> LeadPipelineStageSummaryDTO:
    return LeadPipelineStageSummaryDTO(
        stage=stage.stage,
        lead_count=stage.lead_count,
        overdue_count=stage.overdue_count,
        due_this_week_count=stage.due_this_week_count,
        high_priority_count=stage.high_priority_count,
        dormant_count=stage.dormant_count,
    )


def build_lead_email_thread_summary_dto(thread: LeadEmailThreadSummary) -> LeadEmailThreadSummaryDTO:
    return LeadEmailThreadSummaryDTO(
        thread_id=thread.thread_id,
        source=thread.source,
        subject=thread.subject,
        counterpart_name=thread.counterpart_name,
        counterpart_email=thread.counterpart_email,
        last_message_id=thread.last_message_id,
        last_external_message_id=thread.last_external_message_id,
        last_message_at=thread.last_message_at.isoformat(),
        last_message_direction=thread.last_message_direction,
        message_count=thread.message_count,
        snippet=thread.snippet,
        needs_reply=thread.needs_reply,
        waiting_on_contact=thread.waiting_on_contact,
        memory_summary=thread.memory_summary,
        next_touch_hint=thread.next_touch_hint,
        open_loop=thread.open_loop,
        relationship_pulse=thread.relationship_pulse,
        continuity_span=thread.continuity_span,
        recent_change_hint=thread.recent_change_hint,
        carry_forward_hint=thread.carry_forward_hint,
        unresolved_hint=thread.unresolved_hint,
        continuity_memory=thread.continuity_memory,
    )


def build_lead_inbox_summary_dto(summary: LeadInboxSummary | None) -> LeadInboxSummaryDTO | None:
    if summary is None:
        return None
    return LeadInboxSummaryDTO(
        connected_contact_count=summary.connected_contact_count,
        active_thread_count=summary.active_thread_count,
        needs_reply_count=summary.needs_reply_count,
        waiting_on_contact_count=summary.waiting_on_contact_count,
        stale_thread_count=summary.stale_thread_count,
        auto_created_contact_count=summary.auto_created_contact_count,
    )


def build_mailbox_connection_dto(connection: MailboxConnection) -> MailboxConnectionDTO:
    return MailboxConnectionDTO(
        id=connection.id,
        provider=connection.provider,
        email_address=connection.email_address,
        display_name=connection.display_name,
        status=connection.status,
        connected_at=connection.connected_at.isoformat(),
        connection_mode=connection.connection_mode,
        external_account_id=connection.external_account_id,
        token_expires_at=connection.token_expires_at.isoformat() if connection.token_expires_at else None,
        scope=connection.scope,
        sync_cursor=connection.sync_cursor,
        last_sync_at=connection.last_sync_at.isoformat() if connection.last_sync_at else None,
        last_sync_status=connection.last_sync_status,
        last_sync_error=connection.last_sync_error,
        last_synced_thread_count=connection.last_synced_thread_count,
        sent_message_count=connection.sent_message_count,
        background_sync_enabled=connection.background_sync_enabled,
        last_watch_event_at=connection.last_watch_event_at.isoformat() if connection.last_watch_event_at else None,
        watch_event_count=connection.watch_event_count,
        watch_status=connection.watch_status,
        watch_expires_at=connection.watch_expires_at.isoformat() if connection.watch_expires_at else None,
        reauth_required=connection.reauth_required,
        health_note=connection.health_note,
        last_sent_at=connection.last_sent_at.isoformat() if connection.last_sent_at else None,
    )


def build_calendar_connection_dto(connection: CalendarConnection) -> CalendarConnectionDTO:
    return CalendarConnectionDTO(
        id=connection.id,
        provider=connection.provider,
        calendar_address=connection.calendar_address,
        display_name=connection.display_name,
        status=connection.status,
        connected_at=connection.connected_at.isoformat(),
        connection_mode=connection.connection_mode,
        external_account_id=connection.external_account_id,
        last_sync_at=connection.last_sync_at.isoformat() if connection.last_sync_at else None,
        last_sync_status=connection.last_sync_status,
        last_sync_error=connection.last_sync_error,
        background_sync_enabled=connection.background_sync_enabled,
    )


def build_mailbox_sync_result_dto(result: MailboxSyncResult) -> MailboxSyncResultDTO:
    return MailboxSyncResultDTO(
        connection=build_mailbox_connection_dto(result.connection),
        synced_threads=result.synced_threads,
        created_contacts=result.created_contacts,
        updated_relationships=result.updated_relationships,
        overview=build_lead_follow_up_overview_dto(result.overview),
    )


def build_mailbox_send_result_dto(result: MailboxSendResult) -> MailboxSendResultDTO:
    return MailboxSendResultDTO(
        connection=build_mailbox_connection_dto(result.connection),
        follow_up_id=result.follow_up_id,
        thread_id=result.thread_id,
        sent_at=result.sent_at.isoformat(),
        overview=build_lead_follow_up_overview_dto(result.overview),
    )


def build_lead_import_preview_dto(preview: LeadImportPreview) -> LeadImportPreviewDTO:
    return LeadImportPreviewDTO(
        source_type=preview.source_type,
        source_label=preview.source_label,
        normalized_headers=list(preview.normalized_headers),
        header_mappings=[build_lead_import_header_mapping_dto(item) for item in preview.header_mappings],
        available_fields=list(preview.available_fields),
        total_rows=preview.total_rows,
        importable_rows=preview.importable_rows,
        duplicate_rows=preview.duplicate_rows,
        invalid_rows=preview.invalid_rows,
        rows=[build_lead_import_preview_row_dto(row) for row in preview.rows],
        issues=[build_lead_import_issue_dto(issue) for issue in preview.issues],
        clarification=build_lead_import_clarification_dto(preview.clarification),
    )


def build_lead_import_preview_row_dto(row: LeadImportPreviewRow) -> LeadImportPreviewRowDTO:
    return LeadImportPreviewRowDTO(
        row_number=row.row_number,
        lead_name=row.lead_name,
        company_name=row.company_name,
        owner_name=row.owner_name,
        stage=row.stage,
        priority=row.priority,
        contact_channel=row.contact_channel,
        next_follow_up_at=row.next_follow_up_at.isoformat() if row.next_follow_up_at else None,
        next_step=row.next_step,
        notes=row.notes,
        duplicate=row.duplicate,
        issues=[build_lead_import_issue_dto(issue) for issue in row.issues],
    )


def build_lead_import_header_mapping_dto(item: LeadImportHeaderMapping) -> LeadImportHeaderMappingDTO:
    return LeadImportHeaderMappingDTO(
        original_header=item.original_header,
        suggested_field=item.suggested_field,
        mapped_field=item.mapped_field,
    )


def build_lead_import_issue_dto(issue: LeadImportIssue) -> LeadImportIssueDTO:
    return LeadImportIssueDTO(
        row_number=issue.row_number,
        severity=issue.severity,
        field=issue.field,
        message=issue.message,
    )


def build_lead_import_clarification_dto(
    clarification: LeadImportClarification | None,
) -> LeadImportClarificationDTO | None:
    if clarification is None:
        return None
    return LeadImportClarificationDTO(
        assistant_message=clarification.assistant_message,
        required=clarification.required,
        questions=[build_lead_import_clarification_question_dto(item) for item in clarification.questions],
    )


def build_lead_import_clarification_question_dto(
    question: LeadImportClarificationQuestion,
) -> LeadImportClarificationQuestionDTO:
    return LeadImportClarificationQuestionDTO(
        id=question.id,
        prompt=question.prompt,
        choices=[build_lead_import_clarification_option_dto(item) for item in question.choices],
    )


def build_lead_import_clarification_option_dto(
    option: LeadImportClarificationOption,
) -> LeadImportClarificationOptionDTO:
    return LeadImportClarificationOptionDTO(
        value=option.value,
        label=option.label,
    )


def build_lead_import_commit_result_dto(result: LeadImportCommitResult) -> LeadImportCommitResultDTO:
    return LeadImportCommitResultDTO(
        imported_count=result.imported_count,
        skipped_duplicates=result.skipped_duplicates,
        skipped_invalid=result.skipped_invalid,
        overview=build_lead_follow_up_overview_dto(result.overview),
    )


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _iso_date(value: object) -> str:
    if hasattr(value, "date"):
        return value.date().isoformat()
    return str(value)
