from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.domain.prospecting import SocialPost


class HackerNewsLeadSourceError(RuntimeError):
    """Raised when Hacker News prospecting requests fail."""


class HackerNewsLeadSource:
    SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        try:
            response = httpx.get(
                self.SEARCH_URL,
                params={
                    "query": search_term,
                    "tags": "story",
                    "hitsPerPage": limit,
                },
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HackerNewsLeadSourceError("Unable to load Hacker News search results.") from exc

        hits = payload.get("hits", [])
        if not isinstance(hits, list):
            raise HackerNewsLeadSourceError("Hacker News returned an unexpected response.")

        results: list[SocialPost] = []
        for item in hits:
            if not isinstance(item, dict):
                continue

            external_id = item.get("objectID")
            title = item.get("title")
            if not isinstance(external_id, str) or not isinstance(title, str):
                continue

            created_at_i = item.get("created_at_i", 0)
            if not isinstance(created_at_i, (int, float)):
                created_at_i = 0

            results.append(
                SocialPost(
                    source="hackernews",
                    external_id=external_id,
                    title=title.strip(),
                    body=str(item.get("story_text", "") or "").strip(),
                    author=str(item.get("author", "unknown")),
                    permalink=f"https://news.ycombinator.com/item?id={external_id}",
                    created_at=datetime.fromtimestamp(created_at_i, tz=UTC),
                )
            )

        return results
