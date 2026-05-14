from __future__ import annotations

import httpx

from src.adapters.social.hacker_news_lead_source import HackerNewsLeadSource, HackerNewsLeadSourceError


def test_hacker_news_lead_source_parses_posts(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, *, params, timeout: float, follow_redirects: bool):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        captured["follow_redirects"] = follow_redirects
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "hits": [
                    {
                        "objectID": "123",
                        "title": "Portfolio risk tool ideas",
                        "story_text": "Looking for a dashboard for crash risk.",
                        "author": "alice",
                        "created_at_i": 1715683200,
                    }
                ]
            },
        )

    monkeypatch.setattr("src.adapters.social.hacker_news_lead_source.httpx.get", fake_get)

    posts = HackerNewsLeadSource().search_recent_posts("portfolio risk dashboard", 5)

    assert captured["url"] == "https://hn.algolia.com/api/v1/search_by_date"
    assert captured["params"]["query"] == "portfolio risk dashboard"
    assert captured["params"]["tags"] == "story"
    assert len(posts) == 1
    assert posts[0].source == "hackernews"
    assert posts[0].permalink == "https://news.ycombinator.com/item?id=123"


def test_hacker_news_lead_source_raises_on_http_error(monkeypatch) -> None:
    def fake_get(url: str, *, params, timeout: float, follow_redirects: bool):  # type: ignore[no-untyped-def]
        request = httpx.Request("GET", url)
        return httpx.Response(500, request=request)

    monkeypatch.setattr("src.adapters.social.hacker_news_lead_source.httpx.get", fake_get)

    try:
        HackerNewsLeadSource().search_recent_posts("query", 5)
    except HackerNewsLeadSourceError as exc:
        assert str(exc) == "Unable to load Hacker News search results."
    else:
        raise AssertionError("Expected HackerNewsLeadSourceError")


def test_hacker_news_lead_source_raises_on_invalid_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.social.hacker_news_lead_source.httpx.get",
        lambda *args, **kwargs: httpx.Response(200, request=httpx.Request("GET", "https://example.com"), json={"hits": {}}),  # type: ignore[no-untyped-def]
    )

    try:
        HackerNewsLeadSource().search_recent_posts("query", 5)
    except HackerNewsLeadSourceError as exc:
        assert str(exc) == "Hacker News returned an unexpected response."
    else:
        raise AssertionError("Expected HackerNewsLeadSourceError")


def test_hacker_news_lead_source_skips_invalid_items(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.social.hacker_news_lead_source.httpx.get",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("GET", "https://hn.algolia.com/api/v1/search_by_date"),
            json={
                "hits": [
                    123,
                    {"objectID": "bad"},
                    {
                        "objectID": "good",
                        "title": "Need a risk app",
                        "story_text": "help",
                        "author": "alice",
                        "created_at_i": "bad-timestamp",
                    },
                ]
            },
        ),  # type: ignore[no-untyped-def]
    )

    posts = HackerNewsLeadSource().search_recent_posts("query", 5)

    assert len(posts) == 1
    assert posts[0].external_id == "good"
    assert posts[0].created_at.year == 1970
