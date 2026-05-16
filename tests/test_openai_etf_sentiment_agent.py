from __future__ import annotations

import httpx

from src.adapters.llm.openai_etf_sentiment_agent import (
    OpenAIETFSentimentAgent,
    OpenAIETFSentimentAgentError,
    TemplateETFSentimentAgent,
    _extract_text_from_response,
    _format_crowding,
    _format_move,
    _format_pct,
    _format_text_signals,
)


def test_template_etf_sentiment_agent_builds_briefing() -> None:
    agent = TemplateETFSentimentAgent()

    briefing = agent.generate_briefing(
        prompt="ignored",
        market_snapshot={
            "overview": {
                "market_mood": "constructive",
                "average_five_day_return_pct": 1.25,
                "average_one_month_return_pct": 3.5,
            },
            "leaders": [{"label": "Semiconductors", "five_day_return_pct": 4.2}],
            "laggards": [{"label": "Bonds", "five_day_return_pct": -1.1}],
            "crowding_watch": [
                {
                    "label": "AI / Technology",
                    "one_month_return_pct": 9.0,
                    "drawdown_from_52_week_high_pct": -1.2,
                }
            ],
            "risk_flags": ["Potential crowding near highs in: AI / Technology"],
            "text_signals": {
                "source_counts": {"reddit": 2, "google_news_rss": 1},
                "items": [
                    {"title": "Tech ETF concentration debate grows"},
                    {"title": "Defensive rotation narrative is back"},
                ],
            },
        },
    )

    assert "ETF Sentiment Brief" in briefing
    assert "Semiconductors (+4.2%)" in briefing
    assert "Potential crowding near highs in: AI / Technology" in briefing
    assert "Text signals: google_news_rss=1, reddit=2." in briefing
    assert briefing.endswith("Not financial advice.")


def test_openai_etf_sentiment_agent_uses_api_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"output_text": "ETF Sentiment Brief\nNot financial advice."}

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, object], timeout: float):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("src.adapters.llm.openai_etf_sentiment_agent.httpx.post", fake_post)

    agent = OpenAIETFSentimentAgent(api_key="sk-test", model="gpt-5-nano", max_output_tokens=321)
    result = agent.generate_briefing(prompt="System prompt", market_snapshot={"overview": {"market_mood": "neutral"}})

    assert result == "ETF Sentiment Brief\nNot financial advice."
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"] == {"Authorization": "Bearer sk-test", "Content-Type": "application/json"}
    assert captured["json"] == {
        "model": "gpt-5-nano",
        "instructions": (
            "System prompt\n\nUse only the provided input snapshot. Do not imply you reviewed news, Reddit, flows, or social "
            "data unless that evidence is explicitly present in the input. Separate facts from interpretation. "
            "Write a concise Telegram-ready market briefing under 3500 characters using plain text and flat bullets. "
            "Include: overall market mood, strongest bullish themes, strongest bearish themes, crowding observations, "
            "key risks, probability-weighted scenarios, confidence, and the line 'Not financial advice.'"
        ),
        "input": '{"overview": {"market_mood": "neutral"}}',
        "max_output_tokens": 321,
        "store": False,
    }
    assert captured["timeout"] == 30.0


def test_openai_etf_sentiment_agent_supports_output_array_payload(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"output": [{"content": [{"text": "Line 1"}, {"text": "Line 2"}]}]}

    monkeypatch.setattr("src.adapters.llm.openai_etf_sentiment_agent.httpx.post", lambda *args, **kwargs: FakeResponse())

    agent = OpenAIETFSentimentAgent(api_key="sk-test")
    assert agent.generate_briefing(prompt="Prompt", market_snapshot={}) == "Line 1\nLine 2"


def test_openai_etf_sentiment_agent_raises_on_http_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("src.adapters.llm.openai_etf_sentiment_agent.httpx.post", fake_post)

    agent = OpenAIETFSentimentAgent(api_key="sk-test")
    try:
        agent.generate_briefing(prompt="Prompt", market_snapshot={})
    except OpenAIETFSentimentAgentError as exc:
        assert str(exc) == "Unable to generate ETF sentiment briefing."
    else:
        raise AssertionError("Expected OpenAIETFSentimentAgentError")


def test_openai_etf_sentiment_agent_raises_on_invalid_payload(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"output": "bad"}

    monkeypatch.setattr("src.adapters.llm.openai_etf_sentiment_agent.httpx.post", lambda *args, **kwargs: FakeResponse())

    agent = OpenAIETFSentimentAgent(api_key="sk-test")
    try:
        agent.generate_briefing(prompt="Prompt", market_snapshot={})
    except OpenAIETFSentimentAgentError as exc:
        assert str(exc) == "OpenAI returned an invalid ETF sentiment payload."
    else:
        raise AssertionError("Expected OpenAIETFSentimentAgentError")


def test_openai_etf_sentiment_agent_raises_on_empty_briefing(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"output_text": " "}

    monkeypatch.setattr("src.adapters.llm.openai_etf_sentiment_agent.httpx.post", lambda *args, **kwargs: FakeResponse())

    agent = OpenAIETFSentimentAgent(api_key="sk-test")
    try:
        agent.generate_briefing(prompt="Prompt", market_snapshot={})
    except OpenAIETFSentimentAgentError as exc:
        assert str(exc) == "OpenAI returned an invalid ETF sentiment payload."
    else:
        raise AssertionError("Expected OpenAIETFSentimentAgentError")


def test_etf_sentiment_format_helpers_cover_fallback_branches() -> None:
    assert _format_pct(None) == "n/a"
    assert _format_move("bad") == "n/a"
    assert _format_crowding("bad") == "n/a"
    assert _format_text_signals("bad") == "n/a"
    assert _format_text_signals({"items": []}) == "No recent discussion or news signals collected."
    assert _format_text_signals({"source_counts": {"reddit": 1}, "items": [{"title": "One"}]}) == "reddit=1. Top themes: One"
    assert _format_text_signals({"source_counts": "bad", "items": ["bad", {"title": " "} ]}) == "signals collected"
    assert _extract_text_from_response({"output": ["bad", {"content": "bad"}, {"content": ["bad", {"text": "A"}]}]}) == "A"
