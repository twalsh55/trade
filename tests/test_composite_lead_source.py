from __future__ import annotations

from datetime import UTC, datetime

from src.adapters.social.composite_lead_source import CompositeLeadSource, CompositeLeadSourceError
from src.domain.prospecting import SocialPost


class StubSource:
    def __init__(self, posts: list[SocialPost]) -> None:
        self.posts = posts
        self.calls: list[tuple[str, int]] = []

    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        self.calls.append((search_term, limit))
        return self.posts


class FailingSource:
    def __init__(self, message: str) -> None:
        self.message = message
        self.calls: list[tuple[str, int]] = []

    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        self.calls.append((search_term, limit))
        raise RuntimeError(self.message)


def make_post(source: str, external_id: str, day: int) -> SocialPost:
    return SocialPost(
        source=source,
        external_id=external_id,
        title=f"title {external_id}",
        body="body",
        author="author",
        permalink=f"https://example.com/{external_id}",
        created_at=datetime(2026, 5, day, tzinfo=UTC),
    )


def test_composite_lead_source_combines_and_sorts() -> None:
    older = make_post("reddit", "1", 13)
    newer = make_post("hackernews", "2", 14)
    source_a = StubSource([older])
    source_b = StubSource([newer])

    posts = CompositeLeadSource((source_a, source_b)).search_recent_posts("query", 5)

    assert source_a.calls == [("query", 5)]
    assert source_b.calls == [("query", 5)]
    assert [post.external_id for post in posts] == ["2", "1"]


def test_composite_lead_source_continues_when_one_source_fails() -> None:
    failing = FailingSource("Unable to load Reddit search results.")
    source = StubSource([make_post("hackernews", "2", 14)])

    posts = CompositeLeadSource((failing, source)).search_recent_posts("query", 5)

    assert failing.calls == [("query", 5)]
    assert source.calls == [("query", 5)]
    assert [post.external_id for post in posts] == ["2"]


def test_composite_lead_source_raises_when_all_sources_fail() -> None:
    source_a = FailingSource("Unable to load Reddit search results.")
    source_b = FailingSource("Unable to load Hacker News search results.")

    try:
        CompositeLeadSource((source_a, source_b)).search_recent_posts("query", 5)
    except CompositeLeadSourceError as exc:
        assert str(exc) == "Unable to load Reddit search results.; Unable to load Hacker News search results."
    else:
        raise AssertionError("Expected CompositeLeadSourceError")
