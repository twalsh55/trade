from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import Callable
from uuid import UUID
from uuid import uuid4

from fastapi import Cookie, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.adapters.api.observability import (
    REQUEST_ID_HEADER,
    build_runtime_report,
    configure_api_logger,
)
from src.adapters.auth.clerk_auth import AuthenticationError
from src.adapters.auth.runtime import (
    CLERK_SESSION_COOKIE,
    build_authenticate_user_use_case,
    derive_clerk_frontend_api_host,
    get_app_base_url,
    get_configured_clerk_page_url,
)
from src.adapters.market_data.yfinance_provider import YFinanceMarketDataAdapter
from src.adapters.persistence.runtime import build_personalization_repository
from src.application.account import (
    AlertHistoryEntry,
    GetUserDashboardSettingsUseCase,
    ListAlertHistoryUseCase,
    UpdateUserDashboardSettingsUseCase,
    UserDashboardSettings,
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
    build_dashboard_snapshot_dto,
    build_user_dashboard_settings_dto,
    dto_to_dict,
)
from src.application.use_cases import BuildCrashDashboardUseCase
from src.domain.auth import User
from src.domain.models import DEFAULT_UNIVERSE
from src.env_utils import load_env_file


@dataclass(frozen=True)
class ApiDependencies:
    auth_use_case_factory: Callable[[], object]
    market_data_factory: Callable[[], object]
    personalization_repository_factory: Callable[[], object]
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


def create_app(dependencies: ApiDependencies | None = None) -> FastAPI:
    load_env_file()
    logger = configure_api_logger()
    deps = dependencies or ApiDependencies(
        auth_use_case_factory=build_authenticate_user_use_case,
        market_data_factory=YFinanceMarketDataAdapter,
        personalization_repository_factory=build_personalization_repository,
        now=lambda: datetime.now(tz=UTC),
    )
    app = FastAPI(title="Trade API", version="0.1.0")

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


app = create_app()
