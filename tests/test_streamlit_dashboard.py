from __future__ import annotations

from datetime import date

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
    def __init__(self, text_values: list[str], slider_value: int) -> None:
        self.sidebar = FakeSidebar()
        self._text_values = iter(text_values)
        self._slider_value = slider_value
        self.columns_created: list[list[FakeColumn]] = []
        self.errors: list[str] = []
        self.markdowns: list[str] = []
        self.subheaders: list[str] = []
        self.writes: list[str] = []
        self.dataframes: list[pd.DataFrame] = []
        self.plot_calls = 0

    def set_page_config(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.page_config = kwargs

    def title(self, value: str) -> None:
        self.title_value = value

    def caption(self, value: str) -> None:
        self.caption_value = value

    def header(self, value: str) -> None:
        self.header_value = value

    def text_input(self, label: str, default: str) -> str:
        return next(self._text_values)

    def slider(self, label: str, min_value: int, max_value: int, value: int) -> int:
        return self._slider_value

    def error(self, message: str) -> None:
        self.errors.append(message)

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

    class CapturingUseCase:
        def __init__(self, market_data) -> None:  # type: ignore[no-untyped-def]
            captured["market_data"] = market_data

        def execute(self, config):  # type: ignore[no-untyped-def]
            captured["config"] = config
            return "done"

    monkeypatch.setattr(dashboard, "YFinanceMarketDataAdapter", FakeAdapter)
    monkeypatch.setattr(dashboard, "BuildCrashDashboardUseCase", CapturingUseCase)

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
    assert result == "done"


def test_render_success_path_with_yield_curve(monkeypatch) -> None:
    fake_st = FakeStreamlit(["SPY, QQQ", "spy", "^vix", "hyg", "^irx", "^tnx"], slider_value=4)
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "run_dashboard", lambda *args: make_result(True, False))
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


def test_render_success_path_without_yield_curve_and_error_path(monkeypatch) -> None:
    fake_st = FakeStreamlit(
        ["SPY", "SPY", "^VIX", "HYG", "^IRX", "^TNX", "SPY", "SPY", "^VIX", "HYG", "^IRX", "^TNX"],
        slider_value=1,
    )
    monkeypatch.setattr(dashboard, "st", fake_st)

    results = [make_result(False, True), ValueError("bad symbols")]

    def fake_run_dashboard(*args):  # type: ignore[no-untyped-def]
        next_result = results.pop(0)
        if isinstance(next_result, Exception):
            raise next_result
        return next_result

    monkeypatch.setattr(dashboard, "run_dashboard", fake_run_dashboard)
    monkeypatch.setattr(dashboard, "build_price_chart", lambda close, benchmark: {"benchmark": benchmark})

    dashboard.render()
    dashboard.render()

    top_metrics = fake_st.columns_created[0]
    assert ("Yield Spread (L-S)", "N/A") in top_metrics[4].metrics
    assert any("**Regime:** :green[" in message for message in fake_st.markdowns)
    assert fake_st.dataframes[1].empty
    assert fake_st.errors == ["bad symbols"]
