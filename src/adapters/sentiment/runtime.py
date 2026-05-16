from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from src.adapters.llm.openai_etf_sentiment_agent import OpenAIETFSentimentAgent, TemplateETFSentimentAgent
from src.adapters.market_data.yfinance_provider import YFinanceMarketDataAdapter
from src.adapters.notifications.composite_email_notifier import CompositeEmailNotifier
from src.adapters.notifications.smtp_email_notifier import SMTPEmailNotifier
from src.adapters.notifications.telegram_digest_notifier import TelegramDigestNotifier
from src.adapters.notifications.telegram_notifier import TelegramNotifier
from src.adapters.sentiment.sources.google_news_rss import GoogleNewsRSSSource, SentimentSignal
from src.adapters.sentiment.sources.reddit_discussion import RedditDiscussionSource
from src.application.ports import EmailDeliveryPort

DEFAULT_ETF_PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts" / "ETF_SENTIMENT.md"
DEFAULT_ETF_UNIVERSE: tuple[tuple[str, str], ...] = (
    ("Global Equities", "VT"),
    ("US Large Cap", "SPY"),
    ("Nasdaq 100", "QQQ"),
    ("Emerging Markets", "EEM"),
    ("Semiconductors", "SOXX"),
    ("AI / Technology", "XLK"),
    ("Defense", "ITA"),
    ("Energy", "XLE"),
    ("Dividend", "SCHD"),
    ("Quality Factor", "QUAL"),
    ("Small Cap", "IWM"),
    ("Bonds", "BND"),
    ("Gold", "GLD"),
    ("Europe", "VGK"),
    ("India", "INDA"),
    ("China", "MCHI"),
)
DEFAULT_SENTIMENT_QUERIES: tuple[str, ...] = (
    "ETF market sentiment",
    "MSCI World ETF",
    "S&P 500 ETF sentiment",
    "Nasdaq 100 ETF",
    "AI ETF OR semiconductor ETF",
    "bond ETF OR defensive rotation",
)


class SentimentSignalSource(Protocol):
    def collect_signals(self, query: str, limit: int) -> list[SentimentSignal]:
        """Return recent text signals for the provided query."""


@dataclass(frozen=True)
class ETFSnapshot:
    label: str
    ticker: str
    last_close: float
    one_day_return_pct: float | None
    five_day_return_pct: float | None
    one_month_return_pct: float | None
    drawdown_from_52_week_high_pct: float | None
    realized_volatility_20d_pct: float | None


def run_etf_sentiment_job() -> str:
    prompt = load_etf_sentiment_prompt()
    market_snapshot = build_etf_market_snapshot()
    agent = build_etf_sentiment_agent_from_env()
    return agent.generate_briefing(prompt=prompt, market_snapshot=market_snapshot)


def deliver_etf_sentiment_job() -> str:
    briefing = run_etf_sentiment_job()
    build_etf_sentiment_delivery_from_env().send_email(
        recipient=os.getenv("ETF_SENTIMENT_EMAIL_RECIPIENT", os.getenv("PROSPECT_EMAIL_RECIPIENT", "tom.mg.walsh@gmail.com")).strip()
        or "tom.mg.walsh@gmail.com",
        subject=f"ETF sentiment brief for {date.today().isoformat()}",
        text_body=briefing,
    )
    return briefing


def load_etf_sentiment_prompt() -> str:
    prompt_path = Path(os.getenv("ETF_SENTIMENT_PROMPT_FILE", "").strip() or DEFAULT_ETF_PROMPT_FILE)
    try:
        content = prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"Unable to load ETF sentiment prompt file: {prompt_path}") from exc
    if not content:
        raise ValueError(f"ETF sentiment prompt file is empty: {prompt_path}")
    return content


def build_etf_sentiment_agent_from_env() -> OpenAIETFSentimentAgent | TemplateETFSentimentAgent:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return TemplateETFSentimentAgent()
    return OpenAIETFSentimentAgent(
        api_key=api_key,
        model=os.getenv("ETF_SENTIMENT_OPENAI_MODEL", "gpt-5-nano").strip() or "gpt-5-nano",
        max_output_tokens=parse_positive_int("ETF_SENTIMENT_OPENAI_MAX_OUTPUT_TOKENS", default=900),
    )


def build_email_notifier_from_env() -> SMTPEmailNotifier:
    return SMTPEmailNotifier(
        host=required_env("SMTP_HOST"),
        port=parse_positive_int("SMTP_PORT", default=587),
        username=required_env("SMTP_USERNAME"),
        password=required_env("SMTP_PASSWORD"),
        from_email=required_env("SMTP_FROM_EMAIL"),
        use_tls=os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false",
    )


def build_telegram_digest_notifier_from_env() -> TelegramDigestNotifier:
    return TelegramDigestNotifier(
        TelegramNotifier(
            bot_token=required_env("TELEGRAM_BOT_TOKEN"),
            chat_id=required_env("TELEGRAM_CHAT_ID"),
        )
    )


def build_etf_sentiment_delivery_from_env() -> EmailDeliveryPort:
    notifiers: list[EmailDeliveryPort] = []
    if has_configured_smtp_delivery():
        notifiers.append(build_email_notifier_from_env())
    if has_configured_telegram_delivery():
        notifiers.append(build_telegram_digest_notifier_from_env())
    if not notifiers:
        raise ValueError("Missing SMTP delivery settings and Telegram delivery fallback is unavailable.")
    if len(notifiers) == 1:
        return notifiers[0]
    return CompositeEmailNotifier(tuple(notifiers))


def build_etf_market_snapshot(
    market_data: YFinanceMarketDataAdapter | None = None,
    signal_sources: tuple[SentimentSignalSource, ...] | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    adapter = market_data or YFinanceMarketDataAdapter()
    signals = build_sentiment_signal_snapshot(signal_sources=signal_sources)
    resolved_date = as_of or date.today()
    lookback_days = parse_positive_int("ETF_SENTIMENT_LOOKBACK_DAYS", default=400)
    start_date = resolved_date - timedelta(days=lookback_days)
    universe = DEFAULT_ETF_UNIVERSE
    tickers = [ticker for _, ticker in universe]
    close_data = adapter.load_close_data(tickers, start_date, resolved_date)
    if close_data.empty:
        raise ValueError("Unable to load ETF market snapshot. Check ticker symbols or network connectivity.")

    snapshots: list[ETFSnapshot] = []
    for label, ticker in universe:
        if ticker not in close_data.columns:
            continue
        series = close_data[ticker].dropna()
        if series.empty:
            continue
        snapshots.append(
            ETFSnapshot(
                label=label,
                ticker=ticker,
                last_close=float(series.iloc[-1]),
                one_day_return_pct=_return_pct(series, periods=1),
                five_day_return_pct=_return_pct(series, periods=5),
                one_month_return_pct=_return_pct(series, periods=21),
                drawdown_from_52_week_high_pct=_drawdown_from_high_pct(series, periods=252),
                realized_volatility_20d_pct=_annualized_volatility_pct(series, periods=20),
            )
        )

    if not snapshots:
        raise ValueError("Unable to build ETF sentiment snapshot from downloaded market data.")

    average_five_day = _average_metric(snapshots, "five_day_return_pct")
    average_one_month = _average_metric(snapshots, "one_month_return_pct")
    market_mood = _classify_market_mood(average_five_day, average_one_month)

    leaders = sorted(
        (snapshot for snapshot in snapshots if snapshot.five_day_return_pct is not None),
        key=lambda snapshot: snapshot.five_day_return_pct or 0.0,
        reverse=True,
    )[:5]
    laggards = sorted(
        (snapshot for snapshot in snapshots if snapshot.five_day_return_pct is not None),
        key=lambda snapshot: snapshot.five_day_return_pct or 0.0,
    )[:5]
    crowding_watch = sorted(
        (
            snapshot
            for snapshot in snapshots
            if snapshot.one_month_return_pct is not None and snapshot.drawdown_from_52_week_high_pct is not None
        ),
        key=lambda snapshot: ((snapshot.one_month_return_pct or 0.0) + (snapshot.drawdown_from_52_week_high_pct or 0.0)),
        reverse=True,
    )[:5]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "data_note": (
            "This snapshot combines recent ETF price action via yfinance proxies with lightweight public text signals. "
            "It still does not include direct Trade Republic catalog data, ETF fund flow data, or private/proprietary datasets."
        ),
        "overview": {
            "tracked_etf_count": len(snapshots),
            "market_mood": market_mood,
            "average_five_day_return_pct": average_five_day,
            "average_one_month_return_pct": average_one_month,
        },
        "text_signals": signals,
        "leaders": [asdict(snapshot) for snapshot in leaders],
        "laggards": [asdict(snapshot) for snapshot in laggards],
        "crowding_watch": [asdict(snapshot) for snapshot in crowding_watch],
        "risk_flags": _build_risk_flags(snapshots),
        "etfs": [asdict(snapshot) for snapshot in snapshots],
    }


def collect_etf_sentiment_config_errors() -> list[str]:
    errors: list[str] = []
    prompt_path = Path(os.getenv("ETF_SENTIMENT_PROMPT_FILE", "").strip() or DEFAULT_ETF_PROMPT_FILE)
    if not prompt_path.is_file():
        errors.append(f"Missing ETF sentiment prompt file: {prompt_path}")

    for name in (
        "ETF_SENTIMENT_LOOKBACK_DAYS",
        "ETF_SENTIMENT_OPENAI_MAX_OUTPUT_TOKENS",
        "ETF_SENTIMENT_SIGNAL_LIMIT_PER_QUERY",
        "ETF_SENTIMENT_MAX_SIGNALS",
        "SMTP_PORT",
    ):
        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            continue
        try:
            if int(raw_value) <= 0:
                errors.append(f"{name} must be greater than zero")
        except ValueError:
            errors.append(f"{name} must be an integer")
    return errors


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing {name}. Add it to .env first.")
    return value


def parse_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def has_configured_smtp_delivery() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL")
    )


def has_configured_telegram_delivery() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    )


def build_sentiment_signal_snapshot(
    signal_sources: tuple[SentimentSignalSource, ...] | None = None,
) -> dict[str, Any]:
    queries = load_sentiment_queries_from_env()
    limit = parse_positive_int("ETF_SENTIMENT_SIGNAL_LIMIT_PER_QUERY", default=4)
    sources = build_signal_sources_from_env() if signal_sources is None else signal_sources

    if not sources:
        return {
            "queries": list(queries),
            "source_errors": [],
            "source_counts": {},
            "items": [],
        }

    items: list[SentimentSignal] = []
    source_errors: list[str] = []
    for query in queries:
        for source in sources:
            try:
                items.extend(source.collect_signals(query, limit))
            except RuntimeError as exc:
                source_errors.append(str(exc))

    deduped_items = _dedupe_signals(items)
    source_counts = _build_source_counts(deduped_items)
    return {
        "queries": list(queries),
        "source_errors": source_errors,
        "source_counts": source_counts,
        "items": [asdict(item) for item in deduped_items[: parse_positive_int("ETF_SENTIMENT_MAX_SIGNALS", default=18)]],
    }


def build_signal_sources_from_env() -> tuple[SentimentSignalSource, ...]:
    reddit_enabled = os.getenv("ETF_SENTIMENT_ENABLE_REDDIT_SIGNALS", "true").strip().lower() != "false"
    news_enabled = os.getenv("ETF_SENTIMENT_ENABLE_NEWS_SIGNALS", "true").strip().lower() != "false"
    sources: list[SentimentSignalSource] = []
    if reddit_enabled:
        sources.append(
            RedditDiscussionSource(
                user_agent=os.getenv("ETF_SENTIMENT_REDDIT_USER_AGENT", "brivoly-etf-sentiment-bot/0.1").strip()
                or "brivoly-etf-sentiment-bot/0.1"
            )
        )
    if news_enabled:
        sources.append(GoogleNewsRSSSource())
    return tuple(sources)


def load_sentiment_queries_from_env() -> tuple[str, ...]:
    raw_value = os.getenv("ETF_SENTIMENT_QUERIES", "").strip()
    queries = tuple(item.strip() for item in raw_value.split(",") if item.strip())
    return queries or DEFAULT_SENTIMENT_QUERIES


def _return_pct(series: pd.Series, periods: int) -> float | None:
    if len(series) <= periods:
        return None
    baseline = float(series.iloc[-periods - 1])
    latest = float(series.iloc[-1])
    if baseline == 0:
        return None
    return ((latest / baseline) - 1.0) * 100.0


def _drawdown_from_high_pct(series: pd.Series, periods: int) -> float | None:
    window = series.tail(periods)
    if window.empty:
        return None
    high = float(window.max())
    latest = float(window.iloc[-1])
    if high == 0:
        return None
    return ((latest / high) - 1.0) * 100.0


def _annualized_volatility_pct(series: pd.Series, periods: int) -> float | None:
    returns = series.pct_change().dropna().tail(periods)
    if len(returns) < max(2, periods // 2):
        return None
    return float(returns.std() * (252**0.5) * 100.0)


def _average_metric(snapshots: list[ETFSnapshot], name: str) -> float | None:
    values = [getattr(snapshot, name) for snapshot in snapshots]
    numeric_values = [value for value in values if isinstance(value, float)]
    if not numeric_values:
        return None
    return round(sum(numeric_values) / len(numeric_values), 2)


def _classify_market_mood(average_five_day: float | None, average_one_month: float | None) -> str:
    if average_five_day is None or average_one_month is None:
        return "neutral"
    if average_five_day >= 2.0 and average_one_month >= 4.0:
        return "optimistic"
    if average_five_day <= -2.0 and average_one_month <= -4.0:
        return "fearful"
    if average_five_day >= 0.75:
        return "constructive"
    if average_five_day <= -0.75:
        return "cautious"
    return "neutral"


def _build_risk_flags(snapshots: list[ETFSnapshot]) -> list[str]:
    flags: list[str] = []
    crowded = [
        snapshot.label
        for snapshot in snapshots
        if (snapshot.one_month_return_pct or -999.0) >= 8.0 and (snapshot.drawdown_from_52_week_high_pct or -999.0) >= -3.0
    ]
    defensive_strength = [
        snapshot.label
        for snapshot in snapshots
        if snapshot.label in {"Bonds", "Gold"} and (snapshot.five_day_return_pct or -999.0) >= 1.5
    ]
    high_vol = [
        snapshot.label
        for snapshot in snapshots
        if (snapshot.realized_volatility_20d_pct or 0.0) >= 30.0
    ]
    if crowded:
        flags.append("Potential crowding near highs in: " + ", ".join(crowded[:4]))
    if defensive_strength:
        flags.append("Defensive assets are strengthening: " + ", ".join(defensive_strength[:4]))
    if high_vol:
        flags.append("Elevated 20d realized volatility in: " + ", ".join(high_vol[:4]))
    return flags


def _dedupe_signals(items: list[SentimentSignal]) -> list[SentimentSignal]:
    seen: set[str] = set()
    deduped: list[SentimentSignal] = []
    for item in items:
        key = f"{item.source}:{item.url}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _build_source_counts(items: list[SentimentSignal]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.source] = counts.get(item.source, 0) + 1
    return counts
