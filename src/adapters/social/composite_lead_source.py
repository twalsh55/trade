from __future__ import annotations

from src.application.ports import SocialLeadSourcePort
from src.domain.prospecting import SocialPost


class CompositeLeadSourceError(RuntimeError):
    """Raised when every configured lead source fails for a search."""


class CompositeLeadSource:
    def __init__(self, sources: tuple[SocialLeadSourcePort, ...]) -> None:
        self.sources = sources

    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        results: list[SocialPost] = []
        errors: list[str] = []
        for source in self.sources:
            try:
                results.extend(source.search_recent_posts(search_term, limit))
            except RuntimeError as exc:
                errors.append(str(exc))
        if errors and not results:
            raise CompositeLeadSourceError("; ".join(errors))
        return sorted(results, key=lambda post: post.created_at, reverse=True)
