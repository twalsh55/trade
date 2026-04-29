from __future__ import annotations

from datetime import UTC, date, datetime, timezone
import logging
from uuid import UUID

import numpy as np
import pandas as pd

from src.adapters.ui import streamlit_dashboard as dashboard
from src.domain.auth import User
from src.domain.models import DashboardResult


class FakeAdapter:
    pass


class FakeSidebar:
    def __enter__(self) -> "FakeSidebar":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False


class FakeColumn:
    def __init__(self) -> None:
        self.metrics: list[tuple[str, str]] = []

    def __enter__(self) -> "FakeColumn":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    def metric(self, label: str, value: str) -> None:
        self.metrics.append((label, value))


class FakeStreamlit:
    def __init__(self, text_values: list[str], slider_value: int, button_values: list[bool] | None = None) -> None:
        self.sidebar = FakeSidebar()
        self._text_values = iter(text_values)
        self._slider_value = slider_value
        self._button_values = iter(button_values or [])
        self.session_state: dict[str, str] = {}
        self.query_params: dict[str, str] = {}
        self.secrets: dict[str, str] = {}
        self.columns_created: list[list[FakeColumn]] = []
        self.errors: list[str] = []
        self.markdowns: list[str] = []
        self.captions: list[str] = []
        self.subheaders: list[str] = []
        self.writes: list[str] = []
        self.dataframes: list[pd.DataFrame] = []
        self.plot_calls = 0
        self.warnings: list[str] = []

    def set_page_config(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.page_config = kwargs

    def title(self, value: str) -> None:
        self.title_value = value

    def caption(self, value: str) -> None:
        self.caption_value = value
        self.captions.append(value)

    def header(self, value: str) -> None:
        self.header_value = value

    def text_input(self, label: str, default: str) -> str:
        return next(self._text_values)

    def slider(self, label: str, min_value: int, max_value: int, value: int) -> int:
        return self._slider_value

    def button(self, label: str) -> bool:
        return next(self._button_values, False)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def markdown(self, message: str) -> None:
        self.markdowns.append(message)

    def subheader(self, value: str) -> None:
        self.subheaders.append(value)

    def write(self, value: str) -> None:
        self.writes.append(value)

    def columns(self, spec):  # type: ignore[no-untyped-def]
        count = spec if isinstance(spec, int) else len(spec)
        created = [FakeColumn() for _ in range(count)]
        self.columns_created.append(created)
        return created

    def plotly_chart(self, figure, width: str) -> None:  # type: ignore[no-untyped-def]
        self.plot_calls += 1
        self.last_figure = figure
        self.last_width = width

    def dataframe(self, frame: pd.DataFrame, hide_index: bool, width: str) -> None:
        self.dataframes.append(frame.copy())


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


def stub_authenticated_user(monkeypatch, user: User | None = None) -> User:
    current_user = user or make_user()
    monkeypatch.setattr(dashboard, "get_current_user", lambda: current_user)
    monkeypatch.setattr(dashboard, "render_account_widget", lambda: None)
    return current_user


def make_result(include_yield_spread: bool, empty_indicator_table: bool) -> DashboardResult:
    dates = pd.bdate_range("2024-01-01", periods=260)
    close = pd.DataFrame({"SPY": np.linspace(100.0, 130.0, len(dates))}, index=dates)
    metrics = {
        "drawdown_252": -0.08,
        "vol20": 0.2,
        "breadth_ratio": 0.6,
    }
    if include_yield_spread:
        metrics["yield_curve_spread"] = -0.25

    indicator_percentiles = (
        pd.DataFrame()
        if empty_indicator_table
        else pd.DataFrame([{"Indicator": "Price", "Current": 130.12345, "P5": 100.0, "P50": 115.0, "P95": 129.0}])
    )
    return DashboardResult(
        close_data=close,
        metrics=metrics,
        indicator_percentiles=indicator_percentiles,
        risk_score=75.0 if include_yield_spread else 45.0,
        risk_components={"Trend stress": 12.0, "Breadth stress": 7.0},
        regime="Risk-Off (High Crash Risk)" if include_yield_spread else "Caution (Fragile Market Regime)",
        actions=["First action", "Second action"],
    )


def test_build_price_chart_builds_expected_traces() -> None:
    dates = pd.bdate_range("2022-01-01", periods=260)
    close = pd.DataFrame({"SPY": np.linspace(100.0, 150.0, len(dates))}, index=dates)

    figure = dashboard.build_price_chart(close, "SPY")

    assert len(figure.data) == 3
    assert figure.data[0].name == "SPY Price"
    assert figure.data[1].name == "50D MA"
    assert figure.data[2].name == "200D MA"


def test_build_buyer_participation_chart_builds_expected_traces() -> None:
    dates = pd.bdate_range("2022-01-01", periods=320)
    close = pd.DataFrame(
        {
            "SPY": np.linspace(100.0, 150.0, len(dates)),
            "QQQ": np.linspace(120.0, 140.0, len(dates)),
            "^VIX": np.linspace(16.0, 28.0, len(dates)),
        },
        index=dates,
    )

    figure = dashboard.build_buyer_participation_chart(close)

    assert len(figure.data) == 2
    assert figure.data[0].name == "Buyer Participation (20D)"
    assert figure.data[1].name == "New High Ratio (252D)"


def test_run_dashboard_builds_config_and_executes_use_case(monkeypatch) -> None:
    dashboard.run_dashboard.clear()
    captured: dict[str, object] = {}
    fake_now = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)

    class FakeDateTime:
        @classmethod
        def now(cls) -> datetime:
            return fake_now

    class CapturingUseCase:
        def __init__(self, market_data) -> None:  # type: ignore[no-untyped-def]
            captured["market_data"] = market_data

        def execute(self, config):  # type: ignore[no-untyped-def]
            captured["config"] = config
            return "done"

    monkeypatch.setattr(dashboard, "YFinanceMarketDataAdapter", FakeAdapter)
    monkeypatch.setattr(dashboard, "BuildCrashDashboardUseCase", CapturingUseCase)
    monkeypatch.setattr(dashboard, "datetime", FakeDateTime)

    result = dashboard.run_dashboard(
        ("SPY", "QQQ"),
        "SPY",
        "^VIX",
        "HYG",
        "^IRX",
        "^TNX",
        date(2024, 1, 1),
        date(2024, 12, 31),
    )

    assert isinstance(captured["market_data"], FakeAdapter)
    assert captured["config"].universe == ["SPY", "QQQ"]
    assert result == ("done", fake_now)


def test_run_dashboard_logs_refresh_window(monkeypatch, caplog) -> None:
    dashboard.run_dashboard.clear()

    class CapturingUseCase:
        def __init__(self, market_data) -> None:  # type: ignore[no-untyped-def]
            self.market_data = market_data

        def execute(self, config):  # type: ignore[no-untyped-def]
            return "done"

    monkeypatch.setattr(dashboard, "YFinanceMarketDataAdapter", FakeAdapter)
    monkeypatch.setattr(dashboard, "BuildCrashDashboardUseCase", CapturingUseCase)
    with caplog.at_level(logging.INFO):
        dashboard.run_dashboard(
            ("SPY", "QQQ"),
            "SPY",
            "^VIX",
            "HYG",
            "^IRX",
            "^TNX",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )

    assert any("Refreshing dashboard data" in record.message for record in caplog.records)


def test_schedule_refresh_and_format_refresh_timestamp(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_autorefresh(interval: int, key: str) -> int:
        captured["interval"] = interval
        captured["key"] = key
        return 1

    monkeypatch.setattr(dashboard, "st_autorefresh", fake_autorefresh)

    dashboard.schedule_refresh(interval_seconds=300)

    assert captured["interval"] == 300000
    assert captured["key"] == "market_crash_monitor_refresh"
    assert dashboard.format_refresh_timestamp(datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)) == "2024-05-06 14:30:00 CEST"


def test_telegram_alert_helpers(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat-id")

    result = make_result(True, False)
    refreshed_at = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)

    assert dashboard.get_secret("TELEGRAM_BOT_TOKEN") == "bot-token"
    assert dashboard.should_send_telegram_alert(result) is True
    assert "Risk-Off" in dashboard.build_alert_signature(result, "SPY")
    message = dashboard.build_telegram_alert_message(result, "SPY", refreshed_at)
    assert "Market Crash Monitor alert for SPY" in message
    assert "Refreshed: 2024-05-06 14:30:00 CEST" in message
    startup_message = dashboard.build_startup_message("SPY", refreshed_at)
    assert startup_message == "Market Crash Monitor started for SPY\nStartup time: 2024-05-06 14:30:00 CEST"


def test_build_action_condition_rows_covers_regimes_and_signals() -> None:
    low_result = make_result(False, False)
    low_result = DashboardResult(
        close_data=low_result.close_data,
        metrics={"drawdown_252": -0.03, "rsi14": 50.0, "price": 130.0, "ma50": 120.0},
        indicator_percentiles=low_result.indicator_percentiles,
        risk_score=45.0,
        risk_components=low_result.risk_components,
        regime=low_result.regime,
        actions=low_result.actions,
    )
    low_rows = dashboard.build_action_condition_rows(low_result)
    assert list(low_rows["Suggestion"]) == ["Maintain strategic risk"]

    caution_result = make_result(False, False)
    caution_result = DashboardResult(
        close_data=caution_result.close_data,
        metrics={
            "drawdown_252": -0.12,
            "rsi14": 32.0,
            "price": 99.0,
            "ma50": 120.0,
            "yield_curve_spread": -0.1,
        },
        indicator_percentiles=caution_result.indicator_percentiles,
        risk_score=60.0,
        risk_components=caution_result.risk_components,
        regime=caution_result.regime,
        actions=caution_result.actions,
    )
    caution_rows = dashboard.build_action_condition_rows(caution_result)
    assert list(caution_rows["Suggestion"]) == ["Partial de-risk", "Watchlist dip", "Yield curve caution"]

    high_result = make_result(True, False)
    high_result = DashboardResult(
        close_data=high_result.close_data,
        metrics={
            "drawdown_252": -0.12,
            "rsi14": 32.0,
            "price": 125.0,
            "ma50": 120.0,
            "vix": 20.0,
            "vix_sma20": 25.0,
            "yield_curve_spread": -0.1,
        },
        indicator_percentiles=high_result.indicator_percentiles,
        risk_score=75.0,
        risk_components=high_result.risk_components,
        regime=high_result.regime,
        actions=high_result.actions,
    )
    high_rows = dashboard.build_action_condition_rows(high_result)
    assert list(high_rows["Suggestion"]) == ["De-risk aggressively", "Buy-the-dip staging", "Yield curve caution"]


def test_build_action_condition_rows_includes_no_more_buyers_signal() -> None:
    result = make_result(False, False)
    result = DashboardResult(
        close_data=result.close_data,
        metrics={
            "drawdown_252": -0.02,
            "rsi14": 50.0,
            "price": 110.0,
            "ma50": 100.0,
            "buyer_exhaustion": 80.0,
            "buyer_participation_20d": 0.30,
            "new_high_ratio_252": 0.10,
        },
        indicator_percentiles=result.indicator_percentiles,
        risk_score=30.0,
        risk_components=result.risk_components,
        regime=result.regime,
        actions=result.actions,
    )

    rows = dashboard.build_action_condition_rows(result)
    assert list(rows["Suggestion"]) == ["Maintain strategic risk", "No more buyers"]


def test_get_secret_returns_none_when_secrets_are_unavailable(monkeypatch) -> None:
    class StreamlitWithoutSecrets:
        session_state: dict[str, str] = {}

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(dashboard, "st", StreamlitWithoutSecrets())

    assert dashboard.get_secret("TELEGRAM_BOT_TOKEN") is None


def test_get_secret_returns_none_when_streamlit_secrets_file_is_missing(monkeypatch) -> None:
    class SecretsThatRaise:
        def get(self, name: str):  # type: ignore[no-untyped-def]
            raise dashboard.StreamlitSecretNotFoundError("missing")

    class StreamlitWithRaisingSecrets:
        session_state: dict[str, str] = {}
        secrets = SecretsThatRaise()

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(dashboard, "st", StreamlitWithRaisingSecrets())

    assert dashboard.get_secret("TELEGRAM_BOT_TOKEN") is None


def test_get_telegram_status_variants(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(dashboard, "st", fake_st)

    assert dashboard.get_telegram_status() == "Telegram: missing Railway env vars"

    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token"}
    assert dashboard.get_telegram_status() == "Telegram: chat ID missing"

    fake_st.secrets = {"TELEGRAM_CHAT_ID": "secret-chat"}
    assert dashboard.get_telegram_status() == "Telegram: bot token missing"

    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "secret-chat"}
    assert dashboard.get_telegram_status() == "Telegram: configured"

    fake_st.session_state[dashboard.TELEGRAM_STATUS_KEY] = "startup message sent"
    assert dashboard.get_telegram_status() == "Telegram: startup message sent"


def test_get_telegram_status_style_variants(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(dashboard, "st", fake_st)

    assert dashboard.get_telegram_status_style() == ("gray", "missing Railway env vars")

    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token"}
    assert dashboard.get_telegram_status_style() == ("orange", "chat ID missing")

    fake_st.secrets = {"TELEGRAM_CHAT_ID": "secret-chat"}
    assert dashboard.get_telegram_status_style() == ("orange", "bot token missing")

    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "secret-chat"}
    assert dashboard.get_telegram_status_style() == ("blue", "configured")

    fake_st.session_state[dashboard.TELEGRAM_STATUS_KEY] = "startup message sent"
    assert dashboard.get_telegram_status_style() == ("green", "startup message sent")

    fake_st.session_state[dashboard.TELEGRAM_STATUS_KEY] = "alert sent"
    assert dashboard.get_telegram_status_style() == ("green", "alert sent")


def test_get_telegram_status_style_prefers_active_send_state(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "secret-chat"}
    monkeypatch.setattr(dashboard, "st", fake_st)

    fake_st.session_state[dashboard.TELEGRAM_STATUS_KEY] = "startup message sent"
    assert dashboard.get_telegram_status_style() == ("green", "startup message sent")

    fake_st.session_state[dashboard.TELEGRAM_STATUS_KEY] = "alert sent"
    assert dashboard.get_telegram_status_style() == ("green", "alert sent")


def test_get_secret_reads_from_streamlit_secrets(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token"}
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(dashboard, "st", fake_st)

    assert dashboard.get_secret("TELEGRAM_BOT_TOKEN") == "secret-token"


def test_maybe_send_telegram_alert_deduplicates_and_respects_threshold(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "secret-chat"}
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(dashboard, "st", fake_st)

    sent_messages: list[tuple[str, str, str]] = []

    class FakeNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            self.bot_token = bot_token
            self.chat_id = chat_id

        def send_message(self, text: str) -> None:
            sent_messages.append((self.bot_token, self.chat_id, text))

    monkeypatch.setattr(dashboard, "TelegramNotifier", FakeNotifier)
    refreshed_at = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)
    actionable = make_result(True, False)
    constructive = make_result(False, False)

    dashboard.maybe_send_telegram_alert(actionable, "SPY", refreshed_at)
    dashboard.maybe_send_telegram_alert(actionable, "SPY", refreshed_at)
    dashboard.maybe_send_telegram_alert(constructive, "SPY", refreshed_at)

    assert len(sent_messages) == 1
    assert sent_messages[0][0] == "secret-token"
    assert sent_messages[0][1] == "secret-chat"
    assert "Risk-Off" in sent_messages[0][2]
    assert fake_st.session_state[dashboard.LAST_ALERT_SIGNATURE_KEY] == dashboard.build_alert_signature(actionable, "SPY")
    assert fake_st.session_state[dashboard.TELEGRAM_STATUS_KEY] == "alert sent"


def test_maybe_send_telegram_alert_logs(monkeypatch, caplog) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "secret-chat"}
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(dashboard, "st", fake_st)

    class FakeNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            pass

        def send_message(self, text: str) -> None:
            return None

    monkeypatch.setattr(dashboard, "TelegramNotifier", FakeNotifier)
    refreshed_at = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)
    actionable = make_result(True, False)

    with caplog.at_level(logging.INFO):
        dashboard.maybe_send_telegram_alert(actionable, "SPY", refreshed_at)

    assert any("Sending Telegram alert" in record.message for record in caplog.records)


def test_maybe_send_startup_telegram_message_sends_once_per_session(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "secret-chat"}
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(dashboard, "st", fake_st)

    sent_messages: list[tuple[str, str, str]] = []

    class FakeNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            self.bot_token = bot_token
            self.chat_id = chat_id

        def send_message(self, text: str) -> None:
            sent_messages.append((self.bot_token, self.chat_id, text))

    monkeypatch.setattr(dashboard, "TelegramNotifier", FakeNotifier)
    refreshed_at = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)

    dashboard.maybe_send_startup_telegram_message("SPY", refreshed_at)
    dashboard.maybe_send_startup_telegram_message("SPY", refreshed_at)

    assert sent_messages == [
        ("secret-token", "secret-chat", "Market Crash Monitor started for SPY\nStartup time: 2024-05-06 14:30:00 CEST")
    ]
    assert fake_st.session_state[dashboard.STARTUP_MESSAGE_SENT_KEY] == "sent"
    assert fake_st.session_state[dashboard.TELEGRAM_STATUS_KEY] == "startup message sent"


def test_maybe_send_startup_telegram_message_logs(monkeypatch, caplog) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "secret-chat"}
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(dashboard, "st", fake_st)

    class FakeNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            pass

        def send_message(self, text: str) -> None:
            return None

    monkeypatch.setattr(dashboard, "TelegramNotifier", FakeNotifier)
    refreshed_at = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)

    with caplog.at_level(logging.INFO):
        dashboard.maybe_send_startup_telegram_message("SPY", refreshed_at)

    assert any("Sending Telegram startup message" in record.message for record in caplog.records)


def test_maybe_send_telegram_alert_skips_without_credentials_and_warning_on_failure(monkeypatch) -> None:
    fake_st = FakeStreamlit(["SPY, QQQ", "spy", "^vix", "hyg", "^irx", "^tnx"], slider_value=4)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(dashboard, "st", fake_st)
    stub_authenticated_user(monkeypatch)
    monkeypatch.setattr(dashboard, "schedule_refresh", lambda: None)
    refreshed_at = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)
    result = make_result(True, False)

    dashboard.maybe_send_telegram_alert(result, "SPY", refreshed_at)
    assert dashboard.LAST_ALERT_SIGNATURE_KEY not in fake_st.session_state
    dashboard.maybe_send_startup_telegram_message("SPY", refreshed_at)
    assert dashboard.STARTUP_MESSAGE_SENT_KEY not in fake_st.session_state

    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "secret-chat"}

    def raise_telegram_error(result: object, benchmark: str, refreshed_at: datetime) -> None:
        raise dashboard.TelegramNotificationError("Unable to send Telegram notification.")

    monkeypatch.setattr(dashboard, "maybe_send_startup_telegram_message", lambda benchmark, refreshed_at: None)
    monkeypatch.setattr(dashboard, "maybe_send_telegram_alert", raise_telegram_error)
    monkeypatch.setattr(dashboard, "run_dashboard", lambda *args: (result, refreshed_at))
    monkeypatch.setattr(dashboard, "build_price_chart", lambda close, benchmark: {"benchmark": benchmark})

    dashboard.render()

    assert fake_st.warnings == ["Unable to send Telegram notification."]


def test_render_shows_telegram_status(monkeypatch) -> None:
    fake_st = FakeStreamlit(["SPY", "SPY", "^VIX", "HYG", "^IRX", "^TNX"], slider_value=4)
    fake_st.secrets = {"TELEGRAM_BOT_TOKEN": "secret-token", "TELEGRAM_CHAT_ID": "secret-chat"}
    monkeypatch.setattr(dashboard, "st", fake_st)
    stub_authenticated_user(monkeypatch)
    monkeypatch.setattr(dashboard, "schedule_refresh", lambda: None)
    monkeypatch.setattr(dashboard, "maybe_send_startup_telegram_message", lambda benchmark, refreshed_at: None)
    monkeypatch.setattr(dashboard, "maybe_send_telegram_alert", lambda result, benchmark, refreshed_at: None)
    monkeypatch.setattr(
        dashboard,
        "run_dashboard",
        lambda *args: (make_result(True, False), datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)),
    )
    monkeypatch.setattr(dashboard, "build_price_chart", lambda close, benchmark: {"benchmark": benchmark})

    dashboard.render()

    assert any("Telegram: configured" in message for message in fake_st.markdowns)


def test_clear_dashboard_cache_calls_clear_when_available() -> None:
    cleared: list[str] = []

    class Clearable:
        @staticmethod
        def clear() -> None:
            cleared.append("cleared")

    original = dashboard.run_dashboard
    dashboard.run_dashboard = Clearable()
    try:
        dashboard.clear_dashboard_cache()
    finally:
        dashboard.run_dashboard = original

    assert cleared == ["cleared"]


def test_clear_dashboard_cache_ignores_missing_clear() -> None:
    original = dashboard.run_dashboard
    dashboard.run_dashboard = object()
    try:
        dashboard.clear_dashboard_cache()
    finally:
        dashboard.run_dashboard = original


def test_render_success_path_with_yield_curve(monkeypatch) -> None:
    fake_st = FakeStreamlit(["SPY, QQQ", "spy", "^vix", "hyg", "^irx", "^tnx"], slider_value=4)
    monkeypatch.setattr(dashboard, "st", fake_st)
    stub_authenticated_user(monkeypatch)
    monkeypatch.setattr(dashboard, "schedule_refresh", lambda: None)
    refreshed_at = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(dashboard, "run_dashboard", lambda *args: (make_result(True, False), refreshed_at))
    monkeypatch.setattr(dashboard, "build_price_chart", lambda close, benchmark: {"benchmark": benchmark})

    dashboard.render()

    top_metrics = fake_st.columns_created[0]
    assert ("Yield Spread (L-S)", "-0.25%") in top_metrics[4].metrics
    assert any("**Regime:** :red[" in message for message in fake_st.markdowns)
    assert any("**Yield Curve:** :red[Inverted]" == message for message in fake_st.markdowns)
    assert fake_st.writes == ["- First action", "- Second action"]
    assert fake_st.plot_calls == 2
    assert len(fake_st.dataframes) == 3
    assert list(fake_st.dataframes[0]["Suggestion"]) == ["De-risk aggressively", "Yield curve caution"]
    assert list(fake_st.dataframes[1]["Component"]) == ["Trend stress", "Breadth stress"]
    assert fake_st.dataframes[2].iloc[0]["Current"] == 130.1234
    assert fake_st.captions[-1] == "Last refreshed: 2024-05-06 14:30:00 CEST"


def test_render_force_refresh_updates_tables_and_error_path(monkeypatch) -> None:
    fake_st = FakeStreamlit(
        [
            "SPY",
            "SPY",
            "^VIX",
            "HYG",
            "^IRX",
            "^TNX",
            "SPY",
            "SPY",
            "^VIX",
            "HYG",
            "^IRX",
            "^TNX",
            "SPY",
            "SPY",
            "^VIX",
            "HYG",
            "^IRX",
            "^TNX",
        ],
        slider_value=1,
        button_values=[False, True, False, False, False, False],
    )
    monkeypatch.setattr(dashboard, "st", fake_st)
    stub_authenticated_user(monkeypatch)
    monkeypatch.setattr(dashboard, "schedule_refresh", lambda: None)

    cleared: list[str] = []
    monkeypatch.setattr(dashboard, "clear_dashboard_cache", lambda: cleared.append("cleared"))

    first_result = make_result(False, True)
    second_result = make_result(False, False)
    second_result = DashboardResult(
        close_data=second_result.close_data,
        metrics=second_result.metrics,
        indicator_percentiles=pd.DataFrame([{"Indicator": "Price", "Current": 131.98765, "P5": 100.0, "P50": 115.0, "P95": 130.0}]),
        risk_score=second_result.risk_score,
        risk_components={"Trend stress": 20.0, "Breadth stress": 5.0},
        regime=second_result.regime,
        actions=second_result.actions,
    )
    results = [
        (first_result, datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)),
        (second_result, datetime(2024, 5, 6, 12, 35, tzinfo=timezone.utc)),
        ValueError("bad symbols"),
    ]

    def fake_run_dashboard(*args):  # type: ignore[no-untyped-def]
        next_result = results.pop(0)
        if isinstance(next_result, Exception):
            raise next_result
        return next_result

    monkeypatch.setattr(dashboard, "run_dashboard", fake_run_dashboard)
    monkeypatch.setattr(dashboard, "build_price_chart", lambda close, benchmark: {"benchmark": benchmark})

    dashboard.render()
    dashboard.render()
    dashboard.render()

    top_metrics = fake_st.columns_created[0]
    assert ("Yield Spread (L-S)", "N/A") in top_metrics[4].metrics
    assert any("**Regime:** :green[" in message for message in fake_st.markdowns)
    assert list(fake_st.dataframes[0]["Suggestion"]) == ["Maintain strategic risk"]
    assert fake_st.dataframes[2].empty
    assert list(fake_st.dataframes[3]["Suggestion"]) == ["Maintain strategic risk"]
    assert fake_st.dataframes[4].iloc[0]["Score"] == 20.0
    assert fake_st.dataframes[5].iloc[0]["Current"] == 131.9876
    assert fake_st.plot_calls == 4
    assert cleared == ["cleared"]
    refresh_captions = [caption for caption in fake_st.captions if caption.startswith("Last refreshed:")]
    assert refresh_captions == [
        "Last refreshed: 2024-05-06 14:30:00 CEST",
        "Last refreshed: 2024-05-06 14:35:00 CEST",
    ]
    assert fake_st.errors == ["bad symbols"]


def test_derive_clerk_frontend_api_host_decodes_publishable_key() -> None:
    publishable_key = "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"

    assert dashboard.derive_clerk_frontend_api_host(publishable_key) == "example.clerk.accounts.dev"


def test_get_app_base_url_prefers_env_and_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com")
    assert dashboard.get_app_base_url() == "https://app.example.com"

    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://public.example.com")
    assert dashboard.get_app_base_url() == "https://public.example.com"

    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    assert dashboard.get_app_base_url() == "http://localhost:8501"


def test_get_configured_clerk_page_url_supports_absolute_relative_and_missing(monkeypatch) -> None:
    monkeypatch.delenv("CLERK_SIGN_IN_URL", raising=False)
    monkeypatch.delenv("CLERK_SIGN_UP_URL", raising=False)
    assert dashboard.get_configured_clerk_page_url("sign-in") is None

    monkeypatch.setenv("CLERK_SIGN_IN_URL", "https://accounts.example.com/sign-in")
    assert (
        dashboard.get_configured_clerk_page_url("sign-in")
        == "https://accounts.example.com/sign-in?redirect_url=http%3A%2F%2Flocalhost%3A8501"
    )

    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("CLERK_SIGN_UP_URL", "/sign-up")
    assert (
        dashboard.get_configured_clerk_page_url("sign-up")
        == "https://app.example.com/sign-up?redirect_url=https%3A%2F%2Fapp.example.com"
    )


def test_with_redirect_url_preserves_existing_redirect(monkeypatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com")

    assert (
        dashboard.with_redirect_url(
            "https://accounts.example.com/sign-in?redirect_url=https%3A%2F%2Falready.example.com",
            dashboard.get_app_base_url(),
        )
        == "https://accounts.example.com/sign-in?redirect_url=https%3A%2F%2Falready.example.com"
    )


def test_query_param_helpers_support_dict_like_streamlit(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=1)
    fake_st.query_params = {dashboard.CLERK_SESSION_TOKEN_PARAM: "token-123"}
    monkeypatch.setattr(dashboard, "st", fake_st)

    assert dashboard.get_query_param(dashboard.CLERK_SESSION_TOKEN_PARAM) == "token-123"
    dashboard.clear_query_param(dashboard.CLERK_SESSION_TOKEN_PARAM)
    assert dashboard.get_query_param(dashboard.CLERK_SESSION_TOKEN_PARAM) is None

    fake_st.query_params = {dashboard.CLERK_SESSION_TOKEN_PARAM: ["token-456"]}
    assert dashboard.get_query_param(dashboard.CLERK_SESSION_TOKEN_PARAM) == "token-456"


def test_render_shows_login_screen_when_logged_out(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=4)
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "schedule_refresh", lambda: None)
    monkeypatch.setattr(dashboard, "get_current_user", lambda: None)
    monkeypatch.setattr(dashboard, "authenticate_session_token", lambda token: None)

    auth_gate_calls: list[str] = []
    monkeypatch.setattr(dashboard, "render_auth_gate", lambda: auth_gate_calls.append("shown"))

    run_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(dashboard, "run_dashboard", lambda *args: run_calls.append(args))

    dashboard.render()

    assert auth_gate_calls == ["shown"]
    assert run_calls == []


def test_render_uses_auth_gate_token_to_enter_dashboard(monkeypatch) -> None:
    fake_st = FakeStreamlit(
        ["SPY, QQQ", "spy", "^vix", "hyg", "^irx", "^tnx"],
        slider_value=4,
        button_values=[False],
    )
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "schedule_refresh", lambda: None)
    monkeypatch.setattr(dashboard, "get_current_user", lambda: None)
    monkeypatch.setattr(dashboard, "render_auth_gate", lambda: "token-123")
    monkeypatch.setattr(dashboard, "authenticate_session_token", lambda token: make_user() if token == "token-123" else None)
    monkeypatch.setattr(dashboard, "render_account_widget", lambda: None)

    captured: dict[str, object] = {}
    refreshed_at = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)

    def fake_run_dashboard(*args):  # type: ignore[no-untyped-def]
        captured["args"] = args
        return make_result(False, False), refreshed_at

    monkeypatch.setattr(dashboard, "run_dashboard", fake_run_dashboard)
    monkeypatch.setattr(dashboard, "build_price_chart", lambda close, benchmark: {"benchmark": benchmark})

    dashboard.render()

    assert captured["args"][0] == ("SPY", "QQQ")


def test_render_authenticated_user_enters_configurable_dashboard(monkeypatch) -> None:
    fake_st = FakeStreamlit(
        ["SPY, QQQ", "spy", "^vix", "hyg", "^irx", "^tnx"],
        slider_value=4,
        button_values=[False],
    )
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "schedule_refresh", lambda: None)
    stub_authenticated_user(monkeypatch)

    captured: dict[str, object] = {}
    refreshed_at = datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)

    def fake_run_dashboard(*args):  # type: ignore[no-untyped-def]
        captured["args"] = args
        return make_result(False, False), refreshed_at

    monkeypatch.setattr(dashboard, "run_dashboard", fake_run_dashboard)
    monkeypatch.setattr(dashboard, "build_price_chart", lambda close, benchmark: {"benchmark": benchmark})

    dashboard.render()

    assert captured["args"][0] == ("SPY", "QQQ")
    assert captured["args"][1] == "SPY"
    assert any("Signed in as: `Ada Lovelace`" in message for message in fake_st.markdowns)
    assert "user@example.com" in fake_st.captions


def test_render_uses_auth_gate_when_session_is_invalid(monkeypatch) -> None:
    fake_st = FakeStreamlit([], slider_value=4)
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "schedule_refresh", lambda: None)
    monkeypatch.setattr(dashboard, "get_current_user", lambda: None)

    auth_gate_calls: list[str] = []
    monkeypatch.setattr(dashboard, "render_auth_gate", lambda: auth_gate_calls.append("shown"))

    run_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(dashboard, "run_dashboard", lambda *args: run_calls.append(args))

    dashboard.render()

    assert auth_gate_calls == ["shown"]
    assert run_calls == []
