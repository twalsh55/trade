from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import pandas as pd

from src.application.account import AlertHistoryEntry, UserDashboardSettings
from src.application.billing import BillingOverview
from src.domain.auth import User
from src.domain.crm import (
    LeadFollowUp,
    LeadFollowUpOverview,
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
    crm_ai_prompt: str
    crm_preferred_import_formats: list[str]
    crm_image_intake_channels: list[str]
    crm_image_intake_notes: str


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
    stage: str
    priority: str
    contact_channel: str
    last_contacted_at: str | None
    next_follow_up_at: str
    next_step: str
    notes: str
    timeline: list["LeadTimelineEntryDTO"]


@dataclass(frozen=True)
class LeadTimelineEntryDTO:
    id: str
    occurred_at: str
    kind: str
    channel: str
    summary: str


@dataclass(frozen=True)
class LeadFollowUpOverviewDTO:
    generated_at: str
    total_open: int
    due_today: int
    overdue: int
    high_priority: int
    items: list[LeadFollowUpDTO]


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
    next_follow_up_at: str | None
    notes: str
    duplicate: bool
    issues: list[LeadImportIssueDTO]


@dataclass(frozen=True)
class LeadImportHeaderMappingDTO:
    original_header: str
    suggested_field: str | None
    mapped_field: str | None


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
        crm_ai_prompt=settings.crm_ai_prompt,
        crm_preferred_import_formats=list(settings.crm_preferred_import_formats),
        crm_image_intake_channels=list(settings.crm_image_intake_channels),
        crm_image_intake_notes=settings.crm_image_intake_notes,
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
    )


def build_lead_follow_up_dto(item: LeadFollowUp) -> LeadFollowUpDTO:
    return LeadFollowUpDTO(
        id=item.id,
        lead_name=item.lead_name,
        company_name=item.company_name,
        owner_name=item.owner_name,
        stage=item.stage,
        priority=item.priority,
        contact_channel=item.contact_channel,
        last_contacted_at=item.last_contacted_at.isoformat() if item.last_contacted_at else None,
        next_follow_up_at=item.next_follow_up_at.isoformat(),
        next_step=item.next_step,
        notes=item.notes,
        timeline=[build_lead_timeline_entry_dto(entry) for entry in item.timeline],
    )


def build_lead_timeline_entry_dto(entry: LeadTimelineEntry) -> LeadTimelineEntryDTO:
    return LeadTimelineEntryDTO(
        id=entry.id,
        occurred_at=entry.occurred_at.isoformat(),
        kind=entry.kind,
        channel=entry.channel,
        summary=entry.summary,
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
    )


def build_lead_import_preview_row_dto(row: LeadImportPreviewRow) -> LeadImportPreviewRowDTO:
    return LeadImportPreviewRowDTO(
        row_number=row.row_number,
        lead_name=row.lead_name,
        company_name=row.company_name,
        owner_name=row.owner_name,
        stage=row.stage,
        next_follow_up_at=row.next_follow_up_at.isoformat() if row.next_follow_up_at else None,
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
