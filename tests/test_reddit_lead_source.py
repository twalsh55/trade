from __future__ import annotations

import httpx

from src.adapters.social.reddit_lead_source import RedditLeadSource, RedditLeadSourceError


def test_reddit_lead_source_parses_posts(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, *, params, headers, timeout: float, follow_redirects: bool):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["follow_redirects"] = follow_redirects
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "id": "abc",
                                "title": "Need a crash alert tool",
                                "selftext": "What do you use?",
                                "author": "alice",
                                "permalink": "/r/test/comments/abc/post",
                                "created_utc": 1715683200,
                            }
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr("src.adapters.social.reddit_lead_source.httpx.get", fake_get)

    source = RedditLeadSource()
    posts = source.search_recent_posts("market crash alert tool", 5)

    assert captured["url"] == "https://www.reddit.com/search.json"
    assert captured["params"]["q"] == "market crash alert tool"
    assert captured["headers"] == {"User-Agent": "trade-prospecting-bot/0.1"}
    assert captured["follow_redirects"] is True
    assert len(posts) == 1
    assert posts[0].permalink == "https://www.reddit.com/r/test/comments/abc/post"


def test_reddit_lead_source_raises_on_http_error(monkeypatch) -> None:
    def fake_get(url: str, *, params, headers, timeout: float, follow_redirects: bool):  # type: ignore[no-untyped-def]
        request = httpx.Request("GET", url)
        return httpx.Response(500, request=request)

    monkeypatch.setattr("src.adapters.social.reddit_lead_source.httpx.get", fake_get)

    try:
        RedditLeadSource().search_recent_posts("query", 5)
    except RedditLeadSourceError as exc:
        assert str(exc) == "Unable to load Reddit search results."
    else:
        raise AssertionError("Expected RedditLeadSourceError")


def test_reddit_lead_source_raises_on_invalid_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.social.reddit_lead_source.httpx.get",
        lambda *args, **kwargs: httpx.Response(200, request=httpx.Request("GET", "https://example.com"), json={"data": {"children": {}}}),  # type: ignore[no-untyped-def]
    )

    try:
        RedditLeadSource().search_recent_posts("query", 5)
    except RedditLeadSourceError as exc:
        assert str(exc) == "Reddit returned an unexpected response."
    else:
        raise AssertionError("Expected RedditLeadSourceError")


def test_reddit_lead_source_skips_invalid_items(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.social.reddit_lead_source.httpx.get",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("GET", "https://www.reddit.com/search.json"),
            json={
                "data": {
                    "children": [
                        123,
                        {"data": "bad"},
                        {"data": {"id": "abc"}},
                        {
                            "data": {
                                "id": "good",
                                "title": "Need a risk app",
                                "selftext": "help",
                                "author": "alice",
                                "permalink": "/r/test/comments/good/post",
                                "created_utc": "bad-timestamp",
                            }
                        },
                    ]
                }
            },
        ),  # type: ignore[no-untyped-def]
    )

    posts = RedditLeadSource().search_recent_posts("query", 5)

    assert len(posts) == 1
    assert posts[0].external_id == "good"
    assert posts[0].created_at.year == 1970
