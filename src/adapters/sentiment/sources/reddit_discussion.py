from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.adapters.sentiment.sources.google_news_rss import SentimentSignal


class RedditDiscussionSourceError(RuntimeError):
    """Raised when Reddit ETF discussion requests fail."""


class RedditDiscussionSource:
    SEARCH_URL = "https://www.reddit.com/search.json"

    def __init__(self, user_agent: str = "brivoly-etf-sentiment-bot/0.1", timeout_seconds: float = 20.0) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def collect_signals(self, query: str, limit: int) -> list[SentimentSignal]:
        try:
            response = httpx.get(
                self.SEARCH_URL,
                params={
                    "q": query,
                    "sort": "new",
                    "t": "week",
                    "limit": limit,
                    "raw_json": "1",
                },
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RedditDiscussionSourceError("Unable to load Reddit ETF discussion results.") from exc

        posts = payload.get("data", {}).get("children", [])
        if not isinstance(posts, list):
            raise RedditDiscussionSourceError("Reddit returned an unexpected ETF discussion response.")

        results: list[SentimentSignal] = []
        for item in posts:
            data = item.get("data", {}) if isinstance(item, dict) else {}
            if not isinstance(data, dict):
                continue
            title = data.get("title")
            permalink = data.get("permalink")
            if not isinstance(title, str) or not isinstance(permalink, str):
                continue
            subreddit = data.get("subreddit", "reddit")
            created_utc = data.get("created_utc", 0)
            if not isinstance(created_utc, (int, float)):
                created_utc = 0
            results.append(
                SentimentSignal(
                    source="reddit",
                    channel=f"subreddit:{subreddit}",
                    query=query,
                    title=title.strip(),
                    summary=str(data.get("selftext", "")).strip(),
                    url=f"https://www.reddit.com{permalink}",
                    published_at=datetime.fromtimestamp(created_utc, tz=UTC).isoformat(),
                )
            )
        return results
