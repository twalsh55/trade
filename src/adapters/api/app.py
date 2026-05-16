from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import Callable
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
from src.adapters.market_data.yfinance_provider import YFinanceMarketDataAdapter
from src.adapters.notifications.smtp_email_notifier import EmailNotificationError
from src.adapters.notifications.telegram_notifier import TelegramNotificationError, TelegramNotifier
from src.adapters.operator_briefing.runtime import collect_operator_briefing_config_errors, run_daily_operator_briefing_job
from src.adapters.crm.runtime import build_lead_follow_up_repository
from src.adapters.persistence.runtime import build_personalization_repository
from src.adapters.prospecting.runtime import collect_prospecting_config_errors, run_prospecting_job
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
from src.application.crm import GetLeadFollowUpOverviewUseCase
from src.application.crm import AddLeadFollowUpNoteUseCase, CompleteLeadFollowUpUseCase, SnoozeLeadFollowUpUseCase
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
    build_lead_follow_up_overview_dto,
    build_user_dashboard_settings_dto,
    dto_to_dict,
)
from src.application.use_cases import BuildCrashDashboardUseCase
from src.domain.auth import User
from src.domain.models import DEFAULT_UNIVERSE
from src.env_utils import get_first_configured_env, load_env_file

api_logger = logging.getLogger("brivoly.api")


@dataclass(frozen=True)
class ApiDependencies:
    auth_use_case_factory: Callable[[], object]
    market_data_factory: Callable[[], object]
    personalization_repository_factory: Callable[[], object]
    lead_follow_up_repository_factory: Callable[[], object]
    billing_port_factory: Callable[[], object | None]
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


class BillingSessionPayload(BaseModel):
    return_url: str | None = None


class LeadFollowUpActionPayload(BaseModel):
    action: str
    snooze_hours: int | None = Field(default=None, ge=1, le=24 * 14)
    note_body: str | None = Field(default=None, min_length=1, max_length=1000)


def create_app(dependencies: ApiDependencies | None = None) -> FastAPI:
    load_env_file()
    logger = configure_api_logger()
    deps = dependencies or ApiDependencies(
        auth_use_case_factory=build_authenticate_user_use_case,
        market_data_factory=YFinanceMarketDataAdapter,
        personalization_repository_factory=build_personalization_repository,
        lead_follow_up_repository_factory=build_lead_follow_up_repository,
        billing_port_factory=build_billing_adapter,
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
        user = _require_authenticated_user(deps, authorization, session_cookie)
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
        user = _require_authenticated_user(deps, authorization, session_cookie)
        repository = deps.personalization_repository_factory()
        settings = UpdateUserDashboardSettingsUseCase(repository=repository).execute(
            user,
            normalize_dashboard_settings(
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

    @app.get("/api/alerts/history")
    def alerts_history(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        user = _require_authenticated_user(deps, authorization, session_cookie)
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
        user = _require_authenticated_user(deps, authorization, session_cookie)
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
        user = _require_authenticated_user(deps, authorization, session_cookie)
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

    @app.get("/api/account/billing")
    def billing_overview(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=CLERK_SESSION_COOKIE),
    ) -> dict[str, object]:
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
            guidance_notice = f" Founder guidance received: {command.argument}." if command.argument else ""
            notifier.send_message(
                "Starting a cooperative code run now. I will send a build recommendation when it finishes."
                f"{guidance_notice}"
            )
            background_tasks.add_task(_run_code_from_telegram, notifier, command.argument)
            return {"ok": True, "handled": True, "command": command.name}
        if command.name == "/help" and command.argument is None:
            notifier.send_message(
                "Supported commands:\n"
                "/prospect - run the prospecting agent\n"
                "/prospect status - show whether the prospecting agent is configured\n"
                "/sentiment - run the ETF sentiment agent\n"
                "/sentiment status - show whether the ETF sentiment agent is configured\n"
                "/code - run the prospect agent and queue a build recommendation\n"
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

    return app


def _extract_session_token(authorization: str | None, session_cookie: str | None) -> str | None:
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


def _build_telegram_notifier() -> TelegramNotifier:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram bot is not configured.")
    return TelegramNotifier(bot_token=bot_token, chat_id=chat_id)


def _build_prospecting_status_message() -> str:
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
