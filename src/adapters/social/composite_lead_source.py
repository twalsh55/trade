from __future__ import annotations

from src.application.ports import SocialLeadSourcePort
from src.domain.prospecting import SocialPost


class CompositeLeadSource:
    def __init__(self, sources: tuple[SocialLeadSourcePort, ...]) -> None:
        self.sources = sources

    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        results: list[SocialPost] = []
        for source in self.sources:
            results.extend(source.search_recent_posts(search_term, limit))
        return sorted(results, key=lambda post: post.created_at, reverse=True)
