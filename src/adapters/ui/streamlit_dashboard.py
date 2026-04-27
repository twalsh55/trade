from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.adapters.market_data.yfinance_provider import YFinanceMarketDataAdapter
from src.application.use_cases import BuildCrashDashboardUseCase
from src.domain.models import CAUTION_CUTOFF, DEFAULT_UNIVERSE, RISK_OFF_CUTOFF, DashboardConfig


def build_price_chart(close: pd.DataFrame, benchmark: str) -> go.Figure:
    bench = close[benchmark].dropna()
    ma50 = bench.rolling(50).mean()
    ma200 = bench.rolling(200).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bench.index, y=bench, name=f"{benchmark} Price", line={"width": 2}))
    fig.add_trace(go.Scatter(x=ma50.index, y=ma50, name="50D MA", line={"dash": "dot"}))
    fig.add_trace(go.Scatter(x=ma200.index, y=ma200, name="200D MA", line={"dash": "dash"}))
    fig.update_layout(height=420, margin={"l": 12, "r": 12, "t": 24, "b": 12}, legend={"orientation": "h"})
    return fig


@st.cache_data(ttl=900)
def run_dashboard(
    universe: tuple[str, ...],
    benchmark: str,
    vix_symbol: str,
    risk_proxy: str,
    short_yield_symbol: str,
    long_yield_symbol: str,
    start_date: date,
    end_date: date,
):
    config = DashboardConfig(
        universe=list(universe),
        benchmark=benchmark,
        vix_symbol=vix_symbol,
        risk_proxy=risk_proxy,
        short_yield_symbol=short_yield_symbol,
        long_yield_symbol=long_yield_symbol,
        start_date=start_date,
        end_date=end_date,
    )
    use_case = BuildCrashDashboardUseCase(market_data=YFinanceMarketDataAdapter())
    return use_case.execute(config)


def render() -> None:
    st.set_page_config(page_title="Crash Monitor Dashboard", layout="wide")
    st.title("Market Crash Monitor")
    st.caption(
        "Tracks stress indicators and provides systematic de-risk / dip-buy cues. "
        "Educational use only, not investment advice."
    )

    with st.sidebar:
        st.header("Settings")
        universe_text = st.text_input("Risk Universe (comma-separated)", ", ".join(DEFAULT_UNIVERSE))
        benchmark = st.text_input("Benchmark Symbol", "SPY").upper().strip()
        vix_symbol = st.text_input("Fear Gauge Symbol", "^VIX").upper().strip()
        risk_proxy = st.text_input("Risk Proxy Symbol (credit/risk appetite)", "HYG").upper().strip()
        short_yield_symbol = st.text_input("Short Yield Symbol", "^IRX").upper().strip()
        long_yield_symbol = st.text_input("Long Yield Symbol", "^TNX").upper().strip()
        lookback_years = st.slider("Lookback (years)", min_value=1, max_value=10, value=4)

    universe = [t.strip().upper() for t in universe_text.split(",") if t.strip()]
    end_date = date.today()
    start_date = end_date - timedelta(days=365 * lookback_years)

    try:
        result = run_dashboard(
            tuple(universe),
            benchmark,
            vix_symbol,
            risk_proxy,
            short_yield_symbol,
            long_yield_symbol,
            start_date,
            end_date,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    metrics = result.metrics
    risk_color = "red" if result.risk_score >= RISK_OFF_CUTOFF else "orange" if result.risk_score >= CAUTION_CUTOFF else "green"

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Crash Risk Score", f"{result.risk_score:.1f}/100")
    c2.metric("252D Drawdown", f"{metrics['drawdown_252']:.1%}")
    c3.metric("20D Vol (Ann.)", f"{metrics['vol20']:.1%}")
    c4.metric("Breadth >200D", f"{metrics['breadth_ratio']:.1%}")
    if "yield_curve_spread" in metrics:
        c5.metric("Yield Spread (L-S)", f"{metrics['yield_curve_spread']:.2f}%")
    else:
        c5.metric("Yield Spread (L-S)", "N/A")

    st.markdown(f"**Regime:** :{risk_color}[{result.regime}]")
    if "yield_curve_spread" in metrics:
        curve_text = "Inverted" if metrics["yield_curve_spread"] < 0 else "Normal"
        curve_color = "red" if metrics["yield_curve_spread"] < 0 else "green"
        st.markdown(f"**Yield Curve:** :{curve_color}[{curve_text}]")

    st.subheader("Action Suggestions")
    for action in result.actions:
        st.write(f"- {action}")

    left, right = st.columns([2, 1])
    with left:
        st.subheader(f"{benchmark} Trend & Price")
        st.plotly_chart(build_price_chart(result.close_data, benchmark), width="stretch")
    with right:
        st.subheader("Risk Component Scores")
        component_df = (
            pd.DataFrame({"Component": list(result.risk_components.keys()), "Score": list(result.risk_components.values())})
            .sort_values("Score", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(component_df, hide_index=True, width="stretch")

    st.subheader("Indicators with Percentiles")
    indicator_table = result.indicator_percentiles.copy()
    if not indicator_table.empty:
        indicator_table = indicator_table.round(4)
    st.dataframe(
        indicator_table,
        hide_index=True,
        width="stretch",
    )
