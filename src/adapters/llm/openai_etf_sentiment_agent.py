from __future__ import annotations

import json
from typing import Any

import httpx


class OpenAIETFSentimentAgentError(RuntimeError):
    """Raised when ETF sentiment briefing generation fails."""


class OpenAIETFSentimentAgent:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5-nano",
        timeout_seconds: float = 30.0,
        max_output_tokens: int = 900,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    def generate_briefing(self, prompt: str, market_snapshot: dict[str, Any]) -> str:
        instructions = (
            f"{prompt}\n\n"
            "Use only the provided input snapshot. Do not imply you reviewed news, Reddit, flows, or social data unless "
            "that evidence is explicitly present in the input. Separate facts from interpretation. "
            "Write a concise Telegram-ready market briefing under 3500 characters using plain text and flat bullets. "
            "Include: overall market mood, strongest bullish themes, strongest bearish themes, crowding observations, "
            "key risks, probability-weighted scenarios, confidence, and the line 'Not financial advice.'"
        )

        try:
            response = httpx.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "instructions": instructions,
                    "input": json.dumps(market_snapshot),
                    "max_output_tokens": self.max_output_tokens,
                    "store": False,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenAIETFSentimentAgentError("Unable to generate ETF sentiment briefing.") from exc

        return _extract_text_from_response(payload).strip()


class TemplateETFSentimentAgent:
    def generate_briefing(self, prompt: str, market_snapshot: dict[str, Any]) -> str:
        _ = prompt
        overview = market_snapshot.get("overview", {})
        text_signals = market_snapshot.get("text_signals", {})
        leaders = market_snapshot.get("leaders", [])
        laggards = market_snapshot.get("laggards", [])
        crowding = market_snapshot.get("crowding_watch", [])
        risk_flags = market_snapshot.get("risk_flags", [])

        mood = str(overview.get("market_mood", "neutral"))
        average_five_day = _format_pct(overview.get("average_five_day_return_pct"))
        average_one_month = _format_pct(overview.get("average_one_month_return_pct"))
        leadership_line = ", ".join(_format_move(item) for item in leaders[:3]) or "No clear short-term leaders."
        weakness_line = ", ".join(_format_move(item) for item in laggards[:3]) or "No clear short-term laggards."
        crowding_line = ", ".join(_format_crowding(item) for item in crowding[:3]) or "No crowding extremes detected from price action alone."
        risk_line = "; ".join(str(item) for item in risk_flags[:3]) or "No major price-based risk flags detected."
        text_signal_line = _format_text_signals(text_signals)

        return (
            "ETF Sentiment Brief\n"
            f"What changed:\n"
            f"- 5d leadership: {leadership_line}\n"
            f"- 5d weakness: {weakness_line}\n"
            "Facts:\n"
            f"- Market mood: {mood}\n"
            f"- Average 5d return across tracked ETFs: {average_five_day}\n"
            f"- Average 1m return across tracked ETFs: {average_one_month}\n"
            f"- Crowding watch: {crowding_line}\n"
            f"- Text signals: {text_signal_line}\n"
            "Interpretation:\n"
            "- This template mode uses simple text harvesting plus price behavior, so narrative inference is still lower-confidence than a fully modeled sentiment stack.\n"
            f"- Key risks: {risk_line}\n"
            "Scenarios:\n"
            "- Base case: trend persistence remains possible if leadership stays broad and volatility contained.\n"
            "- Risk case: crowded winners become fragile if momentum cools while defensive assets stabilize.\n"
            "Confidence: Low-Medium\n"
            "Not financial advice."
        )


def _extract_text_from_response(payload: dict[str, object]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = payload.get("output", [])
    if not isinstance(output, list):
        raise OpenAIETFSentimentAgentError("OpenAI returned an invalid ETF sentiment payload.")

    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                parts.append(text)

    content = "\n".join(part.strip() for part in parts if part.strip()).strip()
    if not content:
        raise OpenAIETFSentimentAgentError("OpenAI returned an invalid ETF sentiment payload.")
    return content


def _format_pct(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:+.1f}%"
    return "n/a"


def _format_move(item: object) -> str:
    if not isinstance(item, dict):
        return "n/a"
    label = str(item.get("label", item.get("ticker", "unknown")))
    move = _format_pct(item.get("five_day_return_pct"))
    return f"{label} ({move})"


def _format_crowding(item: object) -> str:
    if not isinstance(item, dict):
        return "n/a"
    label = str(item.get("label", item.get("ticker", "unknown")))
    drawdown = _format_pct(item.get("drawdown_from_52_week_high_pct"))
    monthly = _format_pct(item.get("one_month_return_pct"))
    return f"{label} 1m {monthly}, drawdown {drawdown}"


def _format_text_signals(value: object) -> str:
    if not isinstance(value, dict):
        return "n/a"
    items = value.get("items", [])
    if not isinstance(items, list) or not items:
        return "No recent discussion or news signals collected."
    source_counts = value.get("source_counts", {})
    if not isinstance(source_counts, dict):
        source_counts = {}
    counts_line = ", ".join(f"{key}={count}" for key, count in sorted(source_counts.items())) or "signals collected"
    top_titles: list[str] = []
    for item in items[:2]:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if isinstance(title, str) and title.strip():
            top_titles.append(title.strip())
    title_line = " | ".join(top_titles)
    return f"{counts_line}. Top themes: {title_line}" if title_line else counts_line
