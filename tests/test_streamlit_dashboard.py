from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from src.adapters.ui import streamlit_dashboard as dashboard
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


def test_schedule_refresh_and_format_refresh_timestamp(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_html(html: str, height: int) -> None:
        captured["html"] = html
        captured["height"] = height

    monkeypatch.setattr(dashboard.components, "html", fake_html)

    dashboard.schedule_refresh(interval_seconds=300)

    assert "window.parent.location.reload();" in captured["html"]
    assert "300000" in captured["html"]
    assert captured["height"] == 0
    assert dashboard.format_refresh_timestamp(datetime(2024, 5, 6, 12, 30, tzinfo=timezone.utc)) == "2024-05-06 12:30:00 UTC"


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
    assert "Refreshed: 2024-05-06 12:30:00 UTC" in message
    startup_message = dashboard.build_startup_message("SPY", refreshed_at)
    assert startup_message == "Market Crash Monitor started for SPY\nStartup time: 2024-05-06 12:30:00 UTC"


def test_get_secret_returns_none_when_secrets_are_unavailable(monkeypatch) -> None:
    class StreamlitWithoutSecrets:
        session_state: dict[str, str] = {}

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(dashboard, "st", StreamlitWithoutSecrets())

    assert dashboard.get_secret("TELEGRAM_BOT_TOKEN") is None


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
        ("secret-token", "secret-chat", "Market Crash Monitor started for SPY\nStartup time: 2024-05-06 12:30:00 UTC")
    ]
    assert fake_st.session_state[dashboard.STARTUP_MESSAGE_SENT_KEY] == "sent"


def test_maybe_send_telegram_alert_skips_without_credentials_and_warning_on_failure(monkeypatch) -> None:
    fake_st = FakeStreamlit(["SPY, QQQ", "spy", "^vix", "hyg", "^irx", "^tnx"], slider_value=4)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(dashboard, "st", fake_st)
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
    assert fake_st.plot_calls == 1
    assert len(fake_st.dataframes) == 2
    assert fake_st.dataframes[1].iloc[0]["Current"] == 130.1234
    assert fake_st.captions[-1] == "Last refreshed: 2024-05-06 12:30:00 UTC"


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
        button_values=[True, False],
    )
    monkeypatch.setattr(dashboard, "st", fake_st)
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
    assert fake_st.dataframes[1].empty
    assert not fake_st.dataframes[3].empty
    assert fake_st.dataframes[3].iloc[0]["Current"] == 131.9876
    assert fake_st.dataframes[2].iloc[0]["Score"] == 20.0
    assert cleared == ["cleared"]
    refresh_captions = [caption for caption in fake_st.captions if caption.startswith("Last refreshed:")]
    assert refresh_captions == [
        "Last refreshed: 2024-05-06 12:30:00 UTC",
        "Last refreshed: 2024-05-06 12:35:00 UTC",
    ]
    assert fake_st.errors == ["bad symbols"]
