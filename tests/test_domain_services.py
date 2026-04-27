from __future__ import annotations

import numpy as np
import pandas as pd

from src.domain.services import (
    clamp,
    compute_indicator_percentiles,
    compute_metrics,
    compute_risk_score,
    compute_rsi,
    normalize_yield_series,
    recommend_actions,
    summarize_series_percentiles,
)


def make_close_frame(periods: int = 320) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=periods)
    benchmark = np.linspace(100.0, 180.0, periods)
    return pd.DataFrame(
        {
            "SPY": benchmark,
            "QQQ": benchmark * 1.05,
            "IWM": benchmark * 0.95,
            "^VIX": np.linspace(16.0, 28.0, periods),
            "HYG": np.linspace(100.0, 98.0, periods),
            "^IRX": np.linspace(52.0, 58.0, periods),
            "^TNX": np.linspace(34.0, 31.0, periods),
        },
        index=dates,
    )


def test_clamp_and_normalize_yield_series() -> None:
    assert clamp(-1.0, 0.0, 10.0) == 0.0
    assert clamp(5.0, 0.0, 10.0) == 5.0
    assert clamp(99.0, 0.0, 10.0) == 10.0

    series = pd.Series([1.5, 22.0, 45.0])
    normalized = normalize_yield_series(series)

    assert normalized.tolist() == [1.5, 2.2, 4.5]


def test_compute_rsi_and_series_percentiles_helpers() -> None:
    prices = pd.Series([100.0, 102.0, 101.0, 104.0, 103.0, 106.0, 108.0, 107.0, 110.0])
    rsi = compute_rsi(prices, window=3)

    assert len(rsi) == len(prices)
    assert rsi.iloc[-1] > 0

    summary = summarize_series_percentiles("Demo", pd.Series([1.0, 2.0, 3.0, 4.0]))
    assert summary == {"Indicator": "Demo", "Current": 4.0, "P5": 1.15, "P50": 2.5, "P95": 3.8499999999999996}

    assert summarize_series_percentiles("Empty", pd.Series([np.nan, np.nan])) is None


def test_compute_metrics_requires_sufficient_history() -> None:
    dates = pd.bdate_range("2024-01-01", periods=100)
    close = pd.DataFrame({"SPY": np.linspace(100.0, 120.0, len(dates))}, index=dates)

    try:
        compute_metrics(close, "SPY", "^VIX", "HYG", "^IRX", "^TNX")
    except ValueError as exc:
        assert str(exc) == "Not enough benchmark history to compute 200-day trend and drawdown."
    else:
        raise AssertionError("Expected insufficient history to raise ValueError")


def test_compute_metrics_indicator_percentiles_and_risk_score_cover_optional_inputs() -> None:
    close = make_close_frame()

    metrics = compute_metrics(close, "SPY", "^VIX", "HYG", "^IRX", "^TNX")

    assert metrics["price"] == float(close["SPY"].iloc[-1])
    assert metrics["ma50"] > 0
    assert metrics["ma200"] > 0
    assert metrics["vix"] == float(close["^VIX"].iloc[-1])
    assert metrics["risk_proxy"] > 0
    assert metrics["short_yield"] == 5.8
    assert metrics["long_yield"] == 3.1
    assert metrics["yield_curve_spread"] == -2.6999999999999997

    indicator_percentiles = compute_indicator_percentiles(close, "SPY", "^VIX", "HYG", "^IRX", "^TNX")
    assert set(indicator_percentiles["Indicator"]) == {
        "Price",
        "50D MA",
        "200D MA",
        "20D Vol (Ann.)",
        "252D Drawdown",
        "Breadth >200D",
        "VIX",
        "Risk Proxy / 50D MA",
        "Short Yield",
        "Long Yield",
        "Yield Curve Spread (L-S)",
    }

    score, components = compute_risk_score(metrics)
    assert score > 0
    assert components["Yield curve stress"] == 80.0
    assert "VIX stress" in components
    assert "Credit/risk stress" in components


def test_recommend_actions_cover_all_regimes_and_dip_paths() -> None:
    high_regime, high_actions = recommend_actions(
        80.0,
        {
            "drawdown_252": -0.10,
            "rsi14": 25.0,
            "price": 101.0,
            "ma50": 100.0,
            "vix": 18.0,
            "vix_sma20": 21.0,
            "yield_curve_spread": -0.5,
        },
    )
    assert high_regime == "Risk-Off (High Crash Risk)"
    assert any("Buy-the-dip signal" in action for action in high_actions)
    assert any("Yield curve inverted" in action for action in high_actions)

    caution_regime, caution_actions = recommend_actions(
        55.0,
        {
            "drawdown_252": -0.10,
            "rsi14": 30.0,
            "price": 90.0,
            "ma50": 100.0,
        },
    )
    assert caution_regime == "Caution (Fragile Market Regime)"
    assert any("Watchlist dip" in action for action in caution_actions)

    constructive_regime, constructive_actions = recommend_actions(
        20.0,
        {
            "drawdown_252": -0.03,
            "rsi14": 55.0,
            "price": 110.0,
            "ma50": 100.0,
        },
    )
    assert constructive_regime == "Constructive (Low Crash Stress)"
    assert len(constructive_actions) == 2
