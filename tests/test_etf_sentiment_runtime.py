from __future__ import annotations

from datetime import date

import pandas as pd

from src.adapters.sentiment.runtime import (
    DEFAULT_ETF_PROMPT_FILE,
    DEFAULT_SENTIMENT_QUERIES,
    ETFSnapshot,
    _annualized_volatility_pct,
    _average_metric,
    _build_source_counts,
    _build_risk_flags,
    _classify_market_mood,
    _dedupe_signals,
    _drawdown_from_high_pct,
    _return_pct,
    build_etf_market_snapshot,
    build_sentiment_signal_snapshot,
    build_etf_sentiment_agent_from_env,
    build_etf_sentiment_delivery_from_env,
    build_signal_sources_from_env,
    collect_etf_sentiment_config_errors,
    deliver_etf_sentiment_job,
    has_configured_smtp_delivery,
    has_configured_telegram_delivery,
    load_etf_sentiment_prompt,
    load_sentiment_queries_from_env,
    parse_positive_int,
    required_env,
    run_etf_sentiment_job,
)
from src.adapters.sentiment.sources.google_news_rss import SentimentSignal


def test_load_etf_sentiment_prompt_uses_env_override(tmp_path, monkeypatch) -> None:
    prompt_file = tmp_path / "etf.md"
    prompt_file.write_text("Prompt body", encoding="utf-8")
    monkeypatch.setenv("ETF_SENTIMENT_PROMPT_FILE", str(prompt_file))

    assert load_etf_sentiment_prompt() == "Prompt body"


def test_load_etf_sentiment_prompt_rejects_missing_and_empty_files(tmp_path, monkeypatch) -> None:
    missing_file = tmp_path / "missing.md"
    monkeypatch.setenv("ETF_SENTIMENT_PROMPT_FILE", str(missing_file))
    try:
        load_etf_sentiment_prompt()
    except ValueError as exc:
        assert str(exc) == f"Unable to load ETF sentiment prompt file: {missing_file}"
    else:
        raise AssertionError("Expected missing prompt file to fail")

    empty_file = tmp_path / "empty.md"
    empty_file.write_text("   ", encoding="utf-8")
    monkeypatch.setenv("ETF_SENTIMENT_PROMPT_FILE", str(empty_file))
    try:
        load_etf_sentiment_prompt()
    except ValueError as exc:
        assert str(exc) == f"ETF sentiment prompt file is empty: {empty_file}"
    else:
        raise AssertionError("Expected empty prompt file to fail")


def test_build_etf_sentiment_agent_from_env_switches_modes(monkeypatch) -> None:
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert build_etf_sentiment_agent_from_env().__class__.__name__ == "TemplateETFSentimentAgent"

    monkeypatch.setenv("APP_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ETF_SENTIMENT_OPENAI_MODEL", "gpt-5-mini")
    monkeypatch.setenv("ETF_SENTIMENT_OPENAI_MAX_OUTPUT_TOKENS", "123")
    agent = build_etf_sentiment_agent_from_env()
    assert agent.__class__.__name__ == "OpenAIETFSentimentAgent"
    assert agent.model == "gpt-5-mini"  # type: ignore[attr-defined]
    assert agent.max_output_tokens == 123  # type: ignore[attr-defined]


def test_build_etf_market_snapshot_computes_summary(monkeypatch) -> None:
    dates = pd.bdate_range("2025-01-01", periods=30)
    data = pd.DataFrame(
        {
            "VT": [100 + i for i in range(30)],
            "SPY": [200 + (i * 0.5) for i in range(30)],
            "QQQ": [300 + (i * 2.0) for i in range(30)],
            "EEM": [50 - (i * 0.2) for i in range(30)],
            "SOXX": [400 + (i * 3.0) for i in range(30)],
            "XLK": [150 + (i * 1.8) for i in range(30)],
            "ITA": [120 + (i * 0.8) for i in range(30)],
            "XLE": [90 + (i * 1.5) for i in range(30)],
            "SCHD": [70 + (i * 0.4) for i in range(30)],
            "QUAL": [80 + (i * 0.6) for i in range(30)],
            "IWM": [60 + (i * 0.3) for i in range(30)],
            "BND": [73 - (i * 0.1) for i in range(30)],
            "GLD": [180 + (i * 0.2) for i in range(30)],
            "VGK": [65 + (i * 0.4) for i in range(30)],
            "INDA": [40 + (i * 0.9) for i in range(30)],
            "MCHI": [45 - (i * 0.1) for i in range(30)],
        },
        index=dates,
    )

    class FakeAdapter:
        def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
            assert "VT" in tickers
            assert start_date < end_date
            return data[tickers]

    monkeypatch.delenv("ETF_SENTIMENT_LOOKBACK_DAYS", raising=False)
    snapshot = build_etf_market_snapshot(
        market_data=FakeAdapter(),
        signal_sources=(),
        as_of=date(2025, 2, 20),
    )  # type: ignore[arg-type]

    assert snapshot["overview"]["tracked_etf_count"] == 16
    assert snapshot["overview"]["market_mood"] in {"constructive", "optimistic"}
    assert snapshot["leaders"][0]["ticker"] == "INDA"
    assert snapshot["laggards"][0]["ticker"] in {"EEM", "MCHI", "BND"}
    assert snapshot["etfs"][0]["label"] == "Global Equities"
    assert "yfinance proxies" in snapshot["data_note"]
    assert snapshot["text_signals"]["items"] == []


def test_build_etf_market_snapshot_rejects_missing_data(monkeypatch) -> None:
    class EmptyAdapter:
        def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
            return pd.DataFrame()

    try:
        build_etf_market_snapshot(market_data=EmptyAdapter(), signal_sources=(), as_of=date(2025, 2, 20))  # type: ignore[arg-type]
    except ValueError as exc:
        assert str(exc) == "Unable to load ETF market snapshot. Check ticker symbols or network connectivity."
    else:
        raise AssertionError("Expected empty snapshot to fail")

    class MissingColumnsAdapter:
        def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
            return pd.DataFrame({"OTHER": [1.0, 2.0]}, index=pd.bdate_range("2025-01-01", periods=2))

    try:
        build_etf_market_snapshot(market_data=MissingColumnsAdapter(), signal_sources=(), as_of=date(2025, 2, 20))  # type: ignore[arg-type]
    except ValueError as exc:
        assert str(exc) == "Unable to build ETF sentiment snapshot from downloaded market data."
    else:
        raise AssertionError("Expected missing columns to fail")


def test_build_etf_market_snapshot_skips_empty_series_columns() -> None:
    dates = pd.bdate_range("2025-01-01", periods=30)
    data = pd.DataFrame(
        {
            "VT": [None] * 30,
            "SPY": [200 + i for i in range(30)],
            "QQQ": [300 + i for i in range(30)],
            "EEM": [50 + i for i in range(30)],
            "SOXX": [400 + i for i in range(30)],
            "XLK": [150 + i for i in range(30)],
            "ITA": [120 + i for i in range(30)],
            "XLE": [90 + i for i in range(30)],
            "SCHD": [70 + i for i in range(30)],
            "QUAL": [80 + i for i in range(30)],
            "IWM": [60 + i for i in range(30)],
            "BND": [73 + i for i in range(30)],
            "GLD": [180 + i for i in range(30)],
            "VGK": [65 + i for i in range(30)],
            "INDA": [40 + i for i in range(30)],
            "MCHI": [45 + i for i in range(30)],
        },
        index=dates,
    )

    class FakeAdapter:
        def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
            return data[tickers]

    snapshot = build_etf_market_snapshot(market_data=FakeAdapter(), signal_sources=(), as_of=date(2025, 2, 20))  # type: ignore[arg-type]
    assert snapshot["overview"]["tracked_etf_count"] == 15


def test_collect_etf_sentiment_config_errors_reports_missing_and_invalid_fields(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ETF_SENTIMENT_PROMPT_FILE", str(tmp_path / "missing.md"))
    monkeypatch.setenv("ETF_SENTIMENT_LOOKBACK_DAYS", "0")
    monkeypatch.setenv("ETF_SENTIMENT_OPENAI_MAX_OUTPUT_TOKENS", "abc")
    monkeypatch.setenv("ETF_SENTIMENT_SIGNAL_LIMIT_PER_QUERY", "-1")
    monkeypatch.setenv("ETF_SENTIMENT_MAX_SIGNALS", "zero")
    monkeypatch.setenv("SMTP_PORT", "bad")

    assert collect_etf_sentiment_config_errors() == [
        f"Missing ETF sentiment prompt file: {tmp_path / 'missing.md'}",
        "ETF_SENTIMENT_LOOKBACK_DAYS must be greater than zero",
        "ETF_SENTIMENT_OPENAI_MAX_OUTPUT_TOKENS must be an integer",
        "ETF_SENTIMENT_SIGNAL_LIMIT_PER_QUERY must be greater than zero",
        "ETF_SENTIMENT_MAX_SIGNALS must be an integer",
        "SMTP_PORT must be an integer",
    ]


def test_collect_etf_sentiment_config_errors_allows_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ETF_SENTIMENT_PROMPT_FILE", raising=False)
    monkeypatch.delenv("ETF_SENTIMENT_LOOKBACK_DAYS", raising=False)
    monkeypatch.delenv("ETF_SENTIMENT_OPENAI_MAX_OUTPUT_TOKENS", raising=False)
    assert DEFAULT_ETF_PROMPT_FILE.is_file()
    assert collect_etf_sentiment_config_errors() == []


def test_parse_positive_int_validates_values(monkeypatch) -> None:
    monkeypatch.setenv("ETF_SENTIMENT_LOOKBACK_DAYS", "15")
    assert parse_positive_int("ETF_SENTIMENT_LOOKBACK_DAYS", default=10) == 15

    monkeypatch.setenv("ETF_SENTIMENT_LOOKBACK_DAYS", "bad")
    try:
        parse_positive_int("ETF_SENTIMENT_LOOKBACK_DAYS", default=10)
    except ValueError as exc:
        assert str(exc) == "ETF_SENTIMENT_LOOKBACK_DAYS must be an integer."
    else:
        raise AssertionError("Expected integer validation failure")

    monkeypatch.setenv("ETF_SENTIMENT_LOOKBACK_DAYS", "-1")
    try:
        parse_positive_int("ETF_SENTIMENT_LOOKBACK_DAYS", default=10)
    except ValueError as exc:
        assert str(exc) == "ETF_SENTIMENT_LOOKBACK_DAYS must be greater than zero."
    else:
        raise AssertionError("Expected positive validation failure")


def test_load_sentiment_queries_from_env_uses_defaults_and_override(monkeypatch) -> None:
    monkeypatch.delenv("ETF_SENTIMENT_QUERIES", raising=False)
    assert load_sentiment_queries_from_env() == DEFAULT_SENTIMENT_QUERIES

    monkeypatch.setenv("ETF_SENTIMENT_QUERIES", "one, two , ,three")
    assert load_sentiment_queries_from_env() == ("one", "two", "three")


def test_build_signal_sources_from_env_respects_toggles(monkeypatch) -> None:
    monkeypatch.delenv("ETF_SENTIMENT_ENABLE_REDDIT_SIGNALS", raising=False)
    monkeypatch.delenv("ETF_SENTIMENT_ENABLE_NEWS_SIGNALS", raising=False)
    monkeypatch.delenv("ETF_SENTIMENT_ENABLE_X_SIGNALS", raising=False)
    monkeypatch.delenv("ETF_SENTIMENT_ENABLE_DISCORD_SIGNALS", raising=False)
    assert [source.__class__.__name__ for source in build_signal_sources_from_env()] == [
        "RedditDiscussionSource",
        "GoogleNewsRSSSource",
        "XDiscussionSource",
        "DiscordDiscussionSource",
    ]

    monkeypatch.setenv("ETF_SENTIMENT_ENABLE_REDDIT_SIGNALS", "false")
    monkeypatch.setenv("ETF_SENTIMENT_ENABLE_NEWS_SIGNALS", "false")
    monkeypatch.setenv("ETF_SENTIMENT_ENABLE_X_SIGNALS", "false")
    monkeypatch.setenv("ETF_SENTIMENT_ENABLE_DISCORD_SIGNALS", "false")
    assert build_signal_sources_from_env() == ()


def test_etf_sentiment_delivery_builders_and_config_helpers(monkeypatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert has_configured_smtp_delivery() is False
    assert has_configured_telegram_delivery() is False

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    assert has_configured_smtp_delivery() is True
    assert required_env("SMTP_HOST") == "smtp.example.com"
    assert build_etf_sentiment_delivery_from_env().__class__.__name__ == "SMTPEmailNotifier"

    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    assert has_configured_telegram_delivery() is True
    assert build_etf_sentiment_delivery_from_env().__class__.__name__ == "TelegramDigestNotifier"

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    assert build_etf_sentiment_delivery_from_env().__class__.__name__ == "CompositeEmailNotifier"

    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    try:
        build_etf_sentiment_delivery_from_env()
    except ValueError as exc:
        assert str(exc) == "Missing SMTP delivery settings and Telegram delivery fallback is unavailable."
    else:
        raise AssertionError("Expected delivery configuration failure")

    try:
        required_env("SMTP_HOST")
    except ValueError as exc:
        assert str(exc) == "Missing SMTP_HOST. Add it to .env first."
    else:
        raise AssertionError("Expected missing env validation failure")


def test_deliver_etf_sentiment_job_builds_and_sends(monkeypatch) -> None:
    sent: list[tuple[str, str, str]] = []

    class FakeDelivery:
        def send_email(self, recipient: str, subject: str, text_body: str) -> None:
            sent.append((recipient, subject, text_body))

    monkeypatch.setattr("src.adapters.sentiment.runtime.run_etf_sentiment_job", lambda: "ETF Sentiment Brief")
    monkeypatch.setattr("src.adapters.sentiment.runtime.build_etf_sentiment_delivery_from_env", lambda: FakeDelivery())
    monkeypatch.setenv("ETF_SENTIMENT_EMAIL_RECIPIENT", "sentiment@example.com")

    assert deliver_etf_sentiment_job() == "ETF Sentiment Brief"
    assert sent == [("sentiment@example.com", f"ETF sentiment brief for {date.today().isoformat()}", "ETF Sentiment Brief")]


def test_build_sentiment_signal_snapshot_collects_dedupes_and_records_errors(monkeypatch) -> None:
    class WorkingSource:
        def __init__(self, name: str) -> None:
            self.name = name

        def collect_signals(self, query: str, limit: int) -> list[SentimentSignal]:
            assert limit == 2
            return [
                SentimentSignal(self.name, "channel", query, f"{self.name} {query}", "summary", "https://example.com/shared", "2026-01-01T00:00:00+00:00"),
                SentimentSignal(self.name, "channel", query, f"{self.name} unique {query}", "summary", f"https://example.com/{self.name}/{query}", "2026-01-02T00:00:00+00:00"),
            ]

    class FailingSource:
        def collect_signals(self, query: str, limit: int) -> list[SentimentSignal]:
            raise RuntimeError(f"broken {query}")

    monkeypatch.setenv("ETF_SENTIMENT_QUERIES", "alpha,beta")
    monkeypatch.setenv("ETF_SENTIMENT_SIGNAL_LIMIT_PER_QUERY", "2")
    monkeypatch.setenv("ETF_SENTIMENT_MAX_SIGNALS", "3")

    snapshot = build_sentiment_signal_snapshot(signal_sources=(WorkingSource("reddit"), FailingSource()))  # type: ignore[arg-type]

    assert snapshot["queries"] == ["alpha", "beta"]
    assert snapshot["source_counts"] == {"reddit": 3}
    assert len(snapshot["items"]) == 3
    assert snapshot["source_errors"] == ["broken alpha", "broken beta"]


def test_build_sentiment_signal_snapshot_handles_no_sources(monkeypatch) -> None:
    monkeypatch.delenv("ETF_SENTIMENT_QUERIES", raising=False)
    assert build_sentiment_signal_snapshot(signal_sources=()) == {
        "queries": list(DEFAULT_SENTIMENT_QUERIES),
        "source_errors": [],
        "source_counts": {},
        "items": [],
    }


def test_etf_sentiment_helper_functions_cover_edge_cases() -> None:
    short_series = pd.Series([1.0])
    zero_baseline_series = pd.Series([0.0, 1.0])
    growing_series = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    flat_series = pd.Series([100.0] * 21)
    empty_series = pd.Series(dtype=float)

    assert _return_pct(short_series, periods=1) is None
    assert _return_pct(zero_baseline_series, periods=1) is None
    assert _return_pct(growing_series, periods=1) == 0.9615384615384581
    assert _drawdown_from_high_pct(empty_series, periods=10) is None
    assert _drawdown_from_high_pct(pd.Series([0.0]), periods=10) is None
    assert _drawdown_from_high_pct(growing_series, periods=10) == 0.0
    assert _annualized_volatility_pct(flat_series, periods=20) == 0.0
    assert _annualized_volatility_pct(pd.Series([100.0, 101.0]), periods=20) is None
    assert _average_metric([], "five_day_return_pct") is None
    assert _classify_market_mood(None, 1.0) == "neutral"
    assert _classify_market_mood(2.1, 4.1) == "optimistic"
    assert _classify_market_mood(-2.1, -4.1) == "fearful"
    assert _classify_market_mood(1.0, 1.0) == "constructive"
    assert _classify_market_mood(-1.0, 1.0) == "cautious"
    assert _classify_market_mood(0.1, 0.1) == "neutral"
    assert _dedupe_signals(
        [
            SentimentSignal("reddit", "subreddit:ETFs", "q", "a", "s", "https://example.com/1", "2026-01-01T00:00:00+00:00"),
            SentimentSignal("reddit", "subreddit:ETFs", "q", "b", "s", "https://example.com/1", "2026-01-02T00:00:00+00:00"),
        ]
    )[0].title == "a"
    assert _build_source_counts(
        [
            SentimentSignal("reddit", "subreddit:ETFs", "q", "a", "s", "https://example.com/1", "2026-01-01T00:00:00+00:00"),
            SentimentSignal("google_news_rss", "news", "q", "b", "s", "https://example.com/2", "2026-01-01T00:00:00+00:00"),
            SentimentSignal("reddit", "subreddit:ETFs", "q", "c", "s", "https://example.com/3", "2026-01-01T00:00:00+00:00"),
        ]
    ) == {"reddit": 2, "google_news_rss": 1}

    flags = _build_risk_flags(
        [
            ETFSnapshot("AI / Technology", "XLK", 1.0, 1.0, 2.0, 8.5, -2.0, 31.0),
            ETFSnapshot("Bonds", "BND", 1.0, 1.0, 2.0, 1.0, -5.0, 10.0),
        ]
    )
    assert flags == [
        "Potential crowding near highs in: AI / Technology",
        "Defensive assets are strengthening: Bonds",
        "Elevated 20d realized volatility in: AI / Technology",
    ]


def test_run_etf_sentiment_job_builds_and_executes(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeAgent:
        def generate_briefing(self, prompt: str, market_snapshot: dict[str, object]) -> str:
            calls.append((prompt, market_snapshot))
            return "ETF Sentiment Brief"

    monkeypatch.setattr("src.adapters.sentiment.runtime.load_etf_sentiment_prompt", lambda: "Prompt body")
    monkeypatch.setattr("src.adapters.sentiment.runtime.build_etf_market_snapshot", lambda: {"overview": {"market_mood": "neutral"}})
    monkeypatch.setattr("src.adapters.sentiment.runtime.build_etf_sentiment_agent_from_env", lambda: FakeAgent())

    assert run_etf_sentiment_job() == "ETF Sentiment Brief"
    assert calls == [("Prompt body", {"overview": {"market_mood": "neutral"}})]
