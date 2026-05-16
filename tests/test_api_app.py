from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

import pandas as pd
from fastapi.testclient import TestClient
import pytest

from src.adapters.api.app import (
    ApiDependencies,
    _DisabledBillingPort,
    _TelegramCommand,
    _build_etf_sentiment_status_message,
    _build_prospecting_status_message,
    _extract_telegram_command,
    _normalize_universe,
    _run_code_from_telegram,
    _run_etf_sentiment_from_telegram,
    _run_prospecting_from_telegram,
    create_app,
)
from src.adapters.auth.clerk_auth import AuthenticationError
from src.adapters.crm.in_memory_follow_up_repository import InMemoryLeadFollowUpRepository
from src.adapters.persistence.in_memory_personalization_repository import InMemoryPersonalizationRepository
from src.application.account import (
    AlertHistoryEntry,
    GetUserDashboardSettingsUseCase,
    ListAlertHistoryUseCase,
    UpdateUserDashboardSettingsUseCase,
    UserDashboardSettings,
)
from src.application.billing import BillingOverview
from src.application.crm import GetLeadFollowUpOverviewUseCase
from src.application.founder_code import FounderCodeRequest
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
    build_lead_follow_up_overview_dto,
    build_user_dashboard_settings_dto,
    dto_to_dict,
)
from src.domain.auth import User
from src.domain.crm import LeadFollowUp, LeadTimelineEntry
from src.domain.models import DashboardConfig, DashboardResult


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


@dataclass
class FakeBillingPort:
    overview: BillingOverview | None = None
    checkout_url: str = "https://checkout.stripe.test/session_123"
    portal_url: str = "https://billing.stripe.test/session_123"
    seen_return_urls: list[str | None] | None = None

    def get_billing_overview(self, user: User) -> BillingOverview:
        return self.overview or BillingOverview(
            enabled=True,
            customer_id="cus_123",
            subscription_id="sub_123",
            subscription_status="active",
            price_id="price_123",
            cancel_at_period_end=False,
            current_period_end=datetime(2024, 6, 1, tzinfo=UTC),
            checkout_available=False,
            portal_available=True,
        )

    def create_checkout_session(self, user: User, return_url: str | None = None) -> str:
        if self.seen_return_urls is not None:
            self.seen_return_urls.append(return_url)
        return self.checkout_url

    def create_portal_session(self, user: User, return_url: str | None = None) -> str:
        if self.seen_return_urls is not None:
            self.seen_return_urls.append(return_url)
        return self.portal_url


def make_client(
    *,
    user: User | None = None,
    auth_error: Exception | None = None,
    dashboard_result: DashboardResult | None = None,
    seen_tokens: list[str] | None = None,
    personalization_repository: InMemoryPersonalizationRepository | None = None,
    lead_follow_up_repository: InMemoryLeadFollowUpRepository | None = None,
    billing_port: FakeBillingPort | None = None,
) -> TestClient:
    result = dashboard_result or make_dashboard_result()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    auth_use_case = FakeAuthUseCase(user=user, error=auth_error, seen_tokens=seen_tokens)
    repository = personalization_repository or InMemoryPersonalizationRepository()
    crm_repository = lead_follow_up_repository or InMemoryLeadFollowUpRepository(now=lambda: now)
    app = create_app(
        ApiDependencies(
            auth_use_case_factory=lambda: auth_use_case,
            market_data_factory=lambda: FakeMarketDataAdapter(result=result, captured_configs=[]),
            personalization_repository_factory=lambda: repository,
            lead_follow_up_repository_factory=lambda: crm_repository,
            billing_port_factory=lambda: billing_port,
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


def test_billing_overview_route_returns_disabled_status_when_stripe_is_unconfigured() -> None:
    response = make_client(user=make_user()).get("/api/account/billing", headers={"Authorization": "Bearer session-token"})

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "customer_id": None,
        "subscription_id": None,
        "subscription_status": None,
        "price_id": None,
        "cancel_at_period_end": False,
        "current_period_end": None,
        "checkout_available": False,
        "portal_available": False,
    }


def test_crm_follow_up_overview_dto_and_use_case_sort_and_count_values() -> None:
    user = make_user()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    items = [
        LeadFollowUp(
            id="a",
            lead_name="Amber",
            company_name="Northstar",
            stage="Discovery",
            priority="high",
            contact_channel="email",
            last_contacted_at=now,
            next_follow_up_at=now - pd.Timedelta(hours=1),
            next_step="Follow up",
            notes="Warm lead",
            timeline=(
                LeadTimelineEntry(
                    id="a-1",
                    occurred_at=now,
                    kind="call",
                    channel="phone",
                    summary="Discovery call complete.",
                ),
            ),
        ),
        LeadFollowUp(
            id="b",
            lead_name="Ben",
            company_name="Riverbridge",
            stage="Proposal",
            priority="medium",
            contact_channel="phone",
            last_contacted_at=None,
            next_follow_up_at=now + pd.Timedelta(days=1),
            next_step="Check proposal",
            notes="Waiting on stakeholder",
            timeline=(),
        ),
    ]

    class FakeRepository:
        def list_lead_follow_ups(self, user: User) -> list[LeadFollowUp]:
            return items

    overview = GetLeadFollowUpOverviewUseCase(FakeRepository(), now=lambda: now).execute(user)
    payload = dto_to_dict(build_lead_follow_up_overview_dto(overview))

    assert payload["total_open"] == 2
    assert payload["due_today"] == 1
    assert payload["overdue"] == 1
    assert payload["high_priority"] == 1
    assert payload["items"][0]["id"] == "a"
    assert payload["items"][1]["last_contacted_at"] is None


def test_extract_telegram_command_parses_supported_message_shapes() -> None:
    assert _extract_telegram_command({}) is None
    assert _extract_telegram_command({"message": "bad"}) is None
    assert _extract_telegram_command({"message": {"text": 1, "chat": {}}}) is None
    assert _extract_telegram_command({"message": {"text": "hello", "chat": {"id": 123}}}) is None
    assert _extract_telegram_command({"message": {"text": "/prospect", "chat": "bad"}}) is None
    assert _extract_telegram_command({"message": {"text": "/prospect", "chat": {"id": None}}}) is None
    assert _extract_telegram_command({"message": {"text": "/prospect@mybot", "chat": {"id": 123}}}) == _TelegramCommand(
        chat_id="123",
        name="/prospect",
        argument=None,
        text="/prospect",
    )
    assert _extract_telegram_command({"message": {"text": "/code fix a bug with login", "chat": {"id": 123}}}) == _TelegramCommand(
        chat_id="123",
        name="/code",
        argument="fix a bug with login",
        text="/code fix a bug with login",
    )


def test_build_prospecting_status_message_reports_errors_and_modes(monkeypatch) -> None:
    monkeypatch.setattr("src.adapters.api.app.collect_prospecting_config_errors", lambda: ["Missing SMTP_HOST"])
    assert _build_prospecting_status_message() == "Prospecting agent is not ready:\n- Missing SMTP_HOST"

    monkeypatch.setattr("src.adapters.api.app.collect_prospecting_config_errors", lambda: [])
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert _build_prospecting_status_message() == "Prospecting agent is ready.\nOpenAI idea drafting disabled; template opportunity ideas will be used."

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert _build_prospecting_status_message() == "Prospecting agent is ready.\nOpenAI idea drafting enabled."


def test_build_etf_sentiment_status_message_reports_errors_and_modes(monkeypatch) -> None:
    monkeypatch.setattr("src.adapters.api.app.collect_etf_sentiment_config_errors", lambda: ["Missing prompt"])
    assert _build_etf_sentiment_status_message() == "ETF sentiment agent is not ready:\n- Missing prompt"

    monkeypatch.setattr("src.adapters.api.app.collect_etf_sentiment_config_errors", lambda: [])
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert _build_etf_sentiment_status_message() == (
        "ETF sentiment agent is ready.\nOpenAI analysis disabled; price-action template mode will be used."
    )

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert _build_etf_sentiment_status_message() == "ETF sentiment agent is ready.\nOpenAI analysis enabled."


def test_run_prospecting_from_telegram_sends_success_and_failure_updates(monkeypatch) -> None:
    sent: list[str] = []

    class FakeNotifier:
        def send_message(self, text: str) -> None:
            sent.append(text)

    monkeypatch.setattr(
        "src.adapters.api.app.run_prospecting_job",
        lambda: type("Digest", (), {"scanned_post_count": 7, "shortlisted_count": 2})(),
    )
    _run_prospecting_from_telegram(FakeNotifier())  # type: ignore[arg-type]
    assert sent[-1] == "Prospecting finished. Scanned 7 posts, shortlisted 2 opportunity signals, and sent the digest."

    monkeypatch.setattr("src.adapters.api.app.run_prospecting_job", lambda: (_ for _ in ()).throw(ValueError("broken")))
    _run_prospecting_from_telegram(FakeNotifier())  # type: ignore[arg-type]
    assert sent[-1] == "Prospecting run failed: broken"

    class FailingNotifier:
        calls = 0

        def send_message(self, text: str) -> None:
            self.calls += 1
            raise __import__("src.adapters.notifications.telegram_notifier", fromlist=["TelegramNotificationError"]).TelegramNotificationError(
                "down"
            )

    monkeypatch.setattr("src.adapters.api.app.run_prospecting_job", lambda: (_ for _ in ()).throw(ValueError("broken")))
    _run_prospecting_from_telegram(FailingNotifier())  # type: ignore[arg-type]


def test_run_etf_sentiment_from_telegram_sends_success_and_failure_updates(monkeypatch) -> None:
    sent: list[str] = []

    class FakeNotifier:
        def send_message(self, text: str) -> None:
            sent.append(text)

    monkeypatch.setattr("src.adapters.api.app.deliver_etf_sentiment_job", lambda: "ETF Sentiment Brief")
    _run_etf_sentiment_from_telegram(FakeNotifier())  # type: ignore[arg-type]
    assert sent == []

    monkeypatch.setattr("src.adapters.api.app.deliver_etf_sentiment_job", lambda: (_ for _ in ()).throw(ValueError("broken")))
    _run_etf_sentiment_from_telegram(FakeNotifier())  # type: ignore[arg-type]
    assert sent[-1] == "ETF sentiment run failed: broken"

    class FailingNotifier:
        calls = 0

        def send_message(self, text: str) -> None:
            self.calls += 1
            raise __import__("src.adapters.notifications.telegram_notifier", fromlist=["TelegramNotificationError"]).TelegramNotificationError(
                "down"
            )

    monkeypatch.setattr("src.adapters.api.app.deliver_etf_sentiment_job", lambda: (_ for _ in ()).throw(ValueError("broken")))
    _run_etf_sentiment_from_telegram(FailingNotifier())  # type: ignore[arg-type]


def test_run_code_from_telegram_sends_decision_and_failure_updates(monkeypatch, tmp_path) -> None:
    sent: list[str] = []

    class FakeNotifier:
        def send_message(self, text: str) -> None:
            sent.append(text)

    digest = object()
    brief = object()
    seen_guidance: list[str | None] = []
    monkeypatch.setattr("src.adapters.api.app.run_prospecting_job", lambda founder_guidance=None: seen_guidance.append(founder_guidance) or digest)
    monkeypatch.setattr(
        "src.adapters.api.app.decide_autonomous_build_brief",
        lambda payload, founder_guidance=None: brief if payload is digest and founder_guidance == "fix a bug with login" else None,
    )
    monkeypatch.setattr("src.adapters.api.app.append_autonomous_build_brief", lambda payload: tmp_path / "queue.jsonl")
    monkeypatch.setattr("src.adapters.api.app.format_autonomous_build_brief", lambda payload: "Code cooperation result\nDecision: build now")

    _run_code_from_telegram(FakeNotifier(), "fix a bug with login")  # type: ignore[arg-type]
    assert "Decision: build now" in sent[-1]
    assert "Queue file:" in sent[-1]
    assert seen_guidance == ["fix a bug with login"]

    monkeypatch.setattr("src.adapters.api.app.run_prospecting_job", lambda founder_guidance=None: (_ for _ in ()).throw(ValueError("broken")))
    _run_code_from_telegram(FakeNotifier())  # type: ignore[arg-type]
    assert sent[-1] == "Cooperative code run failed: broken"

    class FailingNotifier:
        def send_message(self, text: str) -> None:
            raise __import__("src.adapters.notifications.telegram_notifier", fromlist=["TelegramNotificationError"]).TelegramNotificationError(
                "down"
            )

    monkeypatch.setattr("src.adapters.api.app.run_prospecting_job", lambda founder_guidance=None: (_ for _ in ()).throw(ValueError("broken")))
    _run_code_from_telegram(FailingNotifier())  # type: ignore[arg-type]


def test_telegram_webhook_handles_commands_and_guards(monkeypatch) -> None:
    client = make_client(user=make_user())
    sent: list[str] = []
    tasks: list[str] = []

    class FakeNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            self.bot_token = bot_token
            self.chat_id = chat_id

        def send_message(self, text: str) -> None:
            sent.append(text)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setattr("src.adapters.api.app.TelegramNotifier", FakeNotifier)
    monkeypatch.setattr("src.adapters.api.app._run_prospecting_from_telegram", lambda notifier: tasks.append("ran"))
    monkeypatch.setattr("src.adapters.api.app._run_etf_sentiment_from_telegram", lambda notifier: tasks.append("sentiment"))
    monkeypatch.setattr("src.adapters.api.app._run_code_from_telegram", lambda notifier, founder_guidance=None: tasks.append("code"))
    queued_commands: list[str] = []
    monkeypatch.setattr("src.adapters.api.app._queue_founder_code_request", lambda command: queued_commands.append(command.text))
    monkeypatch.setattr("src.adapters.api.app.collect_prospecting_config_errors", lambda: [])
    monkeypatch.setattr("src.adapters.api.app.collect_etf_sentiment_config_errors", lambda: [])
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post("/api/telegram/webhook", headers={"X-Telegram-Bot-Api-Secret-Token": "secret"}, json={})
    assert response.json() == {"ok": True, "handled": False}

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        json={"message": {"text": "/prospect", "chat": {"id": 123}}},
    )
    assert response.status_code == 401

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"text": "/prospect", "chat": {"id": 999}}},
    )
    assert response.json() == {"ok": True, "handled": False}

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"text": "/prospect", "chat": {"id": 123}}},
    )
    assert response.json() == {"ok": True, "handled": True, "command": "/prospect"}
    assert sent[-1] == "Starting the daily prospecting run now. I will send a follow-up when it finishes."
    assert tasks == ["ran"]

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"text": "/prospect status", "chat": {"id": 123}}},
    )
    assert response.json() == {"ok": True, "handled": True, "command": "/prospect status"}
    assert sent[-1] == "Prospecting agent is ready.\nOpenAI idea drafting disabled; template opportunity ideas will be used."

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"text": "/sentiment", "chat": {"id": 123}}},
    )
    assert response.json() == {"ok": True, "handled": True, "command": "/sentiment"}
    assert sent[-1] == "Starting the ETF sentiment run now. I will send a follow-up when it finishes."
    assert tasks == ["ran", "sentiment"]

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"text": "/sentiment status", "chat": {"id": 123}}},
    )
    assert response.json() == {"ok": True, "handled": True, "command": "/sentiment status"}
    assert sent[-1] == "ETF sentiment agent is ready.\nOpenAI analysis disabled; price-action template mode will be used."

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"text": "/code", "chat": {"id": 123}}},
    )
    assert response.json() == {"ok": True, "handled": True, "command": "/code"}
    assert sent[-1] == "Starting a cooperative code run now. I will send a build recommendation when it finishes."
    assert tasks == ["ran", "sentiment", "code"]
    assert queued_commands[-1] == "/code"

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"text": "/code fix a bug with login", "chat": {"id": 123}}},
    )
    assert response.json() == {"ok": True, "handled": True, "command": "/code"}
    assert sent[-1] == (
        "Starting a cooperative code run now. I will send a build recommendation when it finishes."
        " Founder guidance received: fix a bug with login."
    )
    assert tasks == ["ran", "sentiment", "code", "code"]
    assert queued_commands[-1] == "/code fix a bug with login"

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"text": "/help", "chat": {"id": 123}}},
    )
    assert response.json() == {"ok": True, "handled": True, "command": "/help"}
    assert "Supported commands:" in sent[-1]
    assert "/code - run the prospect agent and queue a build recommendation" in sent[-1]
    assert "/code <guidance> - treat the text as founder direction unless it would harm the product goal" in sent[-1]

    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"text": "/unknown", "chat": {"id": 123}}},
    )
    assert response.json() == {"ok": True, "handled": False}


def test_telegram_webhook_requires_configuration(monkeypatch) -> None:
    client = make_client(user=make_user())
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    response = client.post("/api/telegram/webhook", json={"message": {"text": "/prospect", "chat": {"id": 123}}})
    assert response.status_code == 503

    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    response = client.post("/api/telegram/webhook", json={"message": {"text": "/prospect", "chat": {"id": 123}}})
    assert response.status_code == 503


def test_telegram_webhook_status_can_report_errors(monkeypatch) -> None:
    client = make_client(user=make_user())
    sent: list[str] = []

    class FakeNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            self.bot_token = bot_token
            self.chat_id = chat_id

        def send_message(self, text: str) -> None:
            sent.append(text)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr("src.adapters.api.app.TelegramNotifier", FakeNotifier)
    monkeypatch.setattr("src.adapters.api.app.collect_prospecting_config_errors", lambda: ["Missing SMTP_HOST"])

    response = client.post("/api/telegram/webhook", json={"message": {"text": "/prospect status", "chat": {"id": 123}}})

    assert response.json() == {"ok": True, "handled": True, "command": "/prospect status"}
    assert sent[-1] == "Prospecting agent is not ready:\n- Missing SMTP_HOST"

    monkeypatch.setattr("src.adapters.api.app.collect_etf_sentiment_config_errors", lambda: ["Missing prompt"])
    response = client.post("/api/telegram/webhook", json={"message": {"text": "/sentiment status", "chat": {"id": 123}}})

    assert response.json() == {"ok": True, "handled": True, "command": "/sentiment status"}
    assert sent[-1] == "ETF sentiment agent is not ready:\n- Missing prompt"


def test_operator_briefing_webhook_requires_valid_secret(monkeypatch) -> None:
    client = make_client(user=make_user())
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "internal-secret")

    unauthorized = client.post("/api/internal/operator-briefing", headers={"X-Internal-Cron-Secret": "wrong"})
    assert unauthorized.status_code == 401

    monkeypatch.setattr("src.adapters.api.app.collect_operator_briefing_config_errors", lambda: [])

    class Briefing:
        prospect_run_count = 3
        total_shortlisted_ideas = 7
        product_updates = ("a", "b")

    monkeypatch.setattr("src.adapters.api.app.run_daily_operator_briefing_job", lambda: Briefing())

    response = client.post("/api/internal/operator-briefing", headers={"X-Internal-Cron-Secret": "internal-secret"})
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "prospect_run_count": 3,
        "shortlisted_ideas": 7,
        "product_updates": 2,
    }


def test_founder_code_requests_webhook_lists_requests(monkeypatch) -> None:
    client = make_client(user=make_user())
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "internal-secret")

    request = FounderCodeRequest(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        created_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
        source_chat_id="123",
        command_text="/code fix login",
        guidance="fix login",
    )

    class FakeRepository:
        pass

    monkeypatch.setattr("src.adapters.api.app.build_founder_code_request_repository", lambda: FakeRepository())
    monkeypatch.setattr(
        "src.adapters.api.app.ListFounderCodeRequestsUseCase.execute",
        lambda self, since=None, limit=50: [request],
    )

    response = client.get(
        "/api/internal/founder-code-requests",
        headers={"X-Internal-Cron-Secret": "internal-secret"},
        params={"since": "2026-05-16T11:00:00+00:00", "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["requests"][0]["command_text"] == "/code fix login"


def test_queue_founder_code_request_tolerates_runtime_error(monkeypatch) -> None:
    command = _TelegramCommand(chat_id="123", name="/code", argument="fix login", text="/code fix login")
    monkeypatch.setattr(
        "src.adapters.api.app.build_founder_code_request_repository",
        lambda: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    __import__("src.adapters.api.app", fromlist=["_queue_founder_code_request"])._queue_founder_code_request(command)


def test_operator_briefing_webhook_reports_configuration_errors(monkeypatch) -> None:
    client = make_client(user=make_user())
    monkeypatch.delenv("INTERNAL_CRON_SECRET", raising=False)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "fallback-secret")
    monkeypatch.setattr("src.adapters.api.app.collect_operator_briefing_config_errors", lambda: ["Missing SMTP_HOST"])

    response = client.post("/api/internal/operator-briefing", headers={"X-Internal-Cron-Secret": "fallback-secret"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Missing SMTP_HOST"


def test_operator_briefing_webhook_requires_configured_secret(monkeypatch) -> None:
    client = make_client(user=make_user())
    monkeypatch.delenv("INTERNAL_CRON_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    response = client.post("/api/internal/operator-briefing")

    assert response.status_code == 503
    assert response.json()["detail"] == "Internal cron secret is not configured."


def test_billing_routes_round_trip_overview_checkout_and_portal_urls() -> None:
    seen_return_urls: list[str | None] = []
    billing_port = FakeBillingPort(seen_return_urls=seen_return_urls)
    client = make_client(user=make_user(), billing_port=billing_port)

    overview_response = client.get("/api/account/billing", headers={"Authorization": "Bearer session-token"})
    checkout_response = client.post(
        "/api/account/billing/checkout",
        headers={"Authorization": "Bearer session-token"},
        json={"return_url": "https://www.brivoly.com/account"},
    )
    portal_response = client.post(
        "/api/account/billing/portal",
        headers={"Authorization": "Bearer session-token"},
        json={"return_url": "https://www.brivoly.com/account"},
    )

    assert overview_response.status_code == 200
    assert overview_response.json()["subscription_status"] == "active"
    assert checkout_response.json() == {"url": "https://checkout.stripe.test/session_123"}
    assert portal_response.json() == {"url": "https://billing.stripe.test/session_123"}
    assert seen_return_urls == ["https://www.brivoly.com/account", "https://www.brivoly.com/account"]


def test_billing_routes_require_auth_and_configuration() -> None:
    anonymous_client = make_client(user=make_user())
    unauthenticated_response = anonymous_client.get("/api/account/billing")
    unavailable_checkout = anonymous_client.post(
        "/api/account/billing/checkout",
        headers={"Authorization": "Bearer session-token"},
        json={"return_url": "https://www.brivoly.com/account"},
    )
    unavailable_portal = anonymous_client.post(
        "/api/account/billing/portal",
        headers={"Authorization": "Bearer session-token"},
        json={"return_url": "https://www.brivoly.com/account"},
    )

    assert unauthenticated_response.status_code == 401
    assert unavailable_checkout.status_code == 503
    assert unavailable_checkout.json()["detail"] == "Stripe billing is not configured."
    assert unavailable_portal.status_code == 503
    assert unavailable_checkout.json()["detail"] == "Stripe billing is not configured."


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


def test_healthcheck_and_readiness_include_request_ids(monkeypatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://trade.example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/trade")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_value")
    client = make_client(user=make_user())

    response = client.get("/healthz", headers={"X-Request-ID": "req-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"

    generated = client.get("/healthz")
    assert generated.status_code == 200
    assert generated.headers["X-Request-ID"]

    readiness = client.get("/readyz")
    assert readiness.status_code == 200
    assert readiness.headers["X-Request-ID"]
    assert readiness.json()["status"] == "ok"
    assert readiness.json()["checks"]["auth"]["configured"] is True


def test_readiness_reports_degraded_runtime_without_auth_config(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "")
    client = make_client(user=make_user())

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["auth"]["configured"] is False


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


def test_crm_followups_endpoint_requires_auth_and_returns_queue() -> None:
    client = make_client(user=make_user())

    unauthorized = client.get("/api/crm/followups")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["detail"] == "Authentication required."

    response = client.get("/api/crm/followups", headers={"Authorization": "Bearer session-token"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_open"] == 4
    assert payload["high_priority"] == 2
    assert payload["items"][0]["lead_name"] == "Amber Flores"
    assert payload["items"][0]["stage"] == "Discovery"
    assert payload["items"][0]["timeline"]


def test_crm_followups_endpoint_supports_complete_snooze_and_notes() -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    client = make_client(user=make_user(), lead_follow_up_repository=repository)

    complete = client.patch(
        "/api/crm/followups/lead-amber-studio",
        headers={"Authorization": "Bearer session-token"},
        json={"action": "complete"},
    )
    assert complete.status_code == 200
    assert complete.json()["total_open"] == 3
    assert all(item["id"] != "lead-amber-studio" for item in complete.json()["items"])

    snooze = client.patch(
        "/api/crm/followups/lead-riverbridge",
        headers={"Authorization": "Bearer session-token"},
        json={"action": "snooze", "snooze_hours": 24},
    )
    assert snooze.status_code == 200
    riverbridge = next(item for item in snooze.json()["items"] if item["id"] == "lead-riverbridge")
    assert riverbridge["next_follow_up_at"] == "2024-05-07T12:30:00+00:00"

    missing = client.patch(
        "/api/crm/followups/missing-id",
        headers={"Authorization": "Bearer session-token"},
        json={"action": "complete"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "CRM follow-up not found."

    invalid = client.patch(
        "/api/crm/followups/lead-riverbridge",
        headers={"Authorization": "Bearer session-token"},
        json={"action": "snooze"},
    )
    assert invalid.status_code == 422

    note = client.patch(
        "/api/crm/followups/lead-riverbridge",
        headers={"Authorization": "Bearer session-token"},
        json={"action": "note", "note_body": "Needs tighter rollout framing before sign-off."},
    )
    assert note.status_code == 200
    riverbridge = next(item for item in note.json()["items"] if item["id"] == "lead-riverbridge")
    assert riverbridge["notes"] == "Needs tighter rollout framing before sign-off."
    assert riverbridge["timeline"][0]["kind"] == "internal_note"
    assert riverbridge["timeline"][0]["summary"] == "Needs tighter rollout framing before sign-off."

    invalid_note = client.patch(
        "/api/crm/followups/lead-riverbridge",
        headers={"Authorization": "Bearer session-token"},
        json={"action": "note"},
    )
    assert invalid_note.status_code == 422

    blank_note = client.patch(
        "/api/crm/followups/lead-riverbridge",
        headers={"Authorization": "Bearer session-token"},
        json={"action": "note", "note_body": "   "},
    )
    assert blank_note.status_code == 422
    assert blank_note.json()["detail"] == "Note body is required."

    bad_action = client.patch(
        "/api/crm/followups/lead-riverbridge",
        headers={"Authorization": "Bearer session-token"},
        json={"action": "archive"},
    )
    assert bad_action.status_code == 422


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
                lead_follow_up_repository_factory=lambda: InMemoryLeadFollowUpRepository(
                    now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
                ),
                billing_port_factory=lambda: None,
                now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC),
            )
        )
        return TestClient(app)

    response = raising_client().get("/api/dashboard", headers={"Authorization": "Bearer session-token"})

    assert response.status_code == 422
    assert "Could not load market data" in response.json()["detail"]


def test_disabled_billing_port_raises_for_redirect_flows() -> None:
    port = _DisabledBillingPort()

    with pytest.raises(RuntimeError, match="not configured"):
        port.create_checkout_session(make_user())

    with pytest.raises(RuntimeError, match="not configured"):
        port.create_portal_session(make_user())
