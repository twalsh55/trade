from __future__ import annotations

import csv
from base64 import b64encode
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

import pandas as pd
import pytest

import src.adapters.api.app as api_app_module
from src.adapters.crm.google_sheets import build_google_sheets_csv_url
from src.adapters.crm.google_sheets import fetch_google_sheets_csv
from src.adapters.crm.in_memory_follow_up_repository import InMemoryLeadFollowUpRepository
from src.adapters.api.app import LeadImportPayload, _resolve_crm_import_source
from src.application.crm_import import (
    CommitLeadImportUseCase,
    PreviewLeadImportUseCase,
    PreviewLeadImportWithAssistanceUseCase,
    _build_duplicate_key,
    _build_imported_follow_up,
    _extract_headers_and_sample_rows,
    _needs_ai_header_assistance,
    _normalize_stage,
    _parse_datetime,
)
from src.domain.crm import LeadImportHeaderMapping
from src.domain.crm import LeadImportClarification
from src.domain.crm import LeadImportClarificationOption
from src.domain.crm import LeadImportClarificationQuestion
from src.domain.crm import LeadImportPreviewRow
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


def test_preview_lead_import_normalizes_headers_and_flags_duplicates() -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    preview = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC)).execute(
        make_user(),
        "Contact,Company,Owner,Status,Next Follow-Up,Notes\nTaylor Brooks,Beacon Ridge,Samir Patel,Qualification,2024-05-09,Imported from sheet\nAmber Flores,Northstar Studio,Ada Lovelace,Discovery,2024-05-10,Duplicate row\n",
        "csv",
        "CSV upload",
    )

    assert preview.normalized_headers[:3] == ["lead_name", "company_name", "owner_name"]
    assert preview.total_rows == 2
    assert preview.importable_rows == 1
    assert preview.duplicate_rows == 1
    assert preview.invalid_rows == 0
    assert preview.rows[0].owner_name == "Samir Patel"
    assert preview.rows[1].duplicate is True
    assert preview.header_mappings[0].original_header == "Contact"
    assert preview.header_mappings[0].mapped_field == "lead_name"
    assert "lead_name" in preview.available_fields


def test_commit_lead_import_adds_follow_ups_to_queue() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    result = CommitLeadImportUseCase(repository=repository, now=lambda: now).execute(
        make_user(),
        "contact,company,owner,status,next follow-up,notes\nTaylor Brooks,Beacon Ridge,Samir Patel,Qualification,2024-05-09,Imported from founder sheet\n",
        "csv",
        "CSV upload",
    )

    assert result.imported_count == 1
    imported = next(item for item in result.overview.items if item.company_name == "Beacon Ridge")
    assert imported.owner_name == "Samir Patel"
    assert imported.contact_channel == "spreadsheet"
    assert imported.timeline[0].kind == "import"


def test_preview_and_commit_lead_import_support_manual_field_mapping() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)
    preview_use_case = PreviewLeadImportUseCase(repository=repository, now=lambda: now)
    commit_use_case = CommitLeadImportUseCase(repository=repository, now=lambda: now)
    csv_content = (
        "Person,Organisation,Touchpoint,Blob\n"
        "Taylor Brooks,Summit Forge,2024-05-09,Imported from a messy client sheet\n"
    )

    with pytest.raises(ValueError, match="No recognizable CRM headers were found"):
        preview_use_case.execute(make_user(), csv_content, "csv", "CSV upload")

    overrides = {
        "Person": "lead_name",
        "Organisation": "company_name",
        "Touchpoint": "next_follow_up_at",
        "Blob": "notes",
    }
    preview = preview_use_case.execute(make_user(), csv_content, "csv", "CSV upload", overrides)
    assert preview.importable_rows == 1
    assert preview.header_mappings[0].mapped_field == "lead_name"

    result = commit_use_case.execute(make_user(), csv_content, "csv", "CSV upload", overrides)
    assert result.imported_count == 1
    imported = next(item for item in result.overview.items if item.company_name == "Summit Forge")
    assert imported.lead_name == "Taylor Brooks"
    assert imported.notes == "Imported from a messy client sheet"


def test_preview_lead_import_can_use_ai_assistance_for_messy_headers() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)

    class FakeAssist:
        def suggest_field_mapping(  # type: ignore[no-untyped-def]
            self,
            prompt,
            preferred_formats,
            source_label,
            headers,
            sample_rows,
            clarification_answers=None,
        ):
            assert headers == ["Person", "Organisation", "Touchpoint", "Blob"]
            assert sample_rows[0]["Person"] == "Taylor Brooks"
            assert source_label == "CSV upload"
            return (
                {
                    "Person": "lead_name",
                    "Organisation": "company_name",
                    "Touchpoint": "next_follow_up_at",
                    "Blob": "notes",
                },
                None,
            )

    preview = PreviewLeadImportWithAssistanceUseCase(
        repository=repository,
        now=lambda: now,
        spreadsheet_assist=FakeAssist(),
    ).execute(
        make_user(),
        "Person,Organisation,Touchpoint,Blob\nTaylor Brooks,Summit Forge,2024-05-09,Imported from a messy client sheet\n",
        "csv",
        "CSV upload",
        prompt="Focus on next follow-up and notes.",
        preferred_formats=["csv"],
    )

    assert preview.importable_rows == 1
    assert preview.header_mappings[0].mapped_field == "lead_name"
    assert preview.rows[0].company_name == "Summit Forge"


def test_preview_lead_import_with_assistance_returns_existing_preview_when_it_is_already_good() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)

    class FakeAssist:
        def suggest_field_mapping(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("AI assistance should not run for already importable previews.")

    preview = PreviewLeadImportWithAssistanceUseCase(
        repository=repository,
        now=lambda: now,
        spreadsheet_assist=FakeAssist(),
    ).execute(
        make_user(),
        "Contact,Company,Next Follow-Up,Notes\nTaylor Brooks,Summit Forge,2024-05-09,Imported cleanly\n",
        "csv",
        "CSV upload",
        prompt="Focus on next follow-up and notes.",
        preferred_formats=["csv"],
    )

    assert preview.importable_rows == 1


def test_preview_lead_import_with_assistance_reraises_non_header_errors() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)

    class FakeAssist:
        def suggest_field_mapping(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("AI assistance should not run for blank spreadsheet content.")

    use_case = PreviewLeadImportWithAssistanceUseCase(
        repository=repository,
        now=lambda: now,
        spreadsheet_assist=FakeAssist(),
    )

    with pytest.raises(ValueError, match="Spreadsheet content is required."):
        use_case.execute(make_user(), "   ", "csv", "CSV upload", prompt="prompt", preferred_formats=["csv"])


def test_preview_lead_import_with_assistance_keeps_manual_overrides_over_ai() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)

    class FakeAssist:
        def suggest_field_mapping(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return (
                {
                    "Person": "lead_name",
                    "Organisation": "company_name",
                    "Followup": "next_follow_up_at",
                    "Context": "notes",
                },
                None,
            )

    preview = PreviewLeadImportWithAssistanceUseCase(
        repository=repository,
        now=lambda: now,
        spreadsheet_assist=FakeAssist(),
    ).execute(
        make_user(),
        "Person,Organisation,Followup,Context\nTaylor Brooks,Summit Forge,2024-05-09,Imported from a messy client sheet\n",
        "csv",
        "CSV upload",
        prompt="prompt",
        preferred_formats=["csv"],
        field_mapping_overrides={"Context": ""},
    )

    context_mapping = next(item for item in preview.header_mappings if item.original_header == "Context")
    assert context_mapping.mapped_field is None


def test_preview_lead_import_with_assistance_can_return_clarification_questions() -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    repository = InMemoryLeadFollowUpRepository(now=lambda: now)

    class FakeAssist:
        def suggest_field_mapping(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return (
                {
                    "Person": "lead_name",
                    "Organisation": "company_name",
                    "Touchpoint": "next_follow_up_at",
                    "Context": "notes",
                },
                LeadImportClarification(
                    assistant_message="I can finish the import once I know whether Touchpoint means the next follow-up date or the last contact date.",
                    required=True,
                    questions=(
                        LeadImportClarificationQuestion(
                            id="touchpoint-meaning",
                            prompt="What does the Touchpoint column represent?",
                            choices=(
                                LeadImportClarificationOption(value="next-follow-up", label="Next follow-up date"),
                                LeadImportClarificationOption(value="last-contacted", label="Last contacted date"),
                            ),
                        ),
                    ),
                ),
            )

    preview = PreviewLeadImportWithAssistanceUseCase(
        repository=repository,
        now=lambda: now,
        spreadsheet_assist=FakeAssist(),
    ).execute(
        make_user(),
        "Person,Organisation,Touchpoint,Context\nTaylor Brooks,Summit Forge,2024-05-09,Imported from a messy client sheet\n",
        "csv",
        "CSV upload",
        prompt="prompt",
        preferred_formats=["csv"],
    )

    assert preview.clarification is not None
    assert preview.clarification.required is True
    assert preview.clarification.questions[0].id == "touchpoint-meaning"


def test_preview_lead_import_rejects_invalid_manual_field_mapping() -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    use_case = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))

    with pytest.raises(ValueError, match="Unsupported field mapping"):
        use_case.execute(
            make_user(),
            "Person,Due\nTaylor Brooks,2024-05-09\n",
            "csv",
            "CSV upload",
            {"Person": "unknown_field"},
        )


def test_preview_lead_import_supports_ignoring_auto_detected_headers_and_skips_unknown_override_headers() -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    use_case = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    preview = use_case.execute(
        make_user(),
        "Contact,Company,Notes\nTaylor Brooks,Beacon Ridge,Imported from sheet\n",
        "csv",
        "CSV upload",
        {"Notes": "", "Missing": "lead_name"},
    )

    notes_mapping = next(item for item in preview.header_mappings if item.original_header == "Notes")
    assert notes_mapping.mapped_field is None


def test_preview_lead_import_recognizes_canonical_machine_headers() -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    use_case = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    preview = use_case.execute(
        make_user(),
        "lead_name,company_name,owner_name,stage,next_follow_up_at,notes\n"
        "Taylor Brooks,Beacon Ridge,Samir Patel,Discovery,2024-05-09,Imported from image\n",
        "image",
        "telegram-photo.jpg",
    )

    assert preview.importable_rows == 1
    assert preview.rows[0].owner_name == "Samir Patel"


def test_build_google_sheets_csv_url_keeps_gid() -> None:
    csv_url = build_google_sheets_csv_url("https://docs.google.com/spreadsheets/d/abc123/edit#gid=456")
    assert csv_url == "https://docs.google.com/spreadsheets/d/abc123/export?format=csv&gid=456"


def test_preview_lead_import_rejects_blank_and_unrecognized_content() -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    use_case = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))

    with pytest.raises(ValueError, match="Spreadsheet content is required."):
        use_case.execute(make_user(), "   ", "csv", "CSV upload")

    with pytest.raises(ValueError, match="No recognizable CRM headers were found"):
        use_case.execute(make_user(), "foo,bar\n1,2\n", "csv", "CSV upload")


def test_extract_headers_and_sample_rows_returns_first_rows() -> None:
    headers, rows = _extract_headers_and_sample_rows(
        "Person,Organisation,Touchpoint\nTaylor Brooks,Summit Forge,2024-05-09\nAvery Hale,Northstar,2024-05-10\n"
    )

    assert headers == ["Person", "Organisation", "Touchpoint"]
    assert rows[0]["Person"] == "Taylor Brooks"
    assert rows[1]["Organisation"] == "Northstar"


def test_extract_headers_and_sample_rows_rejects_blank_or_headerless_content(monkeypatch) -> None:
    with pytest.raises(ValueError, match="Spreadsheet content is required."):
        _extract_headers_and_sample_rows("   ")

    class _Reader:
        fieldnames = None

        def __iter__(self):
            return iter(())

    monkeypatch.setattr("src.application.crm_import.csv.DictReader", lambda *args, **kwargs: _Reader())
    with pytest.raises(ValueError, match="header row"):
        _extract_headers_and_sample_rows("contact,company")


def test_extract_headers_and_sample_rows_limits_rows_and_surfaces_csv_errors(monkeypatch) -> None:
    headers, rows = _extract_headers_and_sample_rows(
        "Person,Organisation\nA,One\nB,Two\nC,Three\nD,Four\n",
        sample_limit=2,
    )
    assert headers == ["Person", "Organisation"]
    assert len(rows) == 2

    class _BrokenReader:
        fieldnames = ["Person"]

        def __iter__(self):
            raise csv.Error("broken csv")

    monkeypatch.setattr("src.application.crm_import.csv.DictReader", lambda *args, **kwargs: _BrokenReader())
    with pytest.raises(ValueError, match="could not be parsed as CSV"):
        _extract_headers_and_sample_rows("Person\nTaylor\n")


def test_needs_ai_header_assistance_detects_missing_identity_or_follow_up() -> None:
    assert _needs_ai_header_assistance(
        [
            LeadImportHeaderMapping("Context", "notes", "notes"),
        ]
    ) is True
    assert _needs_ai_header_assistance(
        [
            LeadImportHeaderMapping("Contact", "lead_name", "lead_name"),
            LeadImportHeaderMapping("Followup", "next_follow_up_at", "next_follow_up_at"),
        ]
    ) is False


def test_preview_lead_import_handles_windows_newlines_without_csv_reader_crashing() -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    use_case = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))

    preview = use_case.execute(
        make_user(),
        "Contact,Company,Owner,Status,Next Follow-Up,Notes\r\nTaylor Brooks,Beacon Ridge,Samir Patel,Qualification,2024-05-09,Imported from sheet\r\n",
        "csv",
        "CSV upload",
    )

    assert preview.importable_rows == 1
    assert preview.rows[0].lead_name == "Taylor Brooks"


def test_preview_lead_import_rejects_missing_header_row_via_csv_reader(monkeypatch) -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    use_case = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))

    class _Reader:
        fieldnames = None

        def __iter__(self):
            return iter(())

    monkeypatch.setattr("src.application.crm_import.csv.DictReader", lambda *args, **kwargs: _Reader())
    with pytest.raises(ValueError, match="header row"):
        use_case.execute(make_user(), "contact,company", "csv", "CSV upload")


def test_preview_lead_import_surfaces_csv_reader_parse_errors_as_validation_errors(monkeypatch) -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    use_case = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))

    class _BrokenReader:
        fieldnames = ["Contact"]

        def __iter__(self):
            raise csv.Error("broken csv")

    monkeypatch.setattr("src.application.crm_import.csv.DictReader", lambda *args, **kwargs: _BrokenReader())

    with pytest.raises(ValueError, match="could not be parsed as CSV"):
        use_case.execute(make_user(), "contact\nTaylor\n", "csv", "CSV upload")


def test_preview_lead_import_surfaces_csv_header_parse_errors_as_validation_errors(monkeypatch) -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    use_case = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))

    class _BrokenHeaderReader:
        @property
        def fieldnames(self):
            raise csv.Error("broken header")

        def __iter__(self):
            return iter(())

    monkeypatch.setattr("src.application.crm_import.csv.DictReader", lambda *args, **kwargs: _BrokenHeaderReader())

    with pytest.raises(ValueError, match="could not be parsed as CSV"):
        use_case.execute(make_user(), "contact\nTaylor\n", "csv", "CSV upload")


def test_preview_lead_import_surfaces_missing_fields_invalid_dates_and_note_warnings() -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    preview = PreviewLeadImportUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC)).execute(
        make_user(),
        "contact,company,status,next follow-up,notes\n,,,bad-date,\nTaylor,Broken Date,Discovery,,\n",
        "csv",
        "CSV upload",
    )

    assert preview.invalid_rows == 2
    assert preview.rows[0].lead_name == "Imported lead 2"
    assert preview.rows[0].company_name == "Unspecified company"
    assert preview.rows[0].owner_name == "Unassigned"
    assert preview.rows[0].stage == "Imported"
    assert preview.rows[0].next_follow_up_at is None
    assert [issue.severity for issue in preview.rows[0].issues] == ["error", "error", "warning"]
    assert preview.rows[1].issues[0].message == "Add a next follow-up date so the row can enter the queue."


def test_import_helpers_cover_datetime_stage_priority_and_duplicate_edge_cases() -> None:
    assert _parse_datetime("") is None
    assert _parse_datetime("2024-05-09T11:30:00Z") == datetime(2024, 5, 9, 11, 30, tzinfo=UTC)
    assert _parse_datetime("05/09/2024 2:15 PM") == datetime(2024, 5, 9, 14, 15, tzinfo=UTC)
    assert _parse_datetime("09.05.2024") == datetime(2024, 5, 9, 9, 0, tzinfo=UTC)
    assert _parse_datetime("not-a-date") is None
    assert _normalize_stage("") == "Imported"
    assert _build_duplicate_key("", "") == ""

    imported_at = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    medium_row = LeadImportPreviewRow(
        row_number=2,
        lead_name="Taylor Brooks",
        company_name="Beacon Ridge",
        owner_name="Samir Patel",
        stage="Qualification",
        next_follow_up_at=datetime(2024, 5, 8, 12, 30, tzinfo=UTC),
        notes="",
        duplicate=False,
        issues=(),
    )
    low_row = LeadImportPreviewRow(
        row_number=3,
        lead_name="Morgan Lee",
        company_name="Stone Harbor",
        owner_name="Riley Chen",
        stage="Proposal",
        next_follow_up_at=datetime(2024, 5, 10, 12, 30, tzinfo=UTC),
        notes="Imported note",
        duplicate=False,
        issues=(),
    )
    medium_item = _build_imported_follow_up(medium_row, "CSV upload", imported_at)
    high_item = _build_imported_follow_up(
        LeadImportPreviewRow(
            row_number=1,
            lead_name="Soon Due",
            company_name="Signal Peak",
            owner_name="Ada Lovelace",
            stage="Discovery",
            next_follow_up_at=datetime(2024, 5, 7, 11, 30, tzinfo=UTC),
            notes="",
            duplicate=False,
            issues=(),
        ),
        "CSV upload",
        imported_at,
    )
    low_item = _build_imported_follow_up(low_row, "Google Sheets", imported_at)
    assert high_item.priority == "high"
    assert medium_item.priority == "medium"
    assert medium_item.notes == "Imported without notes."
    assert low_item.priority == "low"
    assert low_item.timeline[1].kind == "internal_note"

    with pytest.raises(ValueError, match="next follow-up date is required"):
        _build_imported_follow_up(
            LeadImportPreviewRow(
                row_number=4,
                lead_name="No Date",
                company_name="Missing Time",
                owner_name="Owner",
                stage="Imported",
                next_follow_up_at=None,
                notes="",
                duplicate=False,
                issues=(),
            ),
            "CSV upload",
            imported_at,
        )


def test_google_sheet_fetch_and_source_resolution_cover_error_paths(monkeypatch) -> None:
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"\xef\xbb\xbfcontact,company\nTaylor,Beacon\n"

    monkeypatch.setattr("src.adapters.crm.google_sheets.urlopen", lambda *args, **kwargs: _Response())
    assert fetch_google_sheets_csv("https://docs.google.com/spreadsheets/d/abc123/edit") == "contact,company\nTaylor,Beacon\n"

    monkeypatch.setattr("src.adapters.crm.google_sheets.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(ValueError, match="Unable to fetch the Google Sheet"):
        fetch_google_sheets_csv("https://docs.google.com/spreadsheets/d/abc123/edit")

    with pytest.raises(ValueError, match="Google Sheets URL is required"):
        build_google_sheets_csv_url("   ")
    with pytest.raises(ValueError, match="Use a valid Google Sheets URL"):
        build_google_sheets_csv_url("https://example.com/not-a-sheet")
    with pytest.raises(ValueError, match="Unable to determine the Google Sheets document ID"):
        build_google_sheets_csv_url("https://docs.google.com/spreadsheets/d/")
    assert build_google_sheets_csv_url("https://docs.google.com/spreadsheets/d/abc123/edit?gid=789") == (
        "https://docs.google.com/spreadsheets/d/abc123/export?format=csv&gid=789"
    )

    buffer = BytesIO()
    pd.DataFrame([{"Contact": "Taylor Brooks", "Company": "Beacon Ridge"}]).to_excel(buffer, index=False, engine="openpyxl")
    excel_payload = LeadImportPayload(
        source_type="excel",
        file_name="leads.xlsx",
        file_content_base64=b64encode(buffer.getvalue()).decode("ascii"),
    )
    excel_content, excel_label, excel_source_type = _resolve_crm_import_source(excel_payload)
    assert "Contact,Company" in excel_content
    assert excel_label == "leads.xlsx"
    assert excel_source_type == "excel"

    with pytest.raises(ValueError, match="Spreadsheet file name is required"):
        _resolve_crm_import_source(LeadImportPayload(source_type="excel", file_content_base64="aGVsbG8="))

    with pytest.raises(ValueError, match="Spreadsheet file content is required"):
        _resolve_crm_import_source(LeadImportPayload(source_type="excel", file_name="leads.xlsx"))

    assert _resolve_crm_import_source(LeadImportPayload(source_type="csv", csv_content="a,b\n1,2")) == (
        "a,b\n1,2",
        "CSV upload",
        "csv",
    )
    with pytest.raises(ValueError, match="CSV content is required"):
        _resolve_crm_import_source(LeadImportPayload(source_type="csv"))
    with pytest.raises(ValueError, match="Google Sheets URL is required"):
        _resolve_crm_import_source(LeadImportPayload(source_type="google_sheets"))

    monkeypatch.setattr(api_app_module, "fetch_google_sheets_csv", lambda sheet_url: "contact,company\nTaylor,Beacon\n")
    assert _resolve_crm_import_source(
        LeadImportPayload(source_type="google_sheets", sheet_url="https://docs.google.com/spreadsheets/d/abc123/edit")
    ) == ("contact,company\nTaylor,Beacon\n", "Google Sheets", "google_sheets")

    payload = LeadImportPayload.model_construct(source_type="unsupported", csv_content=None, sheet_url=None)
    with pytest.raises(ValueError, match="Unsupported import source."):
        _resolve_crm_import_source(payload)


def test_image_source_resolution_requires_authenticated_context_and_image_fields() -> None:
    with pytest.raises(ValueError, match="Image file name is required"):
        _resolve_crm_import_source(LeadImportPayload(source_type="image", file_content_base64="aGVsbG8="))

    with pytest.raises(ValueError, match="Image file content is required"):
        _resolve_crm_import_source(LeadImportPayload(source_type="image", file_name="note.png"))

    with pytest.raises(ValueError, match="Authenticated image intake context is required"):
        _resolve_crm_import_source(
            LeadImportPayload(
                source_type="image",
                file_name="note.png",
                file_content_base64=b64encode(b"image").decode("ascii"),
            )
        )
