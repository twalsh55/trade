from __future__ import annotations

import os
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from streamlit_autorefresh import st_autorefresh

from src.adapters.notifications.telegram_notifier import TelegramNotificationError, TelegramNotifier
from src.adapters.market_data.yfinance_provider import YFinanceMarketDataAdapter
from src.application.use_cases import BuildCrashDashboardUseCase
from src.domain.models import CAUTION_CUTOFF, DEFAULT_UNIVERSE, RISK_OFF_CUTOFF, DashboardConfig

REFRESH_INTERVAL_SECONDS = 300
LAST_ALERT_SIGNATURE_KEY = "last_telegram_alert_signature"
STARTUP_MESSAGE_SENT_KEY = "startup_telegram_message_sent"
TELEGRAM_STATUS_KEY = "telegram_status_message"
DISPLAY_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Rome"))

logger = logging.getLogger(__name__)


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
) -> tuple[object, datetime]:
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
    logger.info(
        "Refreshing dashboard data for %s through %s",
        start_date.isoformat(),
        end_date.isoformat(),
    )
    return use_case.execute(config), datetime.now().astimezone()


def schedule_refresh(interval_seconds: int = REFRESH_INTERVAL_SECONDS) -> None:
    st_autorefresh(interval=interval_seconds * 1000, key="market_crash_monitor_refresh")


def format_refresh_timestamp(refreshed_at: datetime) -> str:
    return refreshed_at.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")


def clear_dashboard_cache() -> None:
    clear = getattr(run_dashboard, "clear", None)
    if clear is not None:
        logger.info("Clearing cached dashboard data")
        clear()


def get_secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value

    try:
        secrets = getattr(st, "secrets", None)
        if secrets is None:
            return None

        secret_value = secrets.get(name)
    except StreamlitSecretNotFoundError:
        return None

    return str(secret_value) if secret_value else None


def get_telegram_status() -> str:
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not bot_token and not chat_id:
        return "Telegram: missing Railway env vars"
    if not bot_token:
        return "Telegram: bot token missing"
    if not chat_id:
        return "Telegram: chat ID missing"

    status = st.session_state.get(TELEGRAM_STATUS_KEY)
    return f"Telegram: {status}" if status else "Telegram: configured"


def get_telegram_status_style() -> tuple[str, str]:
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not bot_token and not chat_id:
        return "gray", "missing Railway env vars"
    if not bot_token or not chat_id:
        return "orange", get_telegram_status().replace("Telegram: ", "")

    status = st.session_state.get(TELEGRAM_STATUS_KEY)
    if status == "alert sent":
        return "green", "alert sent"
    if status == "startup message sent":
        return "green", "startup message sent"
    return "blue", "configured"


def should_send_telegram_alert(result: object) -> bool:
    actions = getattr(result, "actions", [])
    score = getattr(result, "risk_score", 0.0)
    return score >= CAUTION_CUTOFF or any(
        keyword in action
        for action in actions
        for keyword in ("Buy-the-dip signal", "Watchlist dip", "Yield curve inverted")
    )


def build_alert_signature(result: object, benchmark: str) -> str:
    actions = tuple(getattr(result, "actions", []))
    regime = getattr(result, "regime", "")
    score = round(float(getattr(result, "risk_score", 0.0)), 1)
    return repr((benchmark, regime, score, actions))


def build_telegram_alert_message(result: object, benchmark: str, refreshed_at: datetime) -> str:
    actions = "\n".join(f"- {action}" for action in getattr(result, "actions", []))
    return (
        f"Market Crash Monitor alert for {benchmark}\n"
        f"Regime: {getattr(result, 'regime', 'Unknown')}\n"
        f"Risk score: {float(getattr(result, 'risk_score', 0.0)):.1f}/100\n"
        f"Refreshed: {format_refresh_timestamp(refreshed_at)}\n"
        f"Actions:\n{actions}"
    )


def build_startup_message(benchmark: str, refreshed_at: datetime) -> str:
    return (
        f"Market Crash Monitor started for {benchmark}\n"
        f"Startup time: {format_refresh_timestamp(refreshed_at)}"
    )


def maybe_send_startup_telegram_message(benchmark: str, refreshed_at: datetime) -> None:
    if st.session_state.get(STARTUP_MESSAGE_SENT_KEY):
        return

    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return

    notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
    logger.info("Sending Telegram startup message for %s", benchmark)
    notifier.send_message(build_startup_message(benchmark, refreshed_at))
    st.session_state[STARTUP_MESSAGE_SENT_KEY] = "sent"
    st.session_state[TELEGRAM_STATUS_KEY] = "startup message sent"


def maybe_send_telegram_alert(result: object, benchmark: str, refreshed_at: datetime) -> None:
    if not should_send_telegram_alert(result):
        return

    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return

    signature = build_alert_signature(result, benchmark)
    if st.session_state.get(LAST_ALERT_SIGNATURE_KEY) == signature:
        return

    notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
    logger.info("Sending Telegram alert for %s with signature %s", benchmark, signature)
    notifier.send_message(build_telegram_alert_message(result, benchmark, refreshed_at))
    st.session_state[LAST_ALERT_SIGNATURE_KEY] = signature
    st.session_state[TELEGRAM_STATUS_KEY] = "alert sent"


def render() -> None:
    st.set_page_config(page_title="Crash Monitor Dashboard", layout="wide")
    schedule_refresh()
    logger.info("Rendering dashboard UI")
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
        force_refresh = st.button("Refresh Now")
        status_color, status_text = get_telegram_status_style()
        st.markdown(f":{status_color}[Telegram: {status_text}]")

    universe = [t.strip().upper() for t in universe_text.split(",") if t.strip()]
    end_date = date.today()
    start_date = end_date - timedelta(days=365 * lookback_years)

    if force_refresh:
        clear_dashboard_cache()

    try:
        result, refreshed_at = run_dashboard(
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

    try:
        maybe_send_telegram_alert(result, benchmark, refreshed_at)
    except TelegramNotificationError as exc:
        st.warning(str(exc))

    st.caption(f"Last refreshed: {format_refresh_timestamp(refreshed_at)}")

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
