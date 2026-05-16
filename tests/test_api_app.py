from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from base64 import b64encode
from io import BytesIO
import os
from uuid import UUID

import pandas as pd
from fastapi.testclient import TestClient
import pytest

from src.adapters.api.app import (
    ApiDependencies,
    _DisabledBillingPort,
    _TelegramCommand,
    _build_crm_intake_token,
    _build_etf_sentiment_status_message,
    _build_prospecting_status_message,
    _extract_telegram_command,
    _extract_telegram_image_intake,
    _normalize_universe,
    _run_code_from_telegram,
    _run_etf_sentiment_from_telegram,
    _run_prospecting_from_telegram,
    create_app,
)
import src.adapters.api.app as api_app_module
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


@dataclass
class FakeUserRepository:
    user: User | None = None

    def get_user_by_id(self, user_id: UUID) -> User | None:
        if self.user and self.user.id == user_id:
            return self.user
        return None


def make_client(
    *,
    user: User | None = None,
    auth_error: Exception | None = None,
    dashboard_result: DashboardResult | None = None,
    seen_tokens: list[str] | None = None,
    personalization_repository: InMemoryPersonalizationRepository | None = None,
    lead_follow_up_repository: InMemoryLeadFollowUpRepository | None = None,
    billing_port: FakeBillingPort | None = None,
    user_repository: FakeUserRepository | None = None,
) -> TestClient:
    result = dashboard_result or make_dashboard_result()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    auth_use_case = FakeAuthUseCase(user=user, error=auth_error, seen_tokens=seen_tokens)
    repository = personalization_repository or InMemoryPersonalizationRepository()
    crm_repository = lead_follow_up_repository or InMemoryLeadFollowUpRepository(now=lambda: now)
    user_repo = user_repository or FakeUserRepository(user=user)
    app = create_app(
        ApiDependencies(
            auth_use_case_factory=lambda: auth_use_case,
            market_data_factory=lambda: FakeMarketDataAdapter(result=result, captured_configs=[]),
            personalization_repository_factory=lambda: repository,
            lead_follow_up_repository_factory=lambda: crm_repository,
            billing_port_factory=lambda: billing_port,
            user_repository_factory=lambda: user_repo,
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
        crm_ai_prompt="Extract CRM fields from spreadsheets and screenshots.",
        crm_preferred_import_formats=["csv", "spreadsheet_screenshot"],
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
    assert settings_payload["crm_preferred_import_formats"] == ["csv", "spreadsheet_screenshot"]
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
            owner_name="Ada Lovelace",
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
            owner_name="Samir Patel",
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


def test_extract_telegram_image_intake_supports_photos_and_image_documents() -> None:
    assert _extract_telegram_image_intake({}) is None
    assert _extract_telegram_image_intake({"message": {"chat": {"id": 123}}}) is None
    assert _extract_telegram_image_intake({"message": {"caption": "/intake code", "chat": "bad"}}) is None
    assert _extract_telegram_image_intake({"message": {"caption": "hello", "chat": {"id": 123}}}) is None
    assert _extract_telegram_image_intake({"message": {"caption": "/intake", "chat": {"id": 123}}}) is None
    assert _extract_telegram_image_intake({"message": {"caption": "/intake code", "chat": {"id": 123}}}) is None

    photo_intake = _extract_telegram_image_intake(
        {
            "message": {
                "caption": "/intake abc123",
                "chat": {"id": 123},
                "photo": [{"file_id": "small"}, {"file_id": "large"}],
            }
        }
    )
    assert photo_intake is not None
    assert photo_intake.file_id == "large"
    assert photo_intake.file_name == "telegram-photo.jpg"

    document_intake = _extract_telegram_image_intake(
        {
            "message": {
                "caption": "/intake token",
                "chat": {"id": 123},
                "document": {"file_id": "doc-1", "file_name": "note.webp", "mime_type": "image/webp"},
            }
        }
    )
    assert document_intake is not None
    assert document_intake.file_id == "doc-1"


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


def test_telegram_webhook_handles_remote_crm_image_intake(monkeypatch) -> None:
    user = make_user()
    client = make_client(
        user=user,
        billing_port=FakeBillingPort(),
        personalization_repository=InMemoryPersonalizationRepository(),
        lead_follow_up_repository=InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC)),
    )
    sent: list[str] = []
    tasks: list[tuple[str, str, str]] = []

    class FakeNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            self.bot_token = bot_token
            self.chat_id = chat_id

        def send_message(self, text: str) -> None:
            sent.append(text)

    def fake_run(notifier, intake, deps) -> None:
        tasks.append((notifier.chat_id, intake.file_id, intake.file_name))

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("CRM_INTAKE_SECRET", "crm-secret")
    monkeypatch.setattr("src.adapters.api.app.TelegramNotifier", FakeNotifier)
    monkeypatch.setattr("src.adapters.api.app._run_telegram_crm_image_intake", fake_run)

    token = _build_crm_intake_token(user.id, "crm-secret")
    response = client.post(
        "/api/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={
            "message": {
                "caption": f"/intake {token}",
                "chat": {"id": 456},
                "photo": [{"file_id": "small"}, {"file_id": "large"}],
            }
        },
    )

    assert response.json() == {"ok": True, "handled": True, "command": "/intake"}
    assert sent[-1] == "Received your note image. Brivoly is importing it into your CRM now."
    assert tasks == [("456", "large", "telegram-photo.jpg")]


def test_crm_intake_channel_returns_caption_for_authenticated_user(monkeypatch) -> None:
    user = make_user()
    client = make_client(user=user)
    monkeypatch.setenv("CRM_INTAKE_SECRET", "crm-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")

    response = client.get("/api/crm/intake-channel", headers={"Authorization": "Bearer session-token"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["telegram_available"] is True
    assert payload["intake_channel"] == "telegram"
    assert payload["intake_caption"].startswith("/intake ")


def test_crm_intake_channel_reports_missing_configuration() -> None:
    client = make_client(user=make_user())
    for env_name in ("CRM_INTAKE_SECRET", "INTERNAL_CRON_SECRET", "TELEGRAM_WEBHOOK_SECRET", "TELEGRAM_BOT_TOKEN"):
        os.environ.pop(env_name, None)

    response = client.get("/api/crm/intake-channel", headers={"Authorization": "Bearer session-token"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["telegram_available"] is False
    assert payload["intake_caption"] is None


def test_run_telegram_crm_image_intake_imports_rows(monkeypatch) -> None:
    user = make_user()
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    personalization = InMemoryPersonalizationRepository()
    personalization.save_dashboard_settings(build_default_dashboard_settings(user.id, telegram_enabled=True))
    deps = ApiDependencies(
        auth_use_case_factory=lambda: FakeAuthUseCase(user=user),
        market_data_factory=lambda: FakeMarketDataAdapter(result=make_dashboard_result(), captured_configs=[]),
        personalization_repository_factory=lambda: personalization,
        lead_follow_up_repository_factory=lambda: repository,
        billing_port_factory=lambda: FakeBillingPort(),
        user_repository_factory=lambda: FakeUserRepository(user=user),
        now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC),
    )
    sent: list[str] = []

    class FakeNotifier:
        def send_message(self, text: str) -> None:
            sent.append(text)

    class FakeImageIntake:
        def extract_spreadsheet_rows_from_image(self, prompt, preferred_formats, file_name, file_bytes) -> str:
            assert file_name == "telegram-photo.jpg"
            assert file_bytes == b"image-bytes"
            return (
                "lead_name,company_name,owner_name,stage,next_follow_up_at,notes,priority,contact_channel,next_step\n"
                "Taylor Brooks,Beacon Ridge,Samir Patel,Discovery,2024-05-09,Imported from Telegram image,high,image,Follow up\n"
            )

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def read(self) -> bytes:
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request_obj):
        if "getFile" in request_obj.full_url:
            return FakeResponse(b'{"ok": true, "result": {"file_path": "photos/file_1.jpg"}}')
        return FakeResponse(b"image-bytes")

    monkeypatch.setenv("CRM_INTAKE_SECRET", "crm-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setattr("src.adapters.api.app.build_crm_image_intake_agent_from_env", lambda: FakeImageIntake())
    monkeypatch.setattr("src.adapters.api.app.request.urlopen", fake_urlopen)

    api_app_module._run_telegram_crm_image_intake(  # type: ignore[attr-defined]
        FakeNotifier(),  # type: ignore[arg-type]
        api_app_module._TelegramImageIntake(  # type: ignore[attr-defined]
            chat_id="123",
            command_name="/intake",
            intake_token=_build_crm_intake_token(user.id, "crm-secret"),
            file_id="telegram-file",
            file_name="telegram-photo.jpg",
        ),
        deps,
    )

    assert "Imported: 1" in sent[-1]
    overview = GetLeadFollowUpOverviewUseCase(repository=repository, now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC)).execute(user)
    assert any(item.notes == "Imported from Telegram image" for item in overview.items)


def test_run_telegram_crm_image_intake_reports_failure_branches(monkeypatch) -> None:
    user = make_user()
    deps = ApiDependencies(
        auth_use_case_factory=lambda: FakeAuthUseCase(user=user),
        market_data_factory=lambda: FakeMarketDataAdapter(result=make_dashboard_result(), captured_configs=[]),
        personalization_repository_factory=lambda: InMemoryPersonalizationRepository(),
        lead_follow_up_repository_factory=lambda: InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC)),
        billing_port_factory=lambda: FakeBillingPort(overview=BillingOverview(enabled=False, customer_id=None, subscription_id=None, subscription_status=None, price_id=None, cancel_at_period_end=False, current_period_end=None, checkout_available=False, portal_available=False)),
        user_repository_factory=lambda: FakeUserRepository(user=user),
        now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC),
    )
    sent: list[str] = []

    class FakeNotifier:
        def send_message(self, text: str) -> None:
            sent.append(text)

    monkeypatch.delenv("CRM_INTAKE_SECRET", raising=False)
    monkeypatch.delenv("INTERNAL_CRON_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    api_app_module._run_telegram_crm_image_intake(  # type: ignore[attr-defined]
        FakeNotifier(),  # type: ignore[arg-type]
        api_app_module._TelegramImageIntake(  # type: ignore[attr-defined]
            chat_id="123",
            command_name="/intake",
            intake_token="bad",
            file_id="telegram-file",
            file_name="telegram-photo.jpg",
        ),
        deps,
    )
    assert sent[-1] == "CRM note import failed: Remote CRM note capture is not configured yet."

    monkeypatch.setenv("CRM_INTAKE_SECRET", "crm-secret")
    api_app_module._run_telegram_crm_image_intake(  # type: ignore[attr-defined]
        FakeNotifier(),  # type: ignore[arg-type]
        api_app_module._TelegramImageIntake(  # type: ignore[attr-defined]
            chat_id="123",
            command_name="/intake",
            intake_token=_build_crm_intake_token(UUID("22222222-2222-2222-2222-222222222222"), "crm-secret"),
            file_id="telegram-file",
            file_name="telegram-photo.jpg",
        ),
        deps,
    )
    assert "active Brivoly account" in sent[-1]

    deps_without_repo = ApiDependencies(
        auth_use_case_factory=deps.auth_use_case_factory,
        market_data_factory=deps.market_data_factory,
        personalization_repository_factory=deps.personalization_repository_factory,
        lead_follow_up_repository_factory=deps.lead_follow_up_repository_factory,
        billing_port_factory=deps.billing_port_factory,
        user_repository_factory=lambda: None,
        now=deps.now,
    )
    api_app_module._run_telegram_crm_image_intake(  # type: ignore[attr-defined]
        FakeNotifier(),  # type: ignore[arg-type]
        api_app_module._TelegramImageIntake(  # type: ignore[attr-defined]
            chat_id="123",
            command_name="/intake",
            intake_token=_build_crm_intake_token(user.id, "crm-secret"),
            file_id="telegram-file",
            file_name="telegram-photo.jpg",
        ),
        deps_without_repo,
    )
    assert "app database" in sent[-1]

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    api_app_module._run_telegram_crm_image_intake(  # type: ignore[attr-defined]
        FakeNotifier(),  # type: ignore[arg-type]
        api_app_module._TelegramImageIntake(  # type: ignore[attr-defined]
            chat_id="123",
            command_name="/intake",
            intake_token=_build_crm_intake_token(user.id, "crm-secret"),
            file_id="telegram-file",
            file_name="telegram-photo.jpg",
        ),
        deps,
    )
    assert "Telegram bot token is not configured" in sent[-1]

    class FailingNotifier:
        def send_message(self, text: str) -> None:
            raise __import__("src.adapters.notifications.telegram_notifier", fromlist=["TelegramNotificationError"]).TelegramNotificationError("down")

    monkeypatch.delenv("CRM_INTAKE_SECRET", raising=False)
    api_app_module._run_telegram_crm_image_intake(  # type: ignore[attr-defined]
        FailingNotifier(),  # type: ignore[arg-type]
        api_app_module._TelegramImageIntake(  # type: ignore[attr-defined]
            chat_id="123",
            command_name="/intake",
            intake_token="bad",
            file_id="telegram-file",
            file_name="telegram-photo.jpg",
        ),
        deps,
    )


def test_parse_crm_intake_token_and_download_telegram_file_validate_shapes(monkeypatch) -> None:
    with pytest.raises(ValueError, match="invalid"):
        api_app_module._parse_crm_intake_token("not-base64", "secret")  # type: ignore[attr-defined]

    bad_payload = b64encode(b'["bad"]').decode("ascii").rstrip("=")
    with pytest.raises(ValueError, match="invalid"):
        api_app_module._parse_crm_intake_token(bad_payload, "secret")  # type: ignore[attr-defined]

    missing_fields = b64encode(b'{"user_id": 1}').decode("ascii").rstrip("=")
    with pytest.raises(ValueError, match="invalid"):
        api_app_module._parse_crm_intake_token(missing_fields, "secret")  # type: ignore[attr-defined]

    wrong_signature = b64encode(b'{"user_id":"11111111-1111-1111-1111-111111111111","signature":"wrong"}').decode("ascii").rstrip("=")
    with pytest.raises(ValueError, match="invalid"):
        api_app_module._parse_crm_intake_token(wrong_signature, "secret")  # type: ignore[attr-defined]

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def read(self) -> bytes:
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("src.adapters.api.app.request.urlopen", lambda req: FakeResponse(b'{"ok": false}'))
    with pytest.raises(ValueError, match="Unable to download"):
        api_app_module._download_telegram_file("bot", "file-1")  # type: ignore[attr-defined]

    monkeypatch.setattr("src.adapters.api.app.request.urlopen", lambda req: FakeResponse(b'{"ok": true, "result": {}}'))
    with pytest.raises(ValueError, match="Unable to download"):
        api_app_module._download_telegram_file("bot", "file-1")  # type: ignore[attr-defined]


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
        crm_ai_prompt="default prompt",
        crm_preferred_import_formats=["csv"],
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
            crm_ai_prompt="Keep owner and next follow-up visible.",
            crm_preferred_import_formats=["pdf_export", "csv"],
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
    assert "follow-up-critical CRM fields" in defaults.crm_ai_prompt

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
            crm_ai_prompt="  Keep OCR evidence when uncertain.  ",
            crm_preferred_import_formats=[" CSV ", "csv", "Spreadsheet Screenshot"],
        )
    )
    assert normalized.universe == ["SPY", "QQQ"]
    assert normalized.benchmark == "SPY"
    assert normalized.vix_symbol == "^VIX"
    assert normalized.crm_ai_prompt == "Keep OCR evidence when uncertain."
    assert normalized.crm_preferred_import_formats == ["csv", "spreadsheet_screenshot"]

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
            "crm_ai_prompt": "Prefer extracting next step and owner from screenshots.",
            "crm_preferred_import_formats": ["spreadsheet_screenshot", "pdf_export"],
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["benchmark"] == "QQQ"
    assert update_response.json()["universe"] == ["SPY", "QQQ"]
    assert update_response.json()["telegram_enabled"] is True
    assert update_response.json()["crm_preferred_import_formats"] == ["spreadsheet_screenshot", "pdf_export"]

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


def test_crm_import_preview_and_commit_endpoints_support_csv_and_google_sheets(monkeypatch) -> None:
    repository = InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC))
    client = make_client(user=make_user(), lead_follow_up_repository=repository)

    preview = client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "csv",
            "csv_content": "Contact,Company,Owner,Status,Next Follow-Up,Notes\nTaylor Brooks,Beacon Ridge,Samir Patel,Qualification,2024-05-09,Imported from sheet\nAmber Flores,Northstar Studio,Ada Lovelace,Discovery,2024-05-10,Duplicate row\n",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["importable_rows"] == 1
    assert preview.json()["duplicate_rows"] == 1
    assert preview.json()["rows"][0]["owner_name"] == "Samir Patel"

    commit = client.post(
        "/api/crm/import",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "csv",
            "csv_content": "Contact,Company,Owner,Status,Next Follow-Up,Notes\nTaylor Brooks,Beacon Ridge,Samir Patel,Qualification,2024-05-09,Imported from sheet\n",
        },
    )
    assert commit.status_code == 200
    assert commit.json()["imported_count"] == 1
    imported = next(item for item in commit.json()["overview"]["items"] if item["company_name"] == "Beacon Ridge")
    assert imported["owner_name"] == "Samir Patel"
    assert imported["timeline"][0]["kind"] == "import"

    monkeypatch.setattr(
        api_app_module,
        "fetch_google_sheets_csv",
        lambda sheet_url: "contact,company,owner,status,next follow-up,notes\nMorgan Lee,Stone Harbor,Riley Chen,Proposal,2024-05-10,From Google Sheet\n",
    )
    google_preview = client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "google_sheets",
            "sheet_url": "https://docs.google.com/spreadsheets/d/test-sheet/edit#gid=0",
        },
    )
    assert google_preview.status_code == 200
    assert google_preview.json()["source_label"] == "Google Sheets"
    assert google_preview.json()["rows"][0]["lead_name"] == "Morgan Lee"
    assert google_preview.json()["header_mappings"][0]["mapped_field"] == "lead_name"

    mapped_preview = client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "csv",
            "csv_content": "Person,Organisation,Followup,Context\nTaylor Brooks,Summit Forge,2024-05-09,Imported from a messy client sheet\n",
            "field_mapping": {
                "Person": "lead_name",
                "Organisation": "company_name",
                "Followup": "next_follow_up_at",
                "Context": "notes",
            },
        },
    )
    assert mapped_preview.status_code == 200
    assert mapped_preview.json()["importable_rows"] == 1
    assert mapped_preview.json()["header_mappings"][0]["mapped_field"] == "lead_name"

    excel_buffer = BytesIO()
    pd.DataFrame(
        [
            {
                "Contact": "Nina Patel",
                "Company": "Summit Harbor",
                "Owner": "Riley Chen",
                "Next Follow-Up": "2024-05-11",
                "Notes": "Imported from Excel",
            }
        ]
    ).to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_preview = client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "excel",
            "file_name": "leads.xlsx",
            "file_content_base64": b64encode(excel_buffer.getvalue()).decode("ascii"),
        },
    )
    assert excel_preview.status_code == 200
    assert excel_preview.json()["rows"][0]["lead_name"] == "Nina Patel"

    excel_commit = client.post(
        "/api/crm/import",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "excel",
            "file_name": "leads.xlsx",
            "file_content_base64": b64encode(excel_buffer.getvalue()).decode("ascii"),
        },
    )
    assert excel_commit.status_code == 200
    assert excel_commit.json()["imported_count"] == 1

    class FakeImageIntake:
        def extract_spreadsheet_rows_from_image(self, prompt: str, preferred_formats: list[str], file_name: str, file_bytes: bytes) -> str:
            assert "follow-up-critical CRM fields" in prompt
            assert file_name == "note.png"
            assert file_bytes == b"note-image"
            return (
                "lead_name,company_name,owner_name,stage,next_follow_up_at,notes,priority,contact_channel,next_step\n"
                "Taylor Brooks,Beacon Ridge,Samir Patel,Discovery,2024-05-09,Imported from note image,high,image,Follow up\n"
            )

    monkeypatch.setattr(api_app_module, "build_crm_image_intake_agent_from_env", lambda: FakeImageIntake())
    image_preview = client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "image",
            "file_name": "note.png",
            "file_content_base64": b64encode(b"note-image").decode("ascii"),
        },
    )
    assert image_preview.status_code == 200
    assert image_preview.json()["source_type"] == "image"
    assert image_preview.json()["rows"][0]["notes"] == "Imported from note image"


def test_crm_import_endpoints_return_validation_errors_for_bad_sources(monkeypatch) -> None:
    client = make_client(user=make_user(), lead_follow_up_repository=InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC)))

    preview = client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={"source_type": "csv"},
    )
    assert preview.status_code == 422
    assert preview.json()["detail"] == "CSV content is required for spreadsheet import."

    commit = client.post(
        "/api/crm/import",
        headers={"Authorization": "Bearer session-token"},
        json={"source_type": "google_sheets"},
    )
    assert commit.status_code == 422
    assert commit.json()["detail"] == "A Google Sheets URL is required."

    bad_mapping = client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "csv",
            "csv_content": "Person,Due\nTaylor Brooks,2024-05-09\n",
            "field_mapping": {"Person": "unsupported_field"},
        },
    )
    assert bad_mapping.status_code == 422
    assert "Unsupported field mapping" in bad_mapping.json()["detail"]

    missing_excel_name = client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={"source_type": "excel", "file_content_base64": "aGVsbG8="},
    )
    assert missing_excel_name.status_code == 422
    assert missing_excel_name.json()["detail"] == "Spreadsheet file name is required."

    free_plan_client = make_client(
        user=make_user(),
        lead_follow_up_repository=InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC)),
        billing_port=FakeBillingPort(
            overview=BillingOverview(
                enabled=True,
                customer_id="cus_123",
                subscription_id=None,
                subscription_status=None,
                price_id="price_123",
                cancel_at_period_end=False,
                current_period_end=None,
                checkout_available=True,
                portal_available=True,
            )
        ),
    )
    image_on_free_plan = free_plan_client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "image",
            "file_name": "note.png",
            "file_content_base64": b64encode(b"note-image").decode("ascii"),
        },
    )
    assert image_on_free_plan.status_code == 422
    assert image_on_free_plan.json()["detail"] == "AI note image intake is available on active or trialing paid plans."

    paid_client = make_client(
        user=make_user(),
        lead_follow_up_repository=InMemoryLeadFollowUpRepository(now=lambda: datetime(2024, 5, 6, 12, 30, tzinfo=UTC)),
        billing_port=FakeBillingPort(),
    )
    monkeypatch.setattr(
        api_app_module,
        "build_crm_image_intake_agent_from_env",
        lambda: (_ for _ in ()).throw(ValueError("AI note image intake is unavailable because no app OpenAI key is configured.")),
    )
    no_ai_key = paid_client.post(
        "/api/crm/import/preview",
        headers={"Authorization": "Bearer session-token"},
        json={
            "source_type": "image",
            "file_name": "note.png",
            "file_content_base64": b64encode(b"note-image").decode("ascii"),
        },
    )
    assert no_ai_key.status_code == 422
    assert "no app OpenAI key is configured" in no_ai_key.json()["detail"]


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
            "crm_ai_prompt": "",
            "crm_preferred_import_formats": [],
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
                user_repository_factory=lambda: FakeUserRepository(user=make_user()),
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
