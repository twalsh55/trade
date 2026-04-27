from __future__ import annotations

from datetime import date

import pandas as pd

from src.application.use_cases import BuildCrashDashboardUseCase
from src.domain.models import DashboardConfig


class StubMarketData:
    def __init__(self, close: pd.DataFrame) -> None:
        self.close = close
        self.calls: list[tuple[list[str], date, date]] = []

    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        self.calls.append((tickers, start_date, end_date))
        return self.close


def test_use_case_executes_and_deduplicates_tickers() -> None:
    dates = pd.bdate_range("2020-01-01", periods=320)
    close = pd.DataFrame(
        {
            "SPY": range(320),
            "QQQ": range(100, 420),
            "^VIX": range(20, 340),
            "HYG": range(50, 370),
            "^IRX": range(60, 380),
            "^TNX": range(70, 390),
        },
        index=dates,
    ).astype(float)
    market_data = StubMarketData(close)
    use_case = BuildCrashDashboardUseCase(market_data=market_data)
    config = DashboardConfig(
        universe=["SPY", "QQQ", "SPY"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        start_date=date(2020, 1, 1),
        end_date=date(2021, 3, 31),
    )

    result = use_case.execute(config)

    tickers, start_date, end_date = market_data.calls[0]
    assert tickers == ["HYG", "QQQ", "SPY", "^IRX", "^TNX", "^VIX"]
    assert start_date == config.start_date
    assert end_date == config.end_date
    assert result.close_data.equals(close)
    assert result.metrics["price"] == float(close["SPY"].iloc[-1])
    assert result.regime
    assert result.actions


def test_use_case_raises_when_market_data_is_missing() -> None:
    market_data = StubMarketData(pd.DataFrame())
    use_case = BuildCrashDashboardUseCase(market_data=market_data)
    config = DashboardConfig(
        universe=["QQQ"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        start_date=date(2020, 1, 1),
        end_date=date(2020, 12, 31),
    )

    try:
        use_case.execute(config)
    except ValueError as exc:
        assert str(exc) == "Could not load market data. Check ticker symbols or network connectivity."
    else:
        raise AssertionError("Expected missing data to raise ValueError")
