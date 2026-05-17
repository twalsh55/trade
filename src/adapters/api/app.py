from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import Callable
from urllib import request
from uuid import UUID
from uuid import uuid4

from fastapi import BackgroundTasks, Cookie, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.adapters.api.observability import (
    REQUEST_ID_HEADER,
    build_runtime_report,
    configure_api_logger,
)
from src.adapters.billing.runtime import build_billing_adapter
from src.adapters.auth.clerk_auth import AuthenticationError
from src.adapters.auth.runtime import (
    CLERK_SESSION_COOKIE,
    build_authenticate_user_use_case,
    derive_clerk_frontend_api_host,
    get_app_base_url,
    get_configured_clerk_page_url,
)
from src.adapters.autonomous_build.runtime import append_autonomous_build_brief
from src.adapters.founder_code.runtime import build_founder_code_request_repository
from src.adapters.market_data.yfinance_provider import YFinanceMarketDataAdapter
from src.adapters.notifications.smtp_email_notifier import EmailNotificationError
from src.adapters.notifications.telegram_notifier import TelegramNotificationError, TelegramNotifier
from src.adapters.operator_briefing.runtime import collect_operator_briefing_config_errors, run_daily_operator_briefing_job
from src.adapters.crm.google_sheets import fetch_google_sheets_csv
from src.adapters.crm.runtime import (
    build_crm_image_intake_agent_from_env,
    build_crm_spreadsheet_assist_agent_from_env,
    build_mailbox_provider_from_env,
)
from src.adapters.crm.spreadsheet_files import convert_excel_bytes_to_csv, decode_base64_file_content
from src.adapters.crm.runtime import build_lead_follow_up_repository
from src.adapters.persistence.runtime import build_personalization_repository, build_user_repository
from src.adapters.prospecting.runtime import collect_prospecting_config_errors, is_prospect_agent_enabled, run_prospecting_job
from src.adapters.sentiment.runtime import collect_etf_sentiment_config_errors, deliver_etf_sentiment_job, run_etf_sentiment_job
from src.adapters.social.reddit_lead_source import RedditLeadSourceError
from src.application.account import (
    AlertHistoryEntry,
    GetUserDashboardSettingsUseCase,
    ListAlertHistoryUseCase,
    UpdateUserDashboardSettingsUseCase,
    UserDashboardSettings,
)
from src.application.billing import (
    CreateBillingPortalSessionUseCase,
    CreateCheckoutSessionUseCase,
    GetBillingOverviewUseCase,
)
from src.application.autonomous_build import decide_autonomous_build_brief, format_autonomous_build_brief
from src.application.founder_code import ListFounderCodeRequestsUseCase, QueueFounderCodeRequestUseCase
from src.application.crm import GetLeadFollowUpOverviewUseCase
from src.application.crm import (
    AddLeadFollowUpNoteUseCase,
    BeginMailboxOAuthUseCase,
    CompleteLeadFollowUpUseCase,
    CompleteMailboxOAuthUseCase,
    ConnectMailboxUseCase,
    DisconnectMailboxConnectionUseCase,
    DesignLeadFollowUpEmailUseCase,
    EmailThreadMessageInput,
    EraseRelationshipMemoryUseCase,
    IngestLeadEmailThreadUseCase,
    ListMailboxConnectionsUseCase,
    ProcessMailboxWatchEventUseCase,
    SendLeadFollowUpEmailUseCase,
    SnoozeLeadFollowUpUseCase,
    SyncMailboxConnectionUseCase,
    UpdateMailboxConnectionSyncUseCase,
)
from src.application.crm_import import (
    CommitLeadImportUseCase,
    GenerateLeadImportFromImageUseCase,
    PreviewLeadImportUseCase,
    PreviewLeadImportWithAssistanceUseCase,
)
from src.application.dashboard import (
    DEFAULT_BENCHMARK,
    DEFAULT_LONG_YIELD_SYMBOL,
    DEFAULT_LOOKBACK_YEARS,
    DEFAULT_RISK_PROXY,
    DEFAULT_SHORT_YIELD_SYMBOL,
    DEFAULT_VIX_SYMBOL,
    build_dashboard_config,
    build_default_dashboard_settings,
    normalize_dashboard_settings,
)
from src.application.dto import (
    build_alert_history_entry_dto,
    build_authenticated_user_dto,
    build_billing_overview_dto,
    build_dashboard_snapshot_dto,
    build_lead_import_commit_result_dto,
    build_lead_import_preview_dto,
    build_lead_follow_up_email_draft_dto,
    build_lead_follow_up_overview_dto,
    build_mailbox_connection_dto,
    build_mailbox_send_result_dto,
    build_mailbox_sync_result_dto,
    build_user_dashboard_settings_dto,
    dto_to_dict,
)
from src.application.use_cases import BuildCrashDashboardUseCase
from src.domain.auth import ExternalIdentity, User
from src.domain.models import DEFAULT_UNIVERSE
from src.env_utils import get_first_configured_env, load_env_file

api_logger = logging.getLogger("brivoly.api")
ANONYMOUS_CRM_USER_ID = UUID("00000000-0000-0000-0000-00000000c0de")
MAILBOX_OAUTH_STATE_TTL_SECONDS = 15 * 60
MAILBOX_WATCH_SECRET_HEADER = "x-brivoly-watch-secret"


@dataclass(frozen=True)
class ApiDependencies:
    auth_use_case_factory: Callable[[], object]
    market_data_factory: Callable[[], object]
    personalization_repository_factory: Callable[[], object]
    lead_follow_up_repository_factory: Callable[[], object]
    mailbox_provider_factory: Callable[[], object]
    billing_port_factory: Callable[[], object | None]
    user_repository_factory: Callable[[], object | None]
    now: Callable[[], datetime]


class UserDashboardSettingsPayload(BaseModel):
    universe: list[str] = Field(min_length=1)
    benchmark: str
    vix_symbol: str
    risk_proxy: str
    short_yield_symbol: str
    long_yield_symbol: str
    lookback_years: int = Field(ge=1, le=10)
    telegram_enabled: bool
    business_name: str = Field(default="", max_length=160)
    business_website: str = Field(default="", max_length=255)
    outbound_sender_name: str = Field(default="", max_length=160)
    profile_alias: str = Field(default="", max_length=80)
    business_logo_data_url: str = Field(default="", max_length=700_000)
    onboarding_profile_deferred: bool = False
    crm_ai_prompt: str = Field(default="", max_length=4000)
    crm_preferred_import_formats: list[str] = Field(default_factory=list, max_length=12)
    crm_image_intake_channels: list[str] = Field(default_factory=list, max_length=12)
    crm_image_intake_notes: str = Field(default="", max_length=1000)
    preferred_language: str = Field(default="en", max_length=16)
    preferred_locale: str = Field(default="en-US", max_length=24)
    data_retention_days: int = Field(default=365, ge=30, le=3650)
    allow_ai_processing: bool = True
    privacy_consent_version: str = Field(default="v1", max_length=32)
    privacy_consent_granted_at: datetime | None = None


class BillingSessionPayload(BaseModel):
    return_url: str | None = None


class LeadFollowUpActionPayload(BaseModel):
    action: str
    snooze_hours: int | None = Field(default=None, ge=1, le=24 * 14)
    note_body: str | None = Field(default=None, min_length=1, max_length=1000)


class LeadImportPayload(BaseModel):
    source_type: str = Field(pattern="^(csv|excel|image|google_sheets)$")
    csv_content: str | None = Field(default=None, min_length=1)
    sheet_url: str | None = None
    file_name: str | None = None
    file_content_base64: str | None = None
    field_mapping: dict[str, str | None] | None = None
    clarification_answers: dict[str, str] | None = None
    row_overrides: dict[str, dict[str, str]] | None = None


class LeadFollowUpEmailDraftPayload(BaseModel):
    objective: str = Field(default="follow_up", pattern="^(follow_up|recap|revive|close_loop)$")
    tone: str = Field(default="warm", pattern="^(warm|direct|confident)$")
    length: str = Field(default="short", pattern="^(short|medium)$")


class CRMInboxThreadMessagePayload(BaseModel):
    message_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(default="", max_length=255)
    sent_at: datetime
    direction: str = Field(pattern="^(inbound|outbound)$")
    from_email: str = Field(min_length=3, max_length=255)
    from_name: str = Field(default="", max_length=160)
    to_emails: list[str] = Field(min_length=1, max_length=25)
    subject: str = Field(default="", max_length=255)
    body_text: str = Field(default="", max_length=5000)
    snippet: str = Field(default="", max_length=500)


class CRMInboxThreadPayload(BaseModel):
    source: str = Field(default="api", max_length=80)
    thread_id: str = Field(min_length=1, max_length=255)
    messages: list[CRMInboxThreadMessagePayload] = Field(min_length=1, max_length=50)


class MailboxConnectionPayload(BaseModel):
    provider: str = Field(pattern="^(gmail|outlook)$")
    email_address: str = Field(min_length=3, max_length=255)
    display_name: str = Field(default="", max_length=160)


class MailboxOAuthStartPayload(BaseModel):
    provider: str = Field(pattern="^(gmail|outlook)$")


class MailboxOAuthCompletePayload(BaseModel):
    provider: str = Field(pattern="^(gmail|outlook)$")
    code: str = Field(min_length=1, max_length=4000)
    state: str = Field(min_length=1, max_length=4000)


class MailboxConnectionUpdatePayload(BaseModel):
    background_sync_enabled: bool


class AccountPrivacyErasePayload(BaseModel):
    scope: str = Field(default="all_memory", pattern="^(relationship_memory|all_memory)$")
    confirm: bool


class MailboxWatchEventPayload(BaseModel):
    external_account_id: str | None = Field(default=None, max_length=255)
    email_address: str | None = Field(default=None, max_length=255)
    connection_id: str | None = Field(default=None, max_length=255)


class MailboxSendPayload(BaseModel):
    connection_id: str | None = Field(default=None, min_length=1, max_length=255)
    thread_id: str | None = Field(default=None, min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=10000)


class FounderCodeRequestDTO(BaseModel):
    id: str
    created_at: str
    source_chat_id: str
    command_text: str
    guidance: str | None


class CRMRemoteIntakeDTO(BaseModel):
    telegram_available: bool
    intake_channel: str | None
    intake_caption: str | None
    magic_link_url: str | None
    instructions: str


class CRMRemoteIntakeUploadPayload(BaseModel):
    intake_token: str = Field(min_length=1, max_length=400)
    file_name: str = Field(min_length=1, max_length=255)
    file_content_base64: str = Field(min_length=1)


def _get_mailbox_oauth_callback_url(provider: str) -> str:
    return f"{get_app_base_url().rstrip('/')}/clientos/inbox/connect/{provider.strip().lower()}"


def _get_mailbox_oauth_state_secret() -> str:
    return (
        os.getenv("CRM_INTAKE_SECRET", "").strip()
        or os.getenv("INTERNAL_CRON_SECRET", "").strip()
        or os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        or os.getenv("CLERK_SECRET_KEY", "").strip()
    )


def _build_mailbox_oauth_state(user: User, provider: str, current_time: datetime) -> str:
    secret = _get_mailbox_oauth_state_secret()
    if not secret:
        raise RuntimeError("Mailbox OAuth is unavailable until a state-signing secret is configured.")
    timestamp = str(int(current_time.timestamp()))
    payload = f"{user.id}:{provider.strip().lower()}:{timestamp}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{payload}:{signature}"


def _validate_mailbox_oauth_state(user: User, provider: str, state: str, current_time: datetime) -> None:
    secret = _get_mailbox_oauth_state_secret()
    if not secret:
        raise ValueError("Mailbox OAuth is unavailable until a state-signing secret is configured.")
    parts = state.strip().split(":")
    if len(parts) != 4:
        raise ValueError("Mailbox OAuth state is invalid.")
    user_id_text, provider_text, timestamp_text, signature = parts
    if user_id_text != str(user.id):
        raise ValueError("Mailbox OAuth state does not match the current account.")
    if provider_text != provider.strip().lower():
        raise ValueError("Mailbox OAuth state does not match this provider.")
    if not timestamp_text.isdigit():
        raise ValueError("Mailbox OAuth state is invalid.")
    payload = f"{user_id_text}:{provider_text}:{timestamp_text}"
    expected_signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Mailbox OAuth state verification failed.")
    issued_at = datetime.fromtimestamp(int(timestamp_text), tz=UTC)
    if current_time - issued_at > timedelta(seconds=MAILBOX_OAUTH_STATE_TTL_SECONDS):
        raise ValueError("Mailbox OAuth state expired. Please try connecting again.")


def _get_mailbox_watch_secret() -> str:
    return (
        os.getenv("MAILBOX_WATCH_WEBHOOK_SECRET", "").strip()
        or os.getenv("CRM_INTAKE_SECRET", "").strip()
        or os.getenv("INTERNAL_CRON_SECRET", "").strip()
    )


def _validate_mailbox_watch_secret(provided_secret: str | None) -> None:
    expected_secret = _get_mailbox_watch_secret()
    if not expected_secret or provided_secret != expected_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid mailbox watch secret.")


def create_app(dependencies: ApiDependencies | None = None) -> FastAPI:
    load_env_file()
    logger = configure_api_logger()
    deps = dependencies or ApiDependencies(
        auth_use_case_factory=build_authenticate_user_use_case,
        market_data_factory=YFinanceMarketDataAdapter,
        personalization_repository_factory=build_personalization_repository,
        lead_follow_up_repository_factory=build_lead_follow_up_repository,
        mailbox_provider_factory=build_mailbox_provider_from_env,
        billing_port_factory=build_billing_adapter,
        user_repository_factory=build_user_repository,
        now=lambda: datetime.now(tz=UTC),
    )
    app = FastAPI(title="Brivoly API", version="0.1.0")

    @app.middleware("http")
    async def add_request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        started_at = perf_counter()
        response = await call_next(request)
        duration_ms = (perf_counter() - started_at) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response

    @app.get("/healthz")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readiness() -> JSONResponse:
        report = build_runtime_report()
        return JSONResponse(report, status_code=status.HTTP_200_OK if report["status"] == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE)

    @app.get("/api/settings/bootstrap")
    def settings_bootstrap() -> dict[str, object]:
        publishable_key = os.getenv("CLERK_PUBLISHABLE_KEY", "").strip() or None
        return {
            "default_universe": list(DEFAULT_UNIVERSE),
            "default_benchmark": DEFAULT_BENCHMARK,
            "default_vix_symbol": DEFAULT_VIX_SYMBOL,
            "default_risk_proxy": DEFAULT_RISK_PROXY,
            "default_short_yield_symbol": DEFAULT_SHORT_YIELD_SYMBOL,
            "default_long_yield_symbol": DEFAULT_LONG_YIELD_SYMBOL,
            "default_lookback_years": DEFAULT_LOOKBACK_YEARS,
            "app_base_url": get_app_base_url(),
            "clerk_publishable_key": publishable_key,
            "clerk_frontend_api_host": derive_clerk_frontend_api_host(publishable_key) if publishable_key else None,
            "clerk_sign_in_url": get_configured_clerk_page_url("sign-in"),
            "clerk_sign_up_url": get_configured_clerk_page_url("sign-up"),
        }

    @app.get("/api/account/settings")
    def account_settings(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.personalization_repository_factory()
        settings = GetUserDashboardSettingsUseCase(
            repository=repository,
            default_factory=_build_default_dashboard_settings,
        ).execute(user)
        return dto_to_dict(build_user_dashboard_settings_dto(settings))

    @app.put("/api/account/settings")
    def update_account_settings(
        payload: UserDashboardSettingsPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.personalization_repository_factory()
        settings = UpdateUserDashboardSettingsUseCase(repository=repository).execute(
            user,
            normalize_dashboard_settings(
                # Capture the first explicit privacy acknowledgement the moment these settings are saved with AI processing enabled.
                UserDashboardSettings(
                user_id=user.id,
                universe=payload.universe,
                benchmark=payload.benchmark,
                vix_symbol=payload.vix_symbol,
                risk_proxy=payload.risk_proxy,
                short_yield_symbol=payload.short_yield_symbol,
                long_yield_symbol=payload.long_yield_symbol,
                lookback_years=payload.lookback_years,
                telegram_enabled=payload.telegram_enabled,
                business_name=payload.business_name,
                business_website=payload.business_website,
                outbound_sender_name=payload.outbound_sender_name,
                profile_alias=payload.profile_alias,
                business_logo_data_url=payload.business_logo_data_url,
                onboarding_profile_deferred=payload.onboarding_profile_deferred,
                crm_ai_prompt=payload.crm_ai_prompt,
                crm_preferred_import_formats=payload.crm_preferred_import_formats,
                crm_image_intake_channels=payload.crm_image_intake_channels,
                crm_image_intake_notes=payload.crm_image_intake_notes,
                preferred_language=payload.preferred_language,
                preferred_locale=payload.preferred_locale,
                data_retention_days=payload.data_retention_days,
                allow_ai_processing=payload.allow_ai_processing,
                privacy_consent_version=payload.privacy_consent_version,
                privacy_consent_granted_at=payload.privacy_consent_granted_at or (deps.now() if payload.allow_ai_processing else None),
                )
            ),
        )
        repository.append_alert_history(
            user.id,
            AlertHistoryEntry(
                occurred_at=deps.now(),
                category="settings",
                severity="info",
                title="Dashboard settings updated",
                message="Your dashboard defaults were updated through the API layer.",
            ),
        )
        return dto_to_dict(build_user_dashboard_settings_dto(settings))

    @app.get("/api/account/privacy/export")
    def account_privacy_export(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        settings_repository = deps.personalization_repository_factory()
        crm_repository = deps.lead_follow_up_repository_factory()
        settings = GetUserDashboardSettingsUseCase(
            repository=settings_repository,
            default_factory=_build_default_dashboard_settings,
        ).execute(user)
        overview = GetLeadFollowUpOverviewUseCase(repository=crm_repository, now=deps.now).execute(user)
        connections = ListMailboxConnectionsUseCase(repository=crm_repository).execute(user)
        return {
            "generated_at": deps.now().isoformat(),
            "user": dto_to_dict(build_authenticated_user_dto(user)),
            "settings": dto_to_dict(build_user_dashboard_settings_dto(settings)),
            "mailboxes": [dto_to_dict(build_mailbox_connection_dto(item)) for item in connections],
            "relationship_memory": dto_to_dict(build_lead_follow_up_overview_dto(overview)),
        }

    @app.post("/api/account/privacy/erase")
    def account_privacy_erase(
        payload: AccountPrivacyErasePayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        if not payload.confirm:
            raise HTTPException(status_code=422, detail="Privacy erase requires explicit confirmation.")
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.lead_follow_up_repository_factory()
        try:
            EraseRelationshipMemoryUseCase(repository=repository).execute(user, scope=payload.scope)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"erased": True, "scope": payload.scope}

    @app.get("/api/alerts/history")
    def alerts_history(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        entries = ListAlertHistoryUseCase(repository=deps.personalization_repository_factory()).execute(user, limit=limit)
        return {
            "items": [dto_to_dict(build_alert_history_entry_dto(entry)) for entry in entries],
            "count": len(entries),
        }

    @app.get("/api/crm/followups")
    def crm_followups(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        overview = GetLeadFollowUpOverviewUseCase(
            repository=deps.lead_follow_up_repository_factory(),
            now=deps.now,
        ).execute(user)
        return dto_to_dict(build_lead_follow_up_overview_dto(overview))

    @app.patch("/api/crm/followups/{follow_up_id}")
    def crm_followup_action(
        follow_up_id: str,
        payload: LeadFollowUpActionPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.lead_follow_up_repository_factory()
        try:
            if payload.action == "complete":
                CompleteLeadFollowUpUseCase(repository=repository, now=deps.now).execute(user, follow_up_id)
            elif payload.action == "snooze":
                if payload.snooze_hours is None:
                    raise HTTPException(status_code=422, detail="snooze_hours is required for snooze.")
                SnoozeLeadFollowUpUseCase(repository=repository, now=deps.now).execute(
                    user,
                    follow_up_id,
                    payload.snooze_hours,
                )
            elif payload.action == "note":
                if payload.note_body is None:
                    raise HTTPException(status_code=422, detail="note_body is required for note.")
                AddLeadFollowUpNoteUseCase(repository=repository, now=deps.now).execute(
                    user,
                    follow_up_id,
                    payload.note_body,
                )
            else:
                raise HTTPException(status_code=422, detail="Unsupported CRM follow-up action.")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="CRM follow-up not found.") from exc

        overview = GetLeadFollowUpOverviewUseCase(repository=repository, now=deps.now).execute(user)
        return dto_to_dict(build_lead_follow_up_overview_dto(overview))

    @app.post("/api/crm/followups/{follow_up_id}/email-draft")
    def crm_followup_email_draft(
        follow_up_id: str,
        payload: LeadFollowUpEmailDraftPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.lead_follow_up_repository_factory()
        personalization_repository = deps.personalization_repository_factory()
        try:
            draft = DesignLeadFollowUpEmailUseCase(
                repository=repository,
                settings_loader=lambda authenticated_user: GetUserDashboardSettingsUseCase(
                    repository=personalization_repository,
                    default_factory=_build_default_dashboard_settings,
                ).execute(authenticated_user),
            ).execute(
                user,
                follow_up_id,
                objective=payload.objective,
                tone=payload.tone,
                length=payload.length,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="CRM follow-up not found.") from exc
        return dto_to_dict(build_lead_follow_up_email_draft_dto(draft))

    @app.post("/api/crm/inbox/threads")
    def crm_inbox_thread_ingest(
        payload: CRMInboxThreadPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.lead_follow_up_repository_factory()
        try:
            overview = IngestLeadEmailThreadUseCase(repository=repository, now=deps.now).execute(
                user,
                source=payload.source,
                thread_id=payload.thread_id,
                messages=[
                    EmailThreadMessageInput(
                        message_id=item.message_id,
                        external_message_id=item.external_message_id,
                        sent_at=item.sent_at,
                        direction=item.direction,
                        from_email=item.from_email,
                        from_name=item.from_name,
                        to_emails=tuple(item.to_emails),
                        subject=item.subject,
                        body_text=item.body_text,
                        snippet=item.snippet,
                    )
                    for item in payload.messages
                ],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return dto_to_dict(build_lead_follow_up_overview_dto(overview))

    @app.post("/api/crm/inbox/watch-events/{provider}")
    def crm_mailbox_watch_event(
        provider: str,
        payload: MailboxWatchEventPayload,
        watch_secret: str | None = Header(default=None, alias=MAILBOX_WATCH_SECRET_HEADER),
    ) -> dict[str, object]:
        _validate_mailbox_watch_secret(watch_secret)
        repository = deps.lead_follow_up_repository_factory()
        user_repository = deps.user_repository_factory()
        if user_repository is None or not callable(getattr(repository, "list_mailbox_connection_user_ids", None)):
            raise HTTPException(status_code=503, detail="Mailbox watch handling is unavailable.")

        matched_result = None
        for user_id in repository.list_mailbox_connection_user_ids():
            user = user_repository.get_user_by_id(user_id)
            if user is None:
                continue
            try:
                matched_result = ProcessMailboxWatchEventUseCase(
                    repository=repository,
                    now=deps.now,
                    mailbox_provider=deps.mailbox_provider_factory(),
                ).execute(
                    user,
                    provider=provider,
                    connection_id=payload.connection_id,
                    external_account_id=payload.external_account_id,
                    email_address=payload.email_address,
                )
                break
            except KeyError:
                continue
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        if matched_result is None:
            raise HTTPException(status_code=404, detail="No matching mailbox connection was found for this watch event.")

        return dto_to_dict(build_mailbox_sync_result_dto(matched_result))

    @app.get("/api/crm/inbox/mailboxes")
    def crm_mailbox_connections(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        connections = ListMailboxConnectionsUseCase(repository=deps.lead_follow_up_repository_factory()).execute(user)
        return {"items": [dto_to_dict(build_mailbox_connection_dto(item)) for item in connections]}

    @app.post("/api/crm/inbox/mailboxes/oauth/start")
    def crm_start_mailbox_oauth(
        payload: MailboxOAuthStartPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        current_time = deps.now()
        try:
            state = _build_mailbox_oauth_state(user, payload.provider, current_time)
            authorization_url = BeginMailboxOAuthUseCase(mailbox_provider=deps.mailbox_provider_factory()).execute(
                provider=payload.provider,
                redirect_uri=_get_mailbox_oauth_callback_url(payload.provider),
                state=state,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"provider": payload.provider, "authorization_url": authorization_url}

    @app.post("/api/crm/inbox/mailboxes/oauth/complete")
    def crm_complete_mailbox_oauth(
        payload: MailboxOAuthCompletePayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        current_time = deps.now()
        try:
            _validate_mailbox_oauth_state(user, payload.provider, payload.state, current_time)
            connection = CompleteMailboxOAuthUseCase(
                repository=deps.lead_follow_up_repository_factory(),
                mailbox_provider=deps.mailbox_provider_factory(),
            ).execute(
                user,
                provider=payload.provider,
                code=payload.code,
                redirect_uri=_get_mailbox_oauth_callback_url(payload.provider),
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return dto_to_dict(build_mailbox_connection_dto(connection))

    @app.post("/api/crm/inbox/mailboxes/connect")
    def crm_connect_mailbox(
        payload: MailboxConnectionPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        try:
            connection = ConnectMailboxUseCase(repository=deps.lead_follow_up_repository_factory(), now=deps.now).execute(
                user,
                provider=payload.provider,
                email_address=payload.email_address,
                display_name=payload.display_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return dto_to_dict(build_mailbox_connection_dto(connection))

    @app.patch("/api/crm/inbox/mailboxes/{connection_id}")
    def crm_update_mailbox(
        connection_id: str,
        payload: MailboxConnectionUpdatePayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        try:
            connection = UpdateMailboxConnectionSyncUseCase(repository=deps.lead_follow_up_repository_factory()).execute(
                user,
                connection_id,
                background_sync_enabled=payload.background_sync_enabled,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Mailbox connection not found.") from exc
        return dto_to_dict(build_mailbox_connection_dto(connection))

    @app.delete("/api/crm/inbox/mailboxes/{connection_id}")
    def crm_delete_mailbox(
        connection_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        try:
            DisconnectMailboxConnectionUseCase(repository=deps.lead_follow_up_repository_factory()).execute(user, connection_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Mailbox connection not found.") from exc
        return {"deleted": True, "connection_id": connection_id}

    @app.post("/api/crm/inbox/mailboxes/{connection_id}/sync")
    def crm_sync_mailbox(
        connection_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.lead_follow_up_repository_factory()
        try:
            result = SyncMailboxConnectionUseCase(
                repository=repository,
                now=deps.now,
                mailbox_provider=deps.mailbox_provider_factory(),
            ).execute(user, connection_id)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Mailbox connection not found.") from exc
        return dto_to_dict(build_mailbox_sync_result_dto(result))

    @app.post("/api/crm/followups/{follow_up_id}/send")
    def crm_send_followup_email(
        follow_up_id: str,
        payload: MailboxSendPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.lead_follow_up_repository_factory()
        try:
            result = SendLeadFollowUpEmailUseCase(
                repository=repository,
                now=deps.now,
                mailbox_provider=deps.mailbox_provider_factory(),
            ).execute(
                user,
                follow_up_id,
                connection_id=payload.connection_id,
                thread_id=payload.thread_id,
                subject=payload.subject,
                body=payload.body,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            missing_id = str(exc).strip("'")
            message = "Mailbox connection not found." if payload.connection_id and missing_id == payload.connection_id else "CRM follow-up not found."
            raise HTTPException(status_code=404, detail=message) from exc
        return dto_to_dict(build_mailbox_send_result_dto(result))

    @app.post("/api/crm/import/preview")
    def crm_import_preview(
        payload: LeadImportPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.lead_follow_up_repository_factory()
        try:
            csv_content, source_label, source_type = _resolve_crm_import_source(payload, user, deps)
            settings = GetUserDashboardSettingsUseCase(
                repository=deps.personalization_repository_factory(),
                default_factory=_build_default_dashboard_settings,
            ).execute(user)
            preview = _preview_crm_import_with_optional_ai_assistance(
                user=user,
                repository=repository,
                now=deps.now,
                csv_content=csv_content,
                source_type=source_type,
                source_label=source_label,
                field_mapping=payload.field_mapping,
                clarification_answers=payload.clarification_answers,
                row_overrides=payload.row_overrides,
                settings=settings,
                deps=deps,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return dto_to_dict(build_lead_import_preview_dto(preview))

    @app.post("/api/crm/import")
    def crm_import_commit(
        payload: LeadImportPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        repository = deps.lead_follow_up_repository_factory()
        try:
            csv_content, source_label, source_type = _resolve_crm_import_source(payload, user, deps)
            settings = GetUserDashboardSettingsUseCase(
                repository=deps.personalization_repository_factory(),
                default_factory=_build_default_dashboard_settings,
            ).execute(user)
            preview = _preview_crm_import_with_optional_ai_assistance(
                user=user,
                repository=repository,
                now=deps.now,
                csv_content=csv_content,
                source_type=source_type,
                source_label=source_label,
                field_mapping=payload.field_mapping,
                clarification_answers=payload.clarification_answers,
                row_overrides=payload.row_overrides,
                settings=settings,
                deps=deps,
            )
            if preview.clarification and preview.clarification.required:
                raise ValueError("AI still needs one or two quick answers before this import is safe to commit.")
            result = CommitLeadImportUseCase(repository=repository, now=deps.now).execute(
                user,
                csv_content,
                source_type,
                source_label,
                payload.field_mapping,
                payload.row_overrides,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return dto_to_dict(build_lead_import_commit_result_dto(result))

    @app.get("/api/crm/intake-channel")
    def crm_intake_channel(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        user = _require_crm_user(deps, authorization, session_cookie)
        secret = _get_crm_intake_secret()
        if not secret:
            dto = CRMRemoteIntakeDTO(
                telegram_available=False,
                intake_channel=None,
                intake_caption=None,
                magic_link_url=None,
                instructions="Remote note capture is unavailable until CRM_INTAKE_SECRET and the Telegram bot are configured.",
            )
            return dto.model_dump()
        intake_token = _build_crm_intake_token(user.id, secret)
        dto = CRMRemoteIntakeDTO(
            telegram_available=bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
            intake_channel="magic_link",
            intake_caption=None,
            magic_link_url=f"{get_app_base_url().rstrip('/')}/intake/{intake_token}",
            instructions=(
                "Open this secure link on your phone, upload a note photo or screenshot, "
                "and Brivoly will import it into your CRM queue using your saved AI Intake Profile."
            ),
        )
        return dto.model_dump()

    @app.post("/api/crm/intake/upload")
    def crm_intake_upload(payload: CRMRemoteIntakeUploadPayload) -> dict[str, object]:
        try:
            result = _commit_crm_image_intake(
                intake_token=payload.intake_token,
                file_name=payload.file_name,
                file_bytes=decode_base64_file_content(payload.file_content_base64),
                deps=deps,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return {
            "imported_count": result.imported_count,
            "skipped_duplicates": result.skipped_duplicates,
            "skipped_invalid": result.skipped_invalid,
            "message": "Brivoly imported your note image into CRM.",
        }

    @app.get("/api/account/billing")
    def billing_overview(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        session_token = _extract_session_token(authorization, session_cookie)
        if not session_token and _is_anonymous_crm_enabled():
            return dto_to_dict(build_billing_overview_dto(GetBillingOverviewUseCase(_DisabledBillingPort()).execute(_build_anonymous_crm_user(deps))))
        user = _require_authenticated_user(deps, authorization, session_cookie)
        billing = deps.billing_port_factory()
        if billing is None:
            return dto_to_dict(
                build_billing_overview_dto(
                    GetBillingOverviewUseCase(_DisabledBillingPort()).execute(user)
                )
            )
        overview = GetBillingOverviewUseCase(billing).execute(user)
        return dto_to_dict(build_billing_overview_dto(overview))

    @app.post("/api/account/billing/checkout")
    def create_checkout_session(
        payload: BillingSessionPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, str]:
        user = _require_authenticated_user(deps, authorization, session_cookie)
        billing = deps.billing_port_factory()
        if billing is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe billing is not configured.")
        url = CreateCheckoutSessionUseCase(billing).execute(user, return_url=payload.return_url)
        return {"url": url}

    @app.post("/api/account/billing/portal")
    def create_billing_portal_session(
        payload: BillingSessionPayload,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, str]:
        user = _require_authenticated_user(deps, authorization, session_cookie)
        billing = deps.billing_port_factory()
        if billing is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe billing is not configured.")
        url = CreateBillingPortalSessionUseCase(billing).execute(user, return_url=payload.return_url)
        return {"url": url}

    @app.get("/api/session")
    def session_bootstrap(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
        session_token = _extract_session_token(authorization, session_cookie)
        if not session_token:
            return {"authenticated": False, "user": None}

        try:
            user = deps.auth_use_case_factory().execute(session_token)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except AuthenticationError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication failed: {exc}") from exc

        if user is None:
            return {"authenticated": False, "user": None}
        return {"authenticated": True, "user": dto_to_dict(build_authenticated_user_dto(user))}

    @app.get("/api/dashboard")
    def dashboard_snapshot(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
        universe: list[str] | None = Query(default=None),
        benchmark: str = Query(default="SPY"),
        vix_symbol: str = Query(default="^VIX"),
        risk_proxy: str = Query(default="HYG"),
        short_yield_symbol: str = Query(default="^IRX"),
        long_yield_symbol: str = Query(default="^TNX"),
        lookback_years: int = Query(default=DEFAULT_LOOKBACK_YEARS, ge=1, le=10),
        end_date: date | None = Query(default=None),
    ) -> dict[str, object]:
        user = _require_authenticated_user(deps, authorization, session_cookie)

        resolved_end_date = end_date or deps.now().date()
        effective_settings = normalize_dashboard_settings(
            UserDashboardSettings(
                user_id=user.id,
                universe=universe or list(DEFAULT_UNIVERSE),
                benchmark=benchmark,
                vix_symbol=vix_symbol,
                risk_proxy=risk_proxy,
                short_yield_symbol=short_yield_symbol,
                long_yield_symbol=long_yield_symbol,
                lookback_years=lookback_years,
                telegram_enabled=False,
                business_name="",
                business_website="",
                outbound_sender_name="",
                profile_alias="",
                business_logo_data_url="",
                onboarding_profile_deferred=False,
                crm_ai_prompt="",
                crm_preferred_import_formats=[],
                crm_image_intake_channels=[],
                crm_image_intake_notes="",
                preferred_language="en",
                preferred_locale="en-US",
                data_retention_days=365,
                allow_ai_processing=True,
                privacy_consent_version="v1",
                privacy_consent_granted_at=None,
            )
        )
        if universe is None:
            repository = deps.personalization_repository_factory()
            effective_settings = GetUserDashboardSettingsUseCase(
                repository=repository,
                default_factory=_build_default_dashboard_settings,
            ).execute(user)
        config = build_dashboard_config(effective_settings, end_date=resolved_end_date)

        try:
            result = BuildCrashDashboardUseCase(market_data=deps.market_data_factory()).execute(config)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

        snapshot = build_dashboard_snapshot_dto(config=config, result=result, refreshed_at=deps.now())
        return dto_to_dict(snapshot)

    @app.post("/api/telegram/webhook")
    def telegram_webhook(
        payload: dict[str, object],
        background_tasks: BackgroundTasks,
        telegram_secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
    ) -> dict[str, object]:
        _validate_telegram_webhook_secret(telegram_secret)
        intake = _extract_telegram_image_intake(payload)
        if intake is not None:
            notifier = _build_telegram_notifier(chat_id=intake.chat_id)
            notifier.send_message("Received your note image. Brivoly is importing it into your CRM now.")
            background_tasks.add_task(_run_telegram_crm_image_intake, notifier, intake, deps)
            return {"ok": True, "handled": True, "command": intake.command_name}
        command = _extract_telegram_command(payload)
        if command is None:
            return {"ok": True, "handled": False}

        configured_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not configured_chat_id:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram chat ID is not configured.")
        if command.chat_id != configured_chat_id:
            return {"ok": True, "handled": False}

        notifier = _build_telegram_notifier()
        if command.name == "/prospect" and command.argument is None:
            if not is_prospect_agent_enabled():
                notifier.send_message("Prospect agent is disabled for now.")
                return {"ok": True, "handled": True, "command": command.name}
            notifier.send_message("Starting the daily prospecting run now. I will send a follow-up when it finishes.")
            background_tasks.add_task(_run_prospecting_from_telegram, notifier)
            return {"ok": True, "handled": True, "command": command.name}
        if command.text == "/prospect status":
            notifier.send_message(_build_prospecting_status_message())
            return {"ok": True, "handled": True, "command": command.text}
        if command.name == "/sentiment" and command.argument is None:
            notifier.send_message("Starting the ETF sentiment run now. I will send a follow-up when it finishes.")
            background_tasks.add_task(_run_etf_sentiment_from_telegram, notifier)
            return {"ok": True, "handled": True, "command": command.name}
        if command.text == "/sentiment status":
            notifier.send_message(_build_etf_sentiment_status_message())
            return {"ok": True, "handled": True, "command": command.text}
        if command.name == "/code":
            _queue_founder_code_request(command)
            guidance_notice = f" Founder guidance received: {command.argument}." if command.argument else ""
            if not is_prospect_agent_enabled():
                notifier.send_message(
                    "Queued your code request. The prospect agent is disabled for now, so no build recommendation will run."
                    f"{guidance_notice}"
                )
                return {"ok": True, "handled": True, "command": command.name}
            notifier.send_message(
                "Starting a cooperative code run now. I will send a build recommendation when it finishes."
                f"{guidance_notice}"
            )
            background_tasks.add_task(_run_code_from_telegram, notifier, command.argument)
            return {"ok": True, "handled": True, "command": command.name}
        if command.name == "/help" and command.argument is None:
            notifier.send_message(
                "Supported commands:\n"
                "/prospect - run the prospecting agent when enabled\n"
                "/prospect status - show whether the prospecting agent is enabled and configured\n"
                "/sentiment - run the ETF sentiment agent\n"
                "/sentiment status - show whether the ETF sentiment agent is configured\n"
                "/code - queue a founder code request and, when enabled, run the prospect agent for a build recommendation\n"
                "/code <guidance> - treat the text as founder direction unless it would harm the product goal"
            )
            return {"ok": True, "handled": True, "command": command.name}
        return {"ok": True, "handled": False}

    @app.post("/api/internal/operator-briefing")
    def operator_briefing_webhook(
        internal_secret: str | None = Header(default=None, alias="X-Internal-Cron-Secret"),
    ) -> dict[str, object]:
        _validate_internal_cron_secret(internal_secret)
        errors = collect_operator_briefing_config_errors()
        if errors:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="\n".join(errors))
        briefing = run_daily_operator_briefing_job()
        return {
            "ok": True,
            "prospect_run_count": briefing.prospect_run_count,
            "shortlisted_ideas": briefing.total_shortlisted_ideas,
            "product_updates": len(briefing.product_updates),
        }

    @app.get("/api/internal/founder-code-requests")
    def founder_code_requests_webhook(
        internal_secret: str | None = Header(default=None, alias="X-Internal-Cron-Secret"),
        since: str | None = Query(default=None),
        limit: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, object]:
        _validate_internal_cron_secret(internal_secret)
        since_datetime = datetime.fromisoformat(since) if since else None
        requests = ListFounderCodeRequestsUseCase(build_founder_code_request_repository()).execute(since=since_datetime, limit=limit)
        return {
            "ok": True,
            "requests": [
                FounderCodeRequestDTO(
                    id=str(item.id),
                    created_at=item.created_at.isoformat(),
                    source_chat_id=item.source_chat_id,
                    command_text=item.command_text,
                    guidance=item.guidance,
                ).model_dump()
                for item in requests
            ],
        }

    return app


def _extract_session_token(authorization: str | None, session_cookie: str | None) -> str | None:
    if session_cookie:
        return session_cookie
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header must use a Bearer token.",
            )
        return token.strip()
    return session_cookie


def _normalize_universe(universe: list[str] | None) -> list[str]:
    if not universe:
        return list(DEFAULT_UNIVERSE)
    normalized = [item.upper().strip() for item in universe if item.strip()]
    return normalized or list(DEFAULT_UNIVERSE)


def _require_authenticated_user(
    deps: ApiDependencies,
    authorization: str | None,
    session_cookie: str | None,
) -> User:
    session_token = _extract_session_token(authorization, session_cookie)
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    try:
        user = deps.auth_use_case_factory().execute(session_token)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication failed: {exc}") from exc

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


def _is_anonymous_crm_enabled() -> bool:
    return os.getenv("ALLOW_ANONYMOUS_CRM", "false").strip().lower() == "true"


def _build_anonymous_crm_user(deps: ApiDependencies) -> User:
    user_repository = deps.user_repository_factory()
    if user_repository is not None and callable(getattr(user_repository, "upsert_authenticated_user", None)):
        return user_repository.upsert_authenticated_user(
            ExternalIdentity(
                provider="anonymous",
                issuer="brivoly.local",
                subject="guest-crm",
                session_id=None,
                email=None,
                given_name="Guest",
                family_name=None,
                display_name="Guest",
            )
        )
    current_time = deps.now()
    return User(
        id=ANONYMOUS_CRM_USER_ID,
        auth_provider="anonymous",
        auth_issuer="brivoly.local",
        auth_subject="guest-crm",
        stripe_customer_id=None,
        email=None,
        given_name="Guest",
        family_name=None,
        display_name="Guest",
        created_at=current_time,
        updated_at=current_time,
        last_login_at=current_time,
    )


def _require_crm_user(
    deps: ApiDependencies,
    authorization: str | None,
    session_cookie: str | None,
) -> User:
    session_token = _extract_session_token(authorization, session_cookie)
    if session_token:
        try:
            return _require_authenticated_user(deps, authorization, session_cookie)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_401_UNAUTHORIZED and _is_anonymous_crm_enabled():
                return _build_anonymous_crm_user(deps)
            raise
    if _is_anonymous_crm_enabled():
        return _build_anonymous_crm_user(deps)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")


def _build_default_dashboard_settings(user_id: UUID) -> UserDashboardSettings:
    return build_default_dashboard_settings(
        user_id,
        telegram_enabled=bool(os.environ.get("TELEGRAM_BOT_TOKEN")) and bool(os.environ.get("TELEGRAM_CHAT_ID")),
    )


@dataclass(frozen=True)
class _TelegramCommand:
    chat_id: str
    name: str
    argument: str | None
    text: str


@dataclass(frozen=True)
class _TelegramImageIntake:
    chat_id: str
    command_name: str
    intake_token: str
    file_id: str
    file_name: str


def _extract_telegram_command(payload: dict[str, object]) -> _TelegramCommand | None:
    message = payload.get("message")
    if not isinstance(message, dict):
        return None

    text = message.get("text")
    chat = message.get("chat")
    if not isinstance(text, str) or not isinstance(chat, dict):
        return None

    chat_id = chat.get("id")
    if chat_id is None:
        return None

    raw_text = text.strip()
    if not raw_text.startswith("/"):
        return None
    first_token, _, remainder = raw_text.partition(" ")
    normalized_name = first_token.split("@", 1)[0]
    argument = remainder.strip() or None
    normalized_text = normalized_name if argument is None else f"{normalized_name} {argument}"
    return _TelegramCommand(chat_id=str(chat_id), name=normalized_name, argument=argument, text=normalized_text)


def _extract_telegram_image_intake(payload: dict[str, object]) -> _TelegramImageIntake | None:
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return None
    caption = message.get("caption")
    if not isinstance(caption, str):
        return None
    raw_caption = caption.strip()
    if not raw_caption.startswith("/intake"):
        return None
    first_token, _, remainder = raw_caption.partition(" ")
    intake_token = remainder.strip()
    if not intake_token:
        return None
    command_name = first_token.split("@", 1)[0]
    photo = message.get("photo")
    if isinstance(photo, list) and photo:
        last_photo = photo[-1]
        if isinstance(last_photo, dict) and isinstance(last_photo.get("file_id"), str):
            return _TelegramImageIntake(
                chat_id=str(chat["id"]),
                command_name=command_name,
                intake_token=intake_token,
                file_id=last_photo["file_id"],
                file_name="telegram-photo.jpg",
            )
    document = message.get("document")
    if isinstance(document, dict) and isinstance(document.get("file_id"), str):
        mime_type = str(document.get("mime_type") or "")
        file_name = str(document.get("file_name") or "telegram-note")
        if mime_type.startswith("image/") or file_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            return _TelegramImageIntake(
                chat_id=str(chat["id"]),
                command_name=command_name,
                intake_token=intake_token,
                file_id=document["file_id"],
                file_name=file_name,
            )
    return None


def _validate_telegram_webhook_secret(provided_secret: str | None) -> None:
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if expected_secret and provided_secret != expected_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram webhook secret.")


def _validate_internal_cron_secret(provided_secret: str | None) -> None:
    expected_secret = (
        os.getenv("INTERNAL_CRON_SECRET", "").strip()
        or os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    )
    if not expected_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Internal cron secret is not configured.")
    if provided_secret != expected_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal cron secret.")


def _build_telegram_notifier(chat_id: str | None = None) -> TelegramNotifier:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    configured_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not configured_chat_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram bot is not configured.")
    return TelegramNotifier(bot_token=bot_token, chat_id=configured_chat_id)


def _queue_founder_code_request(command: _TelegramCommand) -> None:
    try:
        QueueFounderCodeRequestUseCase(build_founder_code_request_repository()).execute(
            chat_id=command.chat_id,
            command_text=command.text,
            guidance=command.argument,
        )
    except RuntimeError as exc:
        api_logger.warning("Unable to persist founder code request", exc_info=exc)


def _build_prospecting_status_message() -> str:
    if not is_prospect_agent_enabled():
        return "Prospect agent is disabled."
    errors = collect_prospecting_config_errors()
    openai_enabled = bool(get_first_configured_env("APP_OPENAI_API_KEY", "OPENAI_API_KEY"))
    if errors:
        return "Prospecting agent is not ready:\n- " + "\n- ".join(errors)
    model_line = (
        "OpenAI idea drafting enabled."
        if openai_enabled
        else "OpenAI idea drafting disabled; template opportunity ideas will be used."
    )
    return f"Prospecting agent is ready.\n{model_line}"


def _run_prospecting_from_telegram(notifier: TelegramNotifier) -> None:
    if not is_prospect_agent_enabled():
        try:
            notifier.send_message("Prospect agent is disabled for now.")
        except TelegramNotificationError:
            return
        return
    try:
        digest = run_prospecting_job()
        notifier.send_message(
            f"Prospecting finished. Scanned {digest.scanned_post_count} posts, shortlisted "
            f"{digest.shortlisted_count} opportunity signals, and sent the digest."
        )
    except (EmailNotificationError, RedditLeadSourceError, TelegramNotificationError, ValueError, RuntimeError) as exc:
        api_logger.exception("Prospecting run failed", exc_info=exc)
        try:
            notifier.send_message(f"Prospecting run failed: {exc}")
        except TelegramNotificationError:
            return


def _build_etf_sentiment_status_message() -> str:
    errors = collect_etf_sentiment_config_errors()
    openai_enabled = bool(get_first_configured_env("APP_OPENAI_API_KEY", "OPENAI_API_KEY"))
    if errors:
        return "ETF sentiment agent is not ready:\n- " + "\n- ".join(errors)
    model_line = (
        "OpenAI analysis enabled."
        if openai_enabled
        else "OpenAI analysis disabled; price-action template mode will be used."
    )
    return f"ETF sentiment agent is ready.\n{model_line}"


def _run_etf_sentiment_from_telegram(notifier: TelegramNotifier) -> None:
    try:
        deliver_etf_sentiment_job()
    except (EmailNotificationError, RedditLeadSourceError, TelegramNotificationError, ValueError, RuntimeError) as exc:
        api_logger.exception("ETF sentiment run failed", exc_info=exc)
        try:
            notifier.send_message(f"ETF sentiment run failed: {exc}")
        except TelegramNotificationError:
            return


def _run_code_from_telegram(notifier: TelegramNotifier, founder_guidance: str | None = None) -> None:
    if not is_prospect_agent_enabled():
        try:
            notifier.send_message("Queued your code request. The prospect agent is disabled for now.")
        except TelegramNotificationError:
            return
        return
    try:
        digest = run_prospecting_job(founder_guidance)
        brief = decide_autonomous_build_brief(digest, founder_guidance=founder_guidance)
        queue_path = append_autonomous_build_brief(brief)
        notifier.send_message(
            f"{format_autonomous_build_brief(brief)}\nQueue file: {queue_path}"
        )
    except (EmailNotificationError, RedditLeadSourceError, TelegramNotificationError, ValueError, RuntimeError) as exc:
        api_logger.exception("Cooperative code run failed", exc_info=exc)
        try:
            notifier.send_message(f"Cooperative code run failed: {exc}")
        except TelegramNotificationError:
            return


def _get_crm_intake_secret() -> str:
    return (
        os.getenv("CRM_INTAKE_SECRET", "").strip()
        or os.getenv("INTERNAL_CRON_SECRET", "").strip()
        or os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    )


def _build_crm_intake_token(user_id: UUID, secret: str) -> str:
    user_text = user_id.hex
    signature = hmac.new(secret.encode("utf-8"), user_text.encode("utf-8"), hashlib.sha256).hexdigest()[:12]
    return f"{user_text}.{signature}"


def _parse_crm_intake_token(token: str, secret: str) -> UUID:
    compact_user_id, separator, compact_signature = token.partition(".")
    if separator:
        if len(compact_user_id) != 32 or len(compact_signature) != 12:
            raise ValueError("The CRM intake code is invalid.")
        expected_signature = hmac.new(secret.encode("utf-8"), compact_user_id.encode("utf-8"), hashlib.sha256).hexdigest()[:12]
        if not hmac.compare_digest(compact_signature, expected_signature):
            raise ValueError("The CRM intake code is invalid.")
        return UUID(compact_user_id)

    padded = token + "=" * (-len(token) % 4)
    try:
        payload = base64.urlsafe_b64decode(padded.encode("ascii"))
        parsed = json.loads(payload.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("The CRM intake code is invalid.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("The CRM intake code is invalid.")
    user_id_text = parsed.get("user_id")
    signature = parsed.get("signature")
    if not isinstance(user_id_text, str) or not isinstance(signature, str):
        raise ValueError("The CRM intake code is invalid.")
    expected_signature = hmac.new(secret.encode("utf-8"), user_id_text.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("The CRM intake code is invalid.")
    return UUID(user_id_text)


def _download_telegram_file(bot_token: str, file_id: str) -> bytes:
    metadata_request = request.Request(
        url=f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}",
        method="GET",
    )
    try:
        with request.urlopen(metadata_request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - exercised via tests
        raise ValueError("Unable to download the Telegram note image.") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ValueError("Unable to download the Telegram note image.")
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("file_path"), str):
        raise ValueError("Unable to download the Telegram note image.")
    file_path = result["file_path"]
    file_request = request.Request(
        url=f"https://api.telegram.org/file/bot{bot_token}/{file_path}",
        method="GET",
    )
    try:
        with request.urlopen(file_request) as response:
            return response.read()
    except Exception as exc:  # pragma: no cover - exercised via tests
        raise ValueError("Unable to download the Telegram note image.") from exc


def _is_supported_crm_image_file_name(file_name: str) -> bool:
    normalized = file_name.lower()
    return normalized.endswith(".png") or normalized.endswith(".jpg") or normalized.endswith(".jpeg") or normalized.endswith(".webp")


def _commit_crm_image_intake(
    *,
    intake_token: str,
    file_name: str,
    file_bytes: bytes,
    deps: ApiDependencies,
):
    secret = _get_crm_intake_secret()
    if not secret:
        raise ValueError("Remote CRM note capture is not configured yet.")
    if not _is_supported_crm_image_file_name(file_name):
        raise ValueError("Upload a supported image file: .png, .jpg, .jpeg, or .webp.")
    if not file_bytes:
        raise ValueError("Choose an image file before uploading.")

    user_id = _parse_crm_intake_token(intake_token, secret)
    user_repository = deps.user_repository_factory()
    if user_repository is None:
        raise ValueError("Remote CRM note capture needs the app database to be configured.")
    user = user_repository.get_user_by_id(user_id)
    if user is None:
        raise ValueError("That CRM intake link no longer points to an active Brivoly account.")
    _ensure_advanced_ai_intake_access(user, deps)
    settings = GetUserDashboardSettingsUseCase(
        repository=deps.personalization_repository_factory(),
        default_factory=_build_default_dashboard_settings,
    ).execute(user)
    csv_content = GenerateLeadImportFromImageUseCase(
        image_intake=build_crm_image_intake_agent_from_env(),
    ).execute(
        prompt=settings.crm_ai_prompt,
        preferred_formats=settings.crm_preferred_import_formats,
        file_name=file_name,
        file_bytes=file_bytes,
    )
    return CommitLeadImportUseCase(
        repository=deps.lead_follow_up_repository_factory(),
        now=deps.now,
    ).execute(
        user,
        csv_content,
        "image",
        file_name,
    )


def _run_telegram_crm_image_intake(
    notifier: TelegramNotifier,
    intake: _TelegramImageIntake,
    deps: ApiDependencies,
) -> None:
    try:
        secret = _get_crm_intake_secret()
        if not secret:
            raise ValueError("Remote CRM note capture is not configured yet.")
        user_id = _parse_crm_intake_token(intake.intake_token, secret)
        user_repository = deps.user_repository_factory()
        if user_repository is None:
            raise ValueError("Remote CRM note capture needs the app database to be configured.")
        user = user_repository.get_user_by_id(user_id)
        if user is None:
            raise ValueError("That CRM intake link no longer points to an active Brivoly account.")
        _ensure_advanced_ai_intake_access(user, deps)
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not bot_token:
            raise ValueError("Telegram bot token is not configured.")
        file_bytes = _download_telegram_file(bot_token, intake.file_id)
        result = _commit_crm_image_intake(
            intake_token=intake.intake_token,
            file_name=intake.file_name,
            file_bytes=file_bytes,
            deps=deps,
        )
        notifier.send_message(
            "Brivoly imported your note image into CRM.\n"
            f"Imported: {result.imported_count}\n"
            f"Skipped duplicates: {result.skipped_duplicates}\n"
            f"Skipped invalid: {result.skipped_invalid}"
        )
    except (EmailNotificationError, TelegramNotificationError, ValueError, RuntimeError) as exc:
        api_logger.exception("Telegram CRM image intake failed", exc_info=exc)
        try:
            notifier.send_message(f"CRM note import failed: {exc}")
        except TelegramNotificationError:
            return


def _resolve_crm_import_source(
    payload: LeadImportPayload,
    user: User | None = None,
    deps: ApiDependencies | None = None,
) -> tuple[str, str, str]:
    if payload.source_type == "csv":
        if not payload.csv_content:
            raise ValueError("CSV content is required for spreadsheet import.")
        return payload.csv_content, "CSV upload", "csv"
    if payload.source_type == "excel":
        if not payload.file_name:
            raise ValueError("Spreadsheet file name is required.")
        if not payload.file_content_base64:
            raise ValueError("Spreadsheet file content is required.")
        file_bytes = decode_base64_file_content(payload.file_content_base64)
        csv_content = convert_excel_bytes_to_csv(payload.file_name, file_bytes)
        return csv_content, payload.file_name, "excel"
    if payload.source_type == "image":
        if not payload.file_name:
            raise ValueError("Image file name is required.")
        if not payload.file_content_base64:
            raise ValueError("Image file content is required.")
        if user is None or deps is None:
            raise ValueError("Authenticated image intake context is required.")
        _ensure_advanced_ai_intake_access(user, deps)
        settings = GetUserDashboardSettingsUseCase(
            repository=deps.personalization_repository_factory(),
            default_factory=_build_default_dashboard_settings,
        ).execute(user)
        file_bytes = decode_base64_file_content(payload.file_content_base64)
        csv_content = GenerateLeadImportFromImageUseCase(
            image_intake=build_crm_image_intake_agent_from_env(),
        ).execute(
            prompt=settings.crm_ai_prompt,
            preferred_formats=settings.crm_preferred_import_formats,
            file_name=payload.file_name,
            file_bytes=file_bytes,
        )
        return csv_content, payload.file_name, "image"
    if payload.source_type == "google_sheets":
        if not payload.sheet_url:
            raise ValueError("A Google Sheets URL is required.")
        return fetch_google_sheets_csv(payload.sheet_url), "Google Sheets", "google_sheets"
    raise ValueError("Unsupported import source.")


def _preview_crm_import_with_optional_ai_assistance(
    *,
    user: User,
    repository,
    now: Callable[[], datetime],
    csv_content: str,
    source_type: str,
    source_label: str,
    field_mapping: dict[str, str | None] | None,
    clarification_answers: dict[str, str] | None,
    row_overrides: dict[str, dict[str, str]] | None,
    settings: UserDashboardSettings,
    deps: ApiDependencies,
):
    try:
        preview = PreviewLeadImportUseCase(repository=repository, now=now).execute(
            user,
            csv_content,
            source_type,
            source_label,
            field_mapping,
            row_overrides,
        )
    except ValueError as exc:
        if str(exc) != "No recognizable CRM headers were found in the spreadsheet.":
            raise
    else:
        if preview.importable_rows > 0:
            return preview
        mapped_fields = {item.mapped_field for item in preview.header_mappings if item.mapped_field}
        has_identity = "lead_name" in mapped_fields or "company_name" in mapped_fields
        has_follow_up = "next_follow_up_at" in mapped_fields
        if has_identity and has_follow_up:
            return preview

    _ensure_advanced_ai_intake_access(user, deps)
    return PreviewLeadImportWithAssistanceUseCase(
        repository=repository,
        now=now,
        spreadsheet_assist=build_crm_spreadsheet_assist_agent_from_env(),
    ).execute(
        user,
        csv_content,
        source_type,
        source_label,
        prompt=settings.crm_ai_prompt,
        preferred_formats=settings.crm_preferred_import_formats,
        field_mapping_overrides=field_mapping,
        clarification_answers=clarification_answers,
        row_overrides=row_overrides,
    )


def _ensure_advanced_ai_intake_access(user: User, deps: ApiDependencies) -> None:
    billing = deps.billing_port_factory()
    if billing is None:
        return
    overview = GetBillingOverviewUseCase(billing).execute(user)
    if not overview.enabled:
        return
    if overview.subscription_status not in {"active", "trialing"}:
        raise ValueError("AI note image intake is available on active or trialing paid plans.")


class _DisabledBillingPort:
    def get_billing_overview(self, user: User):  # type: ignore[no-untyped-def]
        from src.application.billing import BillingOverview

        return BillingOverview(
            enabled=False,
            customer_id=None,
            subscription_id=None,
            subscription_status=None,
            price_id=None,
            cancel_at_period_end=False,
            current_period_end=None,
            checkout_available=False,
            portal_available=False,
        )

    def create_checkout_session(self, user: User, return_url: str | None = None) -> str:
        raise RuntimeError("Stripe billing is not configured.")

    def create_portal_session(self, user: User, return_url: str | None = None) -> str:
        raise RuntimeError("Stripe billing is not configured.")


app = create_app()
