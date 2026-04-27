from __future__ import annotations

import numpy as np
import pandas as pd

from src.domain.models import CAUTION_CUTOFF, RISK_OFF_CUTOFF


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1 / window, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / window, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def normalize_yield_series(series: pd.Series) -> pd.Series:
    # Yahoo yield indices like ^TNX are often quoted as 10x percentage points.
    return series.where(series <= 20, series / 10)


def compute_metrics(
    close: pd.DataFrame,
    benchmark: str,
    vix_symbol: str,
    risk_proxy: str,
    short_yield_symbol: str,
    long_yield_symbol: str,
) -> dict[str, float]:
    bench = close[benchmark].dropna()
    if len(bench) < 220:
        raise ValueError("Not enough benchmark history to compute 200-day trend and drawdown.")

    ma_200 = bench.rolling(200).mean()
    ma_50 = bench.rolling(50).mean()
    dd_252 = bench / bench.rolling(252).max() - 1.0
    ret = bench.pct_change()
    vol20 = ret.rolling(20).std() * np.sqrt(252)
    rsi14 = compute_rsi(bench, 14)

    breadth = (close / close.rolling(200).mean()) > 1
    breadth_ratio = breadth.iloc[-1].mean() if not breadth.empty else np.nan

    metrics = {
        "price": float(bench.iloc[-1]),
        "ma50": float(ma_50.iloc[-1]),
        "ma200": float(ma_200.iloc[-1]),
        "drawdown_252": float(dd_252.iloc[-1]),
        "vol20": float(vol20.iloc[-1]),
        "rsi14": float(rsi14.iloc[-1]),
        "breadth_ratio": float(breadth_ratio),
    }

    if vix_symbol in close:
        vix = close[vix_symbol].dropna()
        if len(vix) > 20:
            metrics["vix"] = float(vix.iloc[-1])
            metrics["vix_sma20"] = float(vix.rolling(20).mean().iloc[-1])

    if risk_proxy in close:
        proxy = close[risk_proxy].dropna()
        if len(proxy) > 50:
            metrics["risk_proxy"] = float(proxy.iloc[-1] / proxy.rolling(50).mean().iloc[-1])

    if short_yield_symbol in close and long_yield_symbol in close:
        short_yield = normalize_yield_series(close[short_yield_symbol].dropna())
        long_yield = normalize_yield_series(close[long_yield_symbol].dropna())
        if not short_yield.empty and not long_yield.empty:
            metrics["short_yield"] = float(short_yield.iloc[-1])
            metrics["long_yield"] = float(long_yield.iloc[-1])
            metrics["yield_curve_spread"] = float(long_yield.iloc[-1] - short_yield.iloc[-1])

    return metrics


def summarize_series_percentiles(name: str, series: pd.Series) -> dict[str, float | str] | None:
    clean = series.dropna()
    if clean.empty:
        return None

    quantiles = clean.quantile([0.05, 0.50, 0.95])
    return {
        "Indicator": name,
        "Current": float(clean.iloc[-1]),
        "P5": float(quantiles.loc[0.05]),
        "P50": float(quantiles.loc[0.50]),
        "P95": float(quantiles.loc[0.95]),
    }


def compute_indicator_percentiles(
    close: pd.DataFrame,
    benchmark: str,
    vix_symbol: str,
    risk_proxy: str,
    short_yield_symbol: str,
    long_yield_symbol: str,
) -> pd.DataFrame:
    bench = close[benchmark].dropna()
    ma_50 = bench.rolling(50).mean()
    ma_200 = bench.rolling(200).mean()
    dd_252 = bench / bench.rolling(252).max() - 1.0
    vol20 = bench.pct_change().rolling(20).std() * np.sqrt(252)
    rsi14 = compute_rsi(bench, 14)
    breadth_ratio_series = ((close / close.rolling(200).mean()) > 1).mean(axis=1)

    rows: list[dict[str, float | str]] = []
    series_map: list[tuple[str, pd.Series]] = [
        ("Price", bench),
        ("50D MA", ma_50),
        ("200D MA", ma_200),
        ("RSI(14)", rsi14),
        ("20D Vol (Ann.)", vol20),
        ("252D Drawdown", dd_252),
        ("Breadth >200D", breadth_ratio_series),
    ]

    if vix_symbol in close:
        series_map.append(("VIX", close[vix_symbol]))
    if risk_proxy in close:
        risk_proxy_ratio = close[risk_proxy] / close[risk_proxy].rolling(50).mean()
        series_map.append(("Risk Proxy / 50D MA", risk_proxy_ratio))
    if short_yield_symbol in close:
        series_map.append(("Short Yield", normalize_yield_series(close[short_yield_symbol])))
    if long_yield_symbol in close:
        series_map.append(("Long Yield", normalize_yield_series(close[long_yield_symbol])))
    if short_yield_symbol in close and long_yield_symbol in close:
        spread = normalize_yield_series(close[long_yield_symbol]) - normalize_yield_series(close[short_yield_symbol])
        series_map.append(("Yield Curve Spread (L-S)", spread))

    for name, series in series_map:
        row = summarize_series_percentiles(name, series)
        if row:
            rows.append(row)

    return pd.DataFrame(rows)


def compute_risk_score(metrics: dict[str, float]) -> tuple[float, dict[str, float]]:
    trend_penalty = clamp((metrics["ma200"] - metrics["price"]) / metrics["ma200"] * 250, 0, 100)
    dd_penalty = clamp(abs(min(metrics["drawdown_252"], 0)) * 400, 0, 100)
    vol_penalty = clamp((metrics["vol20"] - 0.15) / 0.25 * 100, 0, 100)
    rsi_penalty = clamp((45 - metrics["rsi14"]) * 3.0, 0, 100)
    breadth_penalty = clamp((0.55 - metrics["breadth_ratio"]) * 250, 0, 100)

    components: dict[str, float] = {
        "Trend stress": trend_penalty,
        "Drawdown stress": dd_penalty,
        "Volatility stress": vol_penalty,
        "Momentum stress": rsi_penalty,
        "Breadth stress": breadth_penalty,
    }

    if "vix" in metrics:
        components["VIX stress"] = clamp((metrics["vix"] - 18) * 5, 0, 100)

    if "risk_proxy" in metrics:
        components["Credit/risk stress"] = clamp((1.0 - metrics["risk_proxy"]) * 300, 0, 100)

    if "yield_curve_spread" in metrics:
        components["Yield curve stress"] = 80.0 if metrics["yield_curve_spread"] < 0 else 0.0

    weights = {
        "Trend stress": 0.23,
        "Drawdown stress": 0.18,
        "Volatility stress": 0.17,
        "Momentum stress": 0.13,
        "Breadth stress": 0.12,
        "VIX stress": 0.10,
        "Credit/risk stress": 0.07,
        "Yield curve stress": 0.08,
    }

    total_weight = sum(weights[key] for key in components)
    score = sum(components[key] * weights[key] for key in components) / total_weight
    return score, components


def recommend_actions(score: float, metrics: dict[str, float]) -> tuple[str, list[str]]:
    dip_zone = -0.20 < metrics["drawdown_252"] < -0.05
    oversold = metrics["rsi14"] < 35
    trend_reclaim = metrics["price"] > metrics["ma50"]
    vix_cooling = "vix" in metrics and "vix_sma20" in metrics and metrics["vix"] < metrics["vix_sma20"]

    if score >= RISK_OFF_CUTOFF:
        regime = "Risk-Off (High Crash Risk)"
        actions = [
            "De-risk aggressively: trim cyclical/high-beta exposure and tighten gross leverage.",
            "Raise defensive allocation and hold cash reserves for staged re-entry.",
            "Avoid new dip buys until volatility and trend pressure cool.",
        ]
    elif score >= CAUTION_CUTOFF:
        regime = "Caution (Fragile Market Regime)"
        actions = [
            "Partial de-risk: reduce weaker positions and focus on quality balance sheets.",
            "Use smaller position sizes and wider entry spacing.",
            "Wait for stabilization before adding significant risk.",
        ]
    else:
        regime = "Constructive (Low Crash Stress)"
        actions = [
            "No broad de-risk signal; maintain strategic risk with disciplined sizing.",
            "Prioritize entries in leaders holding above medium-term trend.",
        ]

    if dip_zone and oversold and (trend_reclaim or vix_cooling):
        actions.append(
            "Buy-the-dip signal: stage entries in 3 tranches (for example 40/30/30) over 5-10 trading days."
        )
    elif dip_zone and oversold:
        actions.append("Watchlist dip: oversold pullback detected, but wait for trend reclaim or falling fear gauge.")

    if "yield_curve_spread" in metrics and metrics["yield_curve_spread"] < 0:
        actions.append("Yield curve inverted: keep risk budgets tighter and emphasize defensive/quality exposure.")

    return regime, actions
