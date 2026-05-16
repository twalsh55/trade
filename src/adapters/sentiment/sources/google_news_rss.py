from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

import httpx


@dataclass(frozen=True)
class SentimentSignal:
    source: str
    channel: str
    query: str
    title: str
    summary: str
    url: str
    published_at: str


class GoogleNewsRSSSourceError(RuntimeError):
    """Raised when Google News RSS sentiment requests fail."""


class GoogleNewsRSSSource:
    SEARCH_URL = "https://news.google.com/rss/search"

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    def collect_signals(self, query: str, limit: int) -> list[SentimentSignal]:
        try:
            response = httpx.get(
                self.SEARCH_URL,
                params={
                    "q": query,
                    "hl": "en-US",
                    "gl": "US",
                    "ceid": "US:en",
                },
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.text
        except httpx.HTTPError as exc:
            raise GoogleNewsRSSSourceError("Unable to load Google News RSS search results.") from exc

        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise GoogleNewsRSSSourceError("Google News RSS returned an invalid response.") from exc

        items = root.findall("./channel/item")
        results: list[SentimentSignal] = []
        for item in items[:limit]:
            title = _read_text(item, "title")
            link = _read_text(item, "link")
            if not title or not link:
                continue
            results.append(
                SentimentSignal(
                    source="google_news_rss",
                    channel="news",
                    query=query,
                    title=title,
                    summary=_read_text(item, "description"),
                    url=link,
                    published_at=_parse_pub_date(_read_text(item, "pubDate")),
                )
            )
        return results


def _read_text(item: ElementTree.Element, tag_name: str) -> str:
    node = item.find(tag_name)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _parse_pub_date(value: str) -> str:
    if not value:
        return datetime.fromtimestamp(0, tz=UTC).isoformat()
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return datetime.fromtimestamp(0, tz=UTC).isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()
