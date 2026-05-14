from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

import pandas as pd
from fastapi.testclient import TestClient
import pytest

from src.adapters.api.app import ApiDependencies, _normalize_universe, create_app
from src.adapters.auth.clerk_auth import AuthenticationError
from src.adapters.persistence.in_memory_personalization_repository import InMemoryPersonalizationRepository
from src.application.account import (
    AlertHistoryEntry,
    GetUserDashboardSettingsUseCase,
    ListAlertHistoryUseCase,
    UpdateUserDashboardSettingsUseCase,
    UserDashboardSettings,
)
from src.application.dashboard import (
    build_dashboard_config,
    build_default_dashboard_settings,
    normalize_dashboard_settings,
)
from src.application.dto import (
    _iso_date,
    build_alert_history_entry_dto,
    build_authenticated_user_dto,
    build_dashboard_snapshot_dto,
    build_user_dashboard_settings_dto,
    dto_to_dict,
)
from src.domain.auth import User
from src.domain.models import DashboardConfig, DashboardResult


def make_user() -> User:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    return User(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        auth_provider="clerk",
        auth_issuer="https://example.clerk.accounts.dev",
        auth_subject="user_123",
        email="user@example.com",
        given_name="Ada",
        family_name="Lovelace",
        display_name="Ada Lovelace",
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


def make_dashboard_result() -> DashboardResult:
    dates = pd.bdate_range("2024-01-02", periods=260)
    benchmark = pd.Series(range(100, 360), index=dates, dtype=float)
    close = pd.DataFrame(
        {
            "SPY": benchmark,
            "QQQ": benchmark + 50,
            "IWM": benchmark - 10,
            "EFA": benchmark - 20,
            "EEM": benchmark - 30,
            "^VIX": pd.Series(range(20, 280), index=dates, dtype=float),
            "HYG": pd.Series(range(90, 350), index=dates, dtype=float),
            "^IRX": pd.Series([52.0] * len(dates), index=dates, dtype=float),
            "^TNX": pd.Series([41.0] * len(dates), index=dates, dtype=float),
        }
    )
    indicator_percentiles = pd.DataFrame(
        [
            {
                "Indicator": "Price",
                "Current": 359.0,
                "P5": 110.0,
                "P50": 220.0,
                "P95": 350.0,
            },
            {
                "Indicator": "VIX",
                "Current": float("nan"),
                "P5": 22.0,
                "P50": 30.0,
                "P95": 40.0,
            },
        ]
    )
    return DashboardResult(
        close_data=close,
        metrics={
            "price": 359.0,
            "ma50": 334.5,
            "ma200": 259.5,
            "drawdown_252": -0.04,
            "vol20": 0.12,
            "rsi14": 61.0,
            "breadth_ratio": 0.82,
            "yield_curve_spread": -1.1,
        },
        indicator_percentiles=indicator_percentiles,
        risk_score=38.2,
        risk_components={"Trend stress": 10.0, "Yield curve stress": 80.0},
        regime="Constructive (Low Crash Stress)",
        actions=["Maintain strategic risk."],
    )


@dataclass
class FakeAuthUseCase:
    user: User | None = None
    error: Exception | None = None
    seen_tokens: list[str] | None = None

    def execute(self, session_token: str) -> User | None:
        if self.seen_tokens is not None:
            self.seen_tokens.append(session_token)
        if self.error is not None:
            raise self.error
        return self.user


class FakeMarketDataAdapter:
    def __init__(self, result: DashboardResult, captured_configs: list[DashboardConfig]) -> None:
        self.result = result
        self.captured_configs = captured_configs

    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        self.captured_configs.append(
            DashboardConfig(
                universe=tickers,
                benchmark="SPY",
                vix_symbol="^VIX",
                risk_proxy="HYG",
                short_yield_symbol="^IRX",
                long_yield_symbol="^TNX",
                start_date=start_date,
                end_date=end_date,
            )
        )
        return self.result.close_data


def make_client(
    *,
    user: User | None = None,
    auth_error: Exception | None = None,
    dashboard_result: DashboardResult | None = None,
    seen_tokens: list[str] | None = None,
    personalization_repository: InMemoryPersonalizationRepository | None = None,
) -> TestClient:
    result = dashboard_result or make_dashboard_result()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    auth_use_case = FakeAuthUseCase(user=user, error=auth_error, seen_tokens=seen_tokens)
    repository = personalization_repository or InMemoryPersonalizationRepository()
    app = create_app(
        ApiDependencies(
            auth_use_case_factory=lambda: auth_use_case,
            market_data_factory=lambda: FakeMarketDataAdapter(result=result, captured_configs=[]),
            personalization_repository_factory=lambda: repository,
            now=lambda: now,
        )
    )
    return TestClient(app)


def test_authenticated_user_dto_serializes_values() -> None:
    dto = build_authenticated_user_dto(make_user())

    assert dto.id == "11111111-1111-1111-1111-111111111111"
    assert dto.email == "user@example.com"
    assert dto.created_at == "2024-05-06T12:30:00+00:00"


def test_account_settings_and_alert_history_dtos_serialize_values() -> None:
    settings = UserDashboardSettings(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        universe=["SPY", "QQQ"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        lookback_years=4,
        telegram_enabled=True,
    )
    alert = AlertHistoryEntry(
        occurred_at=datetime(2024, 5, 6, 12, 30, tzinfo=UTC),
        category="settings",
        severity="info",
        title="Updated",
        message="Settings changed.",
    )

    settings_payload = dto_to_dict(build_user_dashboard_settings_dto(settings))
    alert_payload = dto_to_dict(build_alert_history_entry_dto(alert))

    assert settings_payload["universe"] == ["SPY", "QQQ"]
    assert settings_payload["telegram_enabled"] is True
    assert alert_payload["title"] == "Updated"
    assert alert_payload["occurred_at"] == "2024-05-06T12:30:00+00:00"


def test_dashboard_snapshot_dto_serializes_frontend_safe_shapes() -> None:
    config = DashboardConfig(
        universe=["SPY", "QQQ"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 5, 6),
    )
    dto = build_dashboard_snapshot_dto(config, make_dashboard_result(), datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    payload = dto_to_dict(dto)

    assert payload["config"]["benchmark"] == "SPY"
    assert payload["indicator_percentiles"][1]["current"] is None
    assert payload["price_history"][0]["date"] == "2024-01-02"
    assert payload["market_breadth_history"][-1]["new_high_ratio_252"] is not None
    assert _iso_date("already-a-string") == "already-a-string"
    assert _normalize_universe(None) == ["SPY", "QQQ", "IWM", "EFA", "EEM"]
    assert _normalize_universe(["", " "]) == ["SPY", "QQQ", "IWM", "EFA", "EEM"]


def test_account_use_cases_and_in_memory_repository_round_trip_settings_and_alerts() -> None:
    repository = InMemoryPersonalizationRepository()
    user = make_user()
    defaults = UserDashboardSettings(
        user_id=user.id,
        universe=["SPY"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        lookback_years=4,
        telegram_enabled=False,
    )
    get_use_case = GetUserDashboardSettingsUseCase(repository=repository, default_factory=lambda user_id: defaults)
    update_use_case = UpdateUserDashboardSettingsUseCase(repository=repository)
    alerts_use_case = ListAlertHistoryUseCase(repository=repository)

    assert get_use_case.execute(user) == defaults

    saved = update_use_case.execute(
        user,
        UserDashboardSettings(
            user_id=UUID("22222222-2222-2222-2222-222222222222"),
            universe=["spy", "qqq"],
            benchmark="QQQ",
            vix_symbol="^VIX",
            risk_proxy="HYG",
            short_yield_symbol="^IRX",
            long_yield_symbol="^TNX",
            lookback_years=2,
            telegram_enabled=True,
        ),
    )

    assert saved.user_id == user.id
    assert repository.get_dashboard_settings(user.id) == saved

    repository.append_alert_history(
        user.id,
        AlertHistoryEntry(
            occurred_at=datetime(2024, 5, 6, 13, 0, tzinfo=UTC),
            category="settings",
            severity="info",
            title="Saved",
            message="Updated dashboard defaults.",
        ),
    )

    entries = alerts_use_case.execute(user, limit=5)
    assert entries[0].title == "Saved"
    assert repository.list_alert_history(UUID("33333333-3333-3333-3333-333333333333"), 1)[0].category == "system"


def test_dashboard_settings_helpers_normalize_defaults_and_build_config() -> None:
    user = make_user()

    defaults = build_default_dashboard_settings(user.id, telegram_enabled=True)
    assert defaults.universe == ["SPY", "QQQ", "IWM", "EFA", "EEM"]
    assert defaults.telegram_enabled is True

    normalized = normalize_dashboard_settings(
        UserDashboardSettings(
            user_id=user.id,
            universe=[" spy ", "", "qqq"],
            benchmark=" spy ",
            vix_symbol=" ^vix ",
            risk_proxy=" hyg ",
            short_yield_symbol=" ^irx ",
            long_yield_symbol=" ^tnx ",
            lookback_years=2,
            telegram_enabled=False,
        )
    )
    assert normalized.universe == ["SPY", "QQQ"]
    assert normalized.benchmark == "SPY"
    assert normalized.vix_symbol == "^VIX"

    config = build_dashboard_config(normalized, end_date=date(2024, 5, 6))
    assert config.start_date == date(2022, 5, 7)
    assert config.end_date == date(2024, 5, 6)


def test_healthcheck_and_settings_bootstrap_work(monkeypatch) -> None:
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "")
    client = make_client(user=make_user())

    assert client.get("/healthz").json() == {"status": "ok"}

    settings_response = client.get("/api/settings/bootstrap")

    assert settings_response.status_code == 200
    assert settings_response.json()["default_benchmark"] == "SPY"
    assert settings_response.json()["clerk_publishable_key"] is None


def test_settings_bootstrap_includes_clerk_host_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")
    monkeypatch.setenv("CLERK_SIGN_IN_URL", "https://accounts.example.com/sign-in")
    client = make_client(user=make_user())

    response = client.get("/api/settings/bootstrap")

    assert response.status_code == 200
    assert response.json()["clerk_publishable_key"] == "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"
    assert response.json()["clerk_frontend_api_host"] == "example.clerk.accounts.dev"
    assert response.json()["clerk_sign_in_url"].startswith("https://accounts.example.com/sign-in")


def test_session_bootstrap_handles_missing_valid_and_invalid_tokens() -> None:
    seen_tokens: list[str] = []
    client = make_client(user=make_user(), seen_tokens=seen_tokens)

    anonymous_response = client.get("/api/session")
    assert anonymous_response.status_code == 200
    assert anonymous_response.json() == {"authenticated": False, "user": None}

    authenticated_response = client.get("/api/session", headers={"Authorization": "Bearer session-token"})
    assert authenticated_response.status_code == 200
    assert authenticated_response.json()["authenticated"] is True
    assert authenticated_response.json()["user"]["display_name"] == "Ada Lovelace"
    assert seen_tokens == ["session-token"]

    bad_scheme_response = client.get("/api/session", headers={"Authorization": "Token nope"})
    assert bad_scheme_response.status_code == 401
    assert bad_scheme_response.json()["detail"] == "Authorization header must use a Bearer token."


def test_session_bootstrap_maps_runtime_and_auth_errors() -> None:
    unavailable_client = make_client(auth_error=RuntimeError("db unavailable"))
    unavailable_response = unavailable_client.get("/api/session", headers={"Authorization": "Bearer token"})
    assert unavailable_response.status_code == 503
    assert unavailable_response.json()["detail"] == "db unavailable"

    invalid_client = make_client(auth_error=AuthenticationError("bad token"))
    invalid_response = invalid_client.get("/api/session", headers={"Authorization": "Bearer token"})
    assert invalid_response.status_code == 401
    assert invalid_response.json()["detail"] == "Authentication failed: bad token"

    unauthenticated_client = make_client(user=None)
    unauthenticated_response = unauthenticated_client.get("/api/session", headers={"Authorization": "Bearer token"})
    assert unauthenticated_response.status_code == 200
    assert unauthenticated_response.json() == {"authenticated": False, "user": None}


def test_dashboard_endpoint_requires_auth_and_returns_snapshot() -> None:
    client = make_client(user=make_user())

    unauthorized_response = client.get("/api/dashboard")
    assert unauthorized_response.status_code == 401
    assert unauthorized_response.json()["detail"] == "Authentication required."

    response = client.get(
        "/api/dashboard",
        headers={"Authorization": "Bearer session-token"},
        params={
            "universe": ["spy", "qqq", ""],
            "benchmark": "spy",
            "vix_symbol": "^vix",
            "risk_proxy": "hyg",
            "short_yield_symbol": "^irx",
            "long_yield_symbol": "^tnx",
            "lookback_years": 2,
            "end_date": "2024-05-06",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["benchmark"] == "SPY"
    assert payload["config"]["universe"] == ["SPY", "QQQ"]
    assert payload["risk_score"] == pytest.approx(25.128205128205128)
    assert payload["regime"] == "Constructive (Low Crash Stress)"
    assert payload["price_history"][-1]["price"] == 359.0

    client.cookies.set("__session", "cookie-token")
    cookie_response = client.get("/api/dashboard")
    assert cookie_response.status_code == 200


def test_dashboard_endpoint_uses_default_universe_when_given_empty_values() -> None:
    client = make_client(user=make_user())

    response = client.get(
        "/api/dashboard",
        headers={"Authorization": "Bearer session-token"},
        params={"universe": ["", " "]},
    )

    assert response.status_code == 200
    assert response.json()["config"]["universe"] == ["SPY", "QQQ", "IWM", "EFA", "EEM"]


def test_account_settings_endpoints_and_alert_history_round_trip() -> None:
    repository = InMemoryPersonalizationRepository()
    client = make_client(user=make_user(), personalization_repository=repository)

    unauthorized_settings = client.get("/api/account/settings")
    assert unauthorized_settings.status_code == 401
    assert unauthorized_settings.json()["detail"] == "Authentication required."

    settings_response = client.get("/api/account/settings", headers={"Authorization": "Bearer session-token"})
    assert settings_response.status_code == 200
    assert settings_response.json()["benchmark"] == "SPY"
    assert settings_response.json()["lookback_years"] == 4

    update_response = client.put(
        "/api/account/settings",
        headers={"Authorization": "Bearer session-token"},
        json={
            "universe": ["spy", "qqq"],
            "benchmark": "qqq",
            "vix_symbol": "^vix",
            "risk_proxy": "hyg",
            "short_yield_symbol": "^irx",
            "long_yield_symbol": "^tnx",
            "lookback_years": 3,
            "telegram_enabled": True,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["benchmark"] == "QQQ"
    assert update_response.json()["universe"] == ["SPY", "QQQ"]
    assert update_response.json()["telegram_enabled"] is True

    alerts_response = client.get("/api/alerts/history", headers={"Authorization": "Bearer session-token"})
    assert alerts_response.status_code == 200
    assert alerts_response.json()["count"] == 1
    assert alerts_response.json()["items"][0]["category"] == "settings"

    updated_dashboard = client.get("/api/dashboard", headers={"Authorization": "Bearer session-token"})
    assert updated_dashboard.status_code == 200
    assert updated_dashboard.json()["config"]["benchmark"] == "QQQ"
    assert updated_dashboard.json()["config"]["universe"] == ["SPY", "QQQ"]


def test_account_settings_validation_and_alert_defaults_work() -> None:
    client = make_client(user=make_user())

    invalid_update = client.put(
        "/api/account/settings",
        headers={"Authorization": "Bearer session-token"},
        json={
            "universe": [],
            "benchmark": "SPY",
            "vix_symbol": "^VIX",
            "risk_proxy": "HYG",
            "short_yield_symbol": "^IRX",
            "long_yield_symbol": "^TNX",
            "lookback_years": 0,
            "telegram_enabled": False,
        },
    )
    assert invalid_update.status_code == 422

    alerts_response = client.get(
        "/api/alerts/history",
        headers={"Authorization": "Bearer session-token"},
        params={"limit": 1},
    )
    assert alerts_response.status_code == 200
    assert alerts_response.json()["count"] == 1
    assert alerts_response.json()["items"][0]["title"] == "Alert history not persisted yet"


def test_dashboard_endpoint_maps_auth_errors_and_missing_users() -> None:
    unavailable_client = make_client(auth_error=RuntimeError("db unavailable"))
    unavailable_response = unavailable_client.get("/api/dashboard", headers={"Authorization": "Bearer token"})
    assert unavailable_response.status_code == 503
    assert unavailable_response.json()["detail"] == "db unavailable"

    invalid_client = make_client(auth_error=AuthenticationError("bad token"))
    invalid_response = invalid_client.get("/api/dashboard", headers={"Authorization": "Bearer token"})
    assert invalid_response.status_code == 401
    assert invalid_response.json()["detail"] == "Authentication failed: bad token"

    anonymous_client = make_client(user=None)
    anonymous_response = anonymous_client.get("/api/dashboard", headers={"Authorization": "Bearer token"})
    assert anonymous_response.status_code == 401
    assert anonymous_response.json()["detail"] == "Authentication required."

    unavailable_settings = unavailable_client.get("/api/account/settings", headers={"Authorization": "Bearer token"})
    assert unavailable_settings.status_code == 503

    invalid_alerts = invalid_client.get("/api/alerts/history", headers={"Authorization": "Bearer token"})
    assert invalid_alerts.status_code == 401


def test_dashboard_endpoint_maps_value_errors_to_422() -> None:
    def raising_client() -> TestClient:
        app = create_app(
            ApiDependencies(
                auth_use_case_factory=lambda: FakeAuthUseCase(user=make_user()),
                market_data_factory=lambda: type(
                    "BrokenMarketData",
                    (),
                    {
                        "load_close_data": staticmethod(lambda tickers, start_date, end_date: pd.DataFrame()),
                    },
                )(),
                personalization_repository_factory=lambda: InMemoryPersonalizationRepository(),
                now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC),
            )
        )
        return TestClient(app)

    response = raising_client().get("/api/dashboard", headers={"Authorization": "Bearer session-token"})

    assert response.status_code == 422
    assert "Could not load market data" in response.json()["detail"]
