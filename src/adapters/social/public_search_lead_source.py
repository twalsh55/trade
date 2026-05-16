from __future__ import annotations

from src.adapters.social.duckduckgo_site_search import DuckDuckGoSiteSearch, DuckDuckGoSiteSearchError
from src.domain.prospecting import SocialPost


class PublicSearchLeadSourceError(RuntimeError):
    """Raised when a public-search lead source fails."""


class PublicSearchLeadSource:
    def __init__(
        self,
        source_name: str,
        user_agent: str,
        timeout_seconds: float = 20.0,
        site_domains: tuple[str, ...] = (),
        author_label: str = "unknown",
        failure_label: str = "public search results",
    ) -> None:
        self.source_name = source_name
        self.author_label = author_label
        self.failure_label = failure_label
        self.search = DuckDuckGoSiteSearch(
            site_domains=site_domains,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
        )

    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        try:
            results = self.search.search(search_term, limit)
        except DuckDuckGoSiteSearchError as exc:
            raise PublicSearchLeadSourceError(f"Unable to load {self.failure_label}.") from exc

        return [
            SocialPost(
                source=self.source_name,
                external_id=result.url,
                title=result.title,
                body=result.snippet,
                author=self.author_label,
                permalink=result.url,
                created_at=result.published_at,
            )
            for result in results
        ]
