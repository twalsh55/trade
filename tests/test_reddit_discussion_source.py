from __future__ import annotations

import httpx

from src.adapters.sentiment.sources.reddit_discussion import RedditDiscussionSource, RedditDiscussionSourceError


def test_reddit_discussion_source_parses_posts(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, *, params, headers, timeout: float, follow_redirects: bool):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "ETF investors getting optimistic?",
                                "selftext": "Seeing more talk about tech concentration.",
                                "permalink": "/r/ETFs/comments/abc/post",
                                "subreddit": "ETFs",
                                "created_utc": 1770000000,
                            }
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr("src.adapters.sentiment.sources.reddit_discussion.httpx.get", fake_get)

    signals = RedditDiscussionSource().collect_signals("Nasdaq 100 ETF", 5)

    assert captured["url"] == "https://www.reddit.com/search.json"
    assert captured["params"]["t"] == "week"
    assert captured["headers"] == {"User-Agent": "brivoly-etf-sentiment-bot/0.1"}
    assert len(signals) == 1
    assert signals[0].channel == "subreddit:ETFs"
    assert signals[0].url == "https://www.reddit.com/r/ETFs/comments/abc/post"
    assert signals[0].published_at.startswith("2026-")


def test_reddit_discussion_source_raises_on_http_and_shape_errors(monkeypatch) -> None:
    def fake_get(url: str, *, params, headers, timeout: float, follow_redirects: bool):  # type: ignore[no-untyped-def]
        request = httpx.Request("GET", url)
        return httpx.Response(500, request=request)

    monkeypatch.setattr("src.adapters.sentiment.sources.reddit_discussion.httpx.get", fake_get)

    try:
        RedditDiscussionSource().collect_signals("query", 5)
    except RedditDiscussionSourceError as exc:
        assert str(exc) == "Unable to load Reddit ETF discussion results."
    else:
        raise AssertionError("Expected RedditDiscussionSourceError")

    monkeypatch.setattr(
        "src.adapters.sentiment.sources.reddit_discussion.httpx.get",
        lambda *args, **kwargs: httpx.Response(200, request=httpx.Request("GET", "https://example.com"), json={"data": {"children": {}}}),  # type: ignore[no-untyped-def]
    )
    try:
        RedditDiscussionSource().collect_signals("query", 5)
    except RedditDiscussionSourceError as exc:
        assert str(exc) == "Reddit returned an unexpected ETF discussion response."
    else:
        raise AssertionError("Expected RedditDiscussionSourceError")


def test_reddit_discussion_source_skips_invalid_items(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.sentiment.sources.reddit_discussion.httpx.get",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com"),
            json={
                "data": {
                    "children": [
                        1,
                        {"data": "bad"},
                        {"data": {"title": "Missing permalink"}},
                        {
                            "data": {
                                "title": "Good",
                                "permalink": "/r/test/comments/1",
                                "subreddit": "test",
                                "created_utc": "bad",
                            }
                        },
                    ]
                }
            },
        ),  # type: ignore[no-untyped-def]
    )

    signals = RedditDiscussionSource().collect_signals("query", 5)

    assert len(signals) == 1
    assert signals[0].published_at == "1970-01-01T00:00:00+00:00"
