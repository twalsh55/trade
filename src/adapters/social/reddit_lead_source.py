from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.domain.prospecting import SocialPost


class RedditLeadSourceError(RuntimeError):
    """Raised when Reddit prospecting requests fail."""


class RedditLeadSource:
    SEARCH_URL = "https://www.reddit.com/search.json"

    def __init__(self, user_agent: str = "trade-prospecting-bot/0.1", timeout_seconds: float = 20.0) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        try:
            response = httpx.get(
                self.SEARCH_URL,
                params={
                    "q": search_term,
                    "sort": "new",
                    "t": "day",
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
            raise RedditLeadSourceError("Unable to load Reddit search results.") from exc

        posts = payload.get("data", {}).get("children", [])
        if not isinstance(posts, list):
            raise RedditLeadSourceError("Reddit returned an unexpected response.")

        results: list[SocialPost] = []
        for item in posts:
            data = item.get("data", {}) if isinstance(item, dict) else {}
            if not isinstance(data, dict):
                continue

            permalink = data.get("permalink")
            external_id = data.get("id")
            title = data.get("title")
            if not isinstance(permalink, str) or not isinstance(external_id, str) or not isinstance(title, str):
                continue

            created_utc = data.get("created_utc", 0)
            if not isinstance(created_utc, (int, float)):
                created_utc = 0

            results.append(
                SocialPost(
                    source="reddit",
                    external_id=external_id,
                    title=title.strip(),
                    body=str(data.get("selftext", "")).strip(),
                    author=str(data.get("author", "unknown")),
                    permalink=f"https://www.reddit.com{permalink}",
                    created_at=datetime.fromtimestamp(created_utc, tz=UTC),
                )
            )

        return results
