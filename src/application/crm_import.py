from __future__ import annotations

import csv
import io
import re
from dataclasses import replace
from datetime import UTC, datetime, time
from typing import Callable
from urllib.parse import quote_plus

from src.application.ports import CRMImageIntakePort, CRMSpreadsheetAssistPort, LeadFollowUpRepositoryPort
from src.domain.auth import User
from src.domain.crm import (
    LeadFollowUp,
    LeadFollowUpOverview,
    LeadImportClarification,
    LeadImportCommitResult,
    LeadImportHeaderMapping,
    LeadImportIssue,
    LeadImportPreview,
    LeadImportPreviewRow,
    LeadTimelineEntry,
)

HEADER_ALIASES = {
    "lead_name": {
        "lead",
        "lead name",
        "contact",
        "contact name",
        "full name",
        "name",
        "prospect",
        "customer",
    },
    "company_name": {
        "account",
        "account name",
        "business",
        "company",
        "company name",
        "organization",
        "org",
    },
    "owner_name": {
        "account owner",
        "assignee",
        "deal owner",
        "lead owner",
        "owner",
        "rep",
        "sales owner",
    },
    "stage": {
        "pipeline",
        "pipeline stage",
        "stage",
        "status",
    },
    "next_follow_up_at": {
        "due date",
        "follow up",
        "follow-up",
        "follow-up at",
        "follow-up date",
        "next contact",
        "next follow up",
        "next follow-up",
        "next step due",
        "next touch",
    },
    "notes": {
        "comment",
        "comments",
        "context",
        "memo",
        "note",
        "notes",
        "summary",
    },
    "priority": {
        "priority",
        "urgency",
    },
    "contact_channel": {
        "channel",
        "contact channel",
        "source channel",
    },
    "next_step": {
        "action",
        "follow-up task",
        "next action",
        "next step",
        "task",
    },
}

DATETIME_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %I:%M %p",
    "%d.%m.%Y",
    "%d.%m.%Y %H:%M",
)

CANONICAL_IMPORT_FIELDS = (
    "lead_name",
    "company_name",
    "owner_name",
    "stage",
    "next_follow_up_at",
    "notes",
    "priority",
    "contact_channel",
    "next_step",
)


class PreviewLeadImportUseCase:
    def __init__(self, repository: LeadFollowUpRepositoryPort, now: Callable[[], datetime]) -> None:
        self.repository = repository
        self.now = now

    def execute(
        self,
        user: User,
        csv_content: str,
        source_type: str,
        source_label: str,
        field_mapping_overrides: dict[str, str | None] | None = None,
    ) -> LeadImportPreview:
        existing_items = self.repository.list_lead_follow_ups(user)
        return _build_preview(csv_content, source_type, source_label, existing_items, field_mapping_overrides)


class PreviewLeadImportWithAssistanceUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
        spreadsheet_assist: CRMSpreadsheetAssistPort,
    ) -> None:
        self.repository = repository
        self.now = now
        self.spreadsheet_assist = spreadsheet_assist

    def execute(
        self,
        user: User,
        csv_content: str,
        source_type: str,
        source_label: str,
        prompt: str,
        preferred_formats: list[str],
        field_mapping_overrides: dict[str, str | None] | None = None,
        clarification_answers: dict[str, str] | None = None,
    ) -> LeadImportPreview:
        existing_items = self.repository.list_lead_follow_ups(user)
        try:
            preview = _build_preview(csv_content, source_type, source_label, existing_items, field_mapping_overrides)
        except ValueError as exc:
            if str(exc) != "No recognizable CRM headers were found in the spreadsheet.":
                raise
        else:
            if preview.importable_rows > 0 or not _needs_ai_header_assistance(preview.header_mappings):
                return preview

        headers, sample_rows = _extract_headers_and_sample_rows(csv_content)
        suggested_mapping, clarification = self.spreadsheet_assist.suggest_field_mapping(
            prompt=prompt,
            preferred_formats=preferred_formats,
            source_label=source_label,
            headers=headers,
            sample_rows=sample_rows,
            clarification_answers=clarification_answers,
        )
        merged_overrides = dict(suggested_mapping)
        if field_mapping_overrides:
            merged_overrides.update(field_mapping_overrides)
        preview = _build_preview(csv_content, source_type, source_label, existing_items, merged_overrides)
        if clarification:
            return replace(preview, clarification=clarification)
        return preview


class CommitLeadImportUseCase:
    def __init__(self, repository: LeadFollowUpRepositoryPort, now: Callable[[], datetime]) -> None:
        self.repository = repository
        self.now = now

    def execute(
        self,
        user: User,
        csv_content: str,
        source_type: str,
        source_label: str,
        field_mapping_overrides: dict[str, str | None] | None = None,
    ) -> LeadImportCommitResult:
        current_time = self.now()
        existing_items = self.repository.list_lead_follow_ups(user)
        preview = _build_preview(csv_content, source_type, source_label, existing_items, field_mapping_overrides)
        imported_items = [
            _build_imported_follow_up(row, preview.source_label, current_time)
            for row in preview.rows
            if not row.duplicate
            and not any(issue.severity == "error" for issue in row.issues)
            and row.next_follow_up_at is not None
        ]
        imported_count = self.repository.import_lead_follow_ups(user, imported_items)
        overview = _build_overview(self.repository.list_lead_follow_ups(user), current_time)
        return LeadImportCommitResult(
            imported_count=imported_count,
            skipped_duplicates=preview.duplicate_rows,
            skipped_invalid=preview.invalid_rows,
            overview=overview,
        )


class GenerateLeadImportFromImageUseCase:
    def __init__(self, image_intake: CRMImageIntakePort) -> None:
        self.image_intake = image_intake

    def execute(
        self,
        prompt: str,
        preferred_formats: list[str],
        file_name: str,
        file_bytes: bytes,
    ) -> str:
        return self.image_intake.extract_spreadsheet_rows_from_image(
            prompt=prompt,
            preferred_formats=preferred_formats,
            file_name=file_name,
            file_bytes=file_bytes,
        )


def _build_preview(
    csv_content: str,
    source_type: str,
    source_label: str,
    existing_items: list[LeadFollowUp],
    field_mapping_overrides: dict[str, str | None] | None = None,
) -> LeadImportPreview:
    normalized_content = csv_content.strip()
    if not normalized_content:
        raise ValueError("Spreadsheet content is required.")

    try:
        reader = csv.DictReader(io.StringIO(normalized_content, newline=""))
        if not reader.fieldnames:
            raise ValueError("The spreadsheet must include a header row.")
    except csv.Error as exc:
        raise ValueError(
            "This spreadsheet export could not be parsed as CSV. Re-export it as CSV or clean up broken line breaks first."
        ) from exc

    suggested_map = _build_suggested_field_map(reader.fieldnames)
    field_map = _build_field_map(reader.fieldnames, suggested_map, field_mapping_overrides)
    normalized_headers = [field_map.get(header, _slug_header(header)) for header in reader.fieldnames]
    if not any(canonical in field_map.values() for canonical in ("lead_name", "company_name", "next_follow_up_at", "notes")):
        raise ValueError("No recognizable CRM headers were found in the spreadsheet.")
    header_mappings = [
        LeadImportHeaderMapping(
            original_header=header,
            suggested_field=suggested_map.get(header),
            mapped_field=field_map.get(header),
        )
        for header in reader.fieldnames
    ]

    existing_keys = {_build_duplicate_key(item.lead_name, item.company_name) for item in existing_items}
    rows: list[LeadImportPreviewRow] = []
    issues: list[LeadImportIssue] = []

    try:
        for row_number, row in enumerate(reader, start=2):
            preview_row = _build_preview_row(row_number, row, field_map, existing_keys)
            rows.append(preview_row)
            issues.extend(preview_row.issues)
    except csv.Error as exc:
        raise ValueError(
            "This spreadsheet export could not be parsed as CSV. Re-export it as CSV or clean up broken line breaks first."
        ) from exc

    duplicate_rows = sum(1 for row in rows if row.duplicate)
    invalid_rows = sum(1 for row in rows if any(issue.severity == "error" for issue in row.issues))
    importable_rows = sum(
        1
        for row in rows
        if not row.duplicate and not any(issue.severity == "error" for issue in row.issues)
    )
    return LeadImportPreview(
        source_type=source_type,
        source_label=source_label,
        normalized_headers=normalized_headers,
        header_mappings=header_mappings,
        available_fields=list(CANONICAL_IMPORT_FIELDS),
        total_rows=len(rows),
        importable_rows=importable_rows,
        duplicate_rows=duplicate_rows,
        invalid_rows=invalid_rows,
        rows=rows,
        issues=issues,
    )


def _extract_headers_and_sample_rows(csv_content: str, sample_limit: int = 3) -> tuple[list[str], list[dict[str, str]]]:
    normalized_content = csv_content.strip()
    if not normalized_content:
        raise ValueError("Spreadsheet content is required.")

    try:
        reader = csv.DictReader(io.StringIO(normalized_content, newline=""))
        if not reader.fieldnames:
            raise ValueError("The spreadsheet must include a header row.")
        sample_rows: list[dict[str, str]] = []
        for raw_row in reader:
            sample_rows.append(
                {
                    header: str(raw_row.get(header) or "").strip()
                    for header in reader.fieldnames
                }
            )
            if len(sample_rows) >= sample_limit:
                break
        return list(reader.fieldnames), sample_rows
    except csv.Error as exc:
        raise ValueError(
            "This spreadsheet export could not be parsed as CSV. Re-export it as CSV or clean up broken line breaks first."
        ) from exc


def _needs_ai_header_assistance(header_mappings: list[LeadImportHeaderMapping]) -> bool:
    mapped_fields = {item.mapped_field for item in header_mappings if item.mapped_field}
    has_identity = "lead_name" in mapped_fields or "company_name" in mapped_fields
    has_follow_up = "next_follow_up_at" in mapped_fields
    return not has_identity or not has_follow_up


def _build_preview_row(
    row_number: int,
    raw_row: dict[str, str | None],
    field_map: dict[str, str],
    existing_keys: set[str],
) -> LeadImportPreviewRow:
    lead_name = _value_for(raw_row, field_map, "lead_name")
    company_name = _value_for(raw_row, field_map, "company_name")
    owner_name = _value_for(raw_row, field_map, "owner_name") or "Unassigned"
    stage = _normalize_stage(_value_for(raw_row, field_map, "stage"))
    priority = _normalize_priority(_value_for(raw_row, field_map, "priority"))
    contact_channel = _normalize_contact_channel(_value_for(raw_row, field_map, "contact_channel"))
    notes = _value_for(raw_row, field_map, "notes")
    next_follow_up_raw = _value_for(raw_row, field_map, "next_follow_up_at")
    next_follow_up_at = _parse_datetime(next_follow_up_raw)
    next_step = _value_for(raw_row, field_map, "next_step")
    row_issues: list[LeadImportIssue] = []

    if not lead_name and not company_name:
        row_issues.append(
            LeadImportIssue(
                row_number=row_number,
                severity="error",
                field="lead_name",
                message="Add a contact or company name so this row can become a CRM lead.",
            )
        )

    if not next_follow_up_raw:
        row_issues.append(
            LeadImportIssue(
                row_number=row_number,
                severity="error",
                field="next_follow_up_at",
                message="Add a next follow-up date so the row can enter the queue.",
            )
        )
    elif next_follow_up_at is None:
        row_issues.append(
            LeadImportIssue(
                row_number=row_number,
                severity="error",
                field="next_follow_up_at",
                message="Use a recognizable next follow-up date such as 2026-05-20 or 05/20/2026 14:00.",
            )
        )

    duplicate = False
    duplicate_key = _build_duplicate_key(lead_name, company_name)
    if duplicate_key and duplicate_key in existing_keys:
        duplicate = True
        row_issues.append(
            LeadImportIssue(
                row_number=row_number,
                severity="warning",
                field=None,
                message="This lead already exists in the current CRM queue and will be skipped.",
            )
        )
    elif duplicate_key:
        existing_keys.add(duplicate_key)

    if not notes:
        row_issues.append(
            LeadImportIssue(
                row_number=row_number,
                severity="warning",
                field="notes",
                message="No notes were provided. The row can still import, but the memory panel will start empty.",
            )
        )

    blocking_issues = tuple(issue for issue in row_issues if issue.severity == "error")
    warnings = tuple(issue for issue in row_issues if issue.severity == "warning")
    issues = blocking_issues + warnings

    return LeadImportPreviewRow(
        row_number=row_number,
        lead_name=lead_name or company_name or f"Imported lead {row_number}",
        company_name=company_name or "Unspecified company",
        owner_name=owner_name,
        stage=stage,
        priority=priority,
        contact_channel=contact_channel,
        next_follow_up_at=next_follow_up_at,
        next_step=next_step,
        notes=notes,
        duplicate=duplicate,
        issues=issues,
    )


def _build_imported_follow_up(row: LeadImportPreviewRow, source_label: str, imported_at: datetime) -> LeadFollowUp:
    if row.next_follow_up_at is None:
        raise ValueError("A next follow-up date is required before import.")
    slug = _slug_token(f"{row.lead_name}-{row.company_name}")
    next_step = row.next_step or f"{row.owner_name} to send the next follow-up and confirm the current {row.stage.lower()} status."
    import_summary = f"Imported from {source_label}. Owner: {row.owner_name}. Stage: {row.stage}."
    timeline: tuple[LeadTimelineEntry, ...] = (
        LeadTimelineEntry(
            id=f"{slug}-import-{int(imported_at.timestamp())}",
            occurred_at=imported_at,
            kind="import",
            channel=source_label.lower().replace(" ", "_"),
            summary=import_summary,
        ),
    )
    if row.notes:
        timeline = (
            timeline[0],
            LeadTimelineEntry(
                id=f"{slug}-note-{int(imported_at.timestamp())}",
                occurred_at=imported_at,
                kind="internal_note",
                channel="internal",
                summary=row.notes,
            ),
        )

    return LeadFollowUp(
        id=f"lead-import-{slug}-{quote_plus(str(row.row_number))}",
        lead_name=row.lead_name,
        company_name=row.company_name,
        owner_name=row.owner_name,
        stage=row.stage,
        priority=row.priority or _derive_priority(row.next_follow_up_at, imported_at),
        contact_channel=row.contact_channel or "spreadsheet",
        last_contacted_at=None,
        next_follow_up_at=row.next_follow_up_at,
        next_step=next_step,
        notes=row.notes or "Imported without notes.",
        timeline=timeline,
    )


def _build_overview(items: list[LeadFollowUp], current_time: datetime) -> LeadFollowUpOverview:
    ordered_items = sorted(items, key=lambda item: (item.next_follow_up_at, item.priority != "high", item.lead_name))
    current_date = current_time.date()
    return LeadFollowUpOverview(
        generated_at=current_time,
        total_open=len(ordered_items),
        due_today=sum(1 for item in ordered_items if item.next_follow_up_at.date() == current_date),
        overdue=sum(1 for item in ordered_items if item.next_follow_up_at < current_time),
        high_priority=sum(1 for item in ordered_items if item.priority == "high"),
        items=[replace(item) for item in ordered_items],
    )


def _build_suggested_field_map(headers: list[str]) -> dict[str, str]:
    field_map: dict[str, str] = {}
    for header in headers:
        slug = _slug_header(header)
        canonical = next(
            (
                name
                for name, aliases in HEADER_ALIASES.items()
                if slug == _slug_header(name) or slug in {_slug_header(alias) for alias in aliases}
            ),
            None,
        )
        if canonical is not None:
            field_map[header] = canonical
    return field_map


def _build_field_map(
    headers: list[str],
    suggested_map: dict[str, str],
    overrides: dict[str, str | None] | None,
) -> dict[str, str]:
    field_map: dict[str, str] = {}
    normalized_overrides = _normalize_field_mapping_overrides(headers, overrides)
    for header in headers:
        override = normalized_overrides.get(header)
        if override == "":
            continue
        if override is not None:
            field_map[header] = override
            continue
        suggested = suggested_map.get(header)
        if suggested is not None:
            field_map[header] = suggested
    return field_map


def _normalize_field_mapping_overrides(
    headers: list[str],
    overrides: dict[str, str | None] | None,
) -> dict[str, str]:
    if not overrides:
        return {}
    known_headers = set(headers)
    normalized: dict[str, str] = {}
    for raw_header, raw_field in overrides.items():
        if raw_header not in known_headers:
            continue
        candidate = str(raw_field or "").strip()
        if not candidate:
            normalized[raw_header] = ""
            continue
        if candidate not in CANONICAL_IMPORT_FIELDS:
            raise ValueError(f"Unsupported field mapping '{candidate}' for header '{raw_header}'.")
        normalized[raw_header] = candidate
    return normalized


def _value_for(raw_row: dict[str, str | None], field_map: dict[str, str], canonical_field: str) -> str:
    for header, mapped_field in field_map.items():
        if mapped_field != canonical_field:
            continue
        value = raw_row.get(header)
        if value is not None and value.strip():
            return value.strip()
    return ""


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        pass

    for fmt in DATETIME_FORMATS:
        try:
            parsed = datetime.strptime(normalized, fmt)
            if "H" not in fmt and "I" not in fmt:
                parsed = datetime.combine(parsed.date(), time(hour=9))
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _normalize_stage(value: str) -> str:
    normalized = value.strip() if value else ""
    if not normalized:
        return "Imported"
    return normalized[:1].upper() + normalized[1:]


def _normalize_priority(value: str) -> str:
    normalized = _slug_header(value)
    if normalized in {"high", "medium", "low"}:
        return normalized
    return ""


def _normalize_contact_channel(value: str) -> str:
    normalized = _slug_header(value)
    if not normalized:
        return ""
    return normalized.replace(" ", "_")


def _derive_priority(next_follow_up_at: datetime, imported_at: datetime) -> str:
    hours_until_due = (next_follow_up_at - imported_at).total_seconds() / 3600
    if hours_until_due <= 24:
        return "high"
    if hours_until_due <= 72:
        return "medium"
    return "low"


def _build_duplicate_key(lead_name: str, company_name: str) -> str:
    lead = _slug_header(lead_name)
    company = _slug_header(company_name)
    if not lead and not company:
        return ""
    return f"{lead}|{company}"


def _slug_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _slug_token(value: str) -> str:
    return _slug_header(value).replace(" ", "-")
