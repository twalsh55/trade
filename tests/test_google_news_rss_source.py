from __future__ import annotations

import httpx

from src.adapters.sentiment.sources.google_news_rss import GoogleNewsRSSSource, GoogleNewsRSSSourceError


def test_google_news_rss_source_parses_items(monkeypatch) -> None:
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
            text=(
                "<rss><channel>"
                "<item><title>ETF mood improves</title><link>https://example.com/1</link>"
                "<description>Risk appetite rose</description><pubDate>Wed, 15 May 2026 10:00:00 GMT</pubDate></item>"
                "<item><title></title><link>https://example.com/2</link></item>"
                "</channel></rss>"
            ),
        )

    monkeypatch.setattr("src.adapters.sentiment.sources.google_news_rss.httpx.get", fake_get)

    signals = GoogleNewsRSSSource().collect_signals("ETF market sentiment", 5)

    assert captured["url"] == "https://news.google.com/rss/search"
    assert captured["params"]["q"] == "ETF market sentiment"
    assert captured["follow_redirects"] is True
    assert len(signals) == 1
    assert signals[0].title == "ETF mood improves"
    assert signals[0].source == "google_news_rss"
    assert signals[0].published_at == "2026-05-15T10:00:00+00:00"

    monkeypatch.setattr(
        "src.adapters.sentiment.sources.google_news_rss.httpx.get",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com"),
            text=(
                "<rss><channel>"
                "<item><title>No tz</title><link>https://example.com/3</link><pubDate>Wed, 15 May 2026 10:00:00</pubDate></item>"
                "<item><title>Missing date</title><link>https://example.com/4</link></item>"
                "</channel></rss>"
            ),
        ),  # type: ignore[no-untyped-def]
    )
    signals = GoogleNewsRSSSource().collect_signals("ETF market sentiment", 5)
    assert signals[0].published_at == "2026-05-15T10:00:00+00:00"
    assert signals[1].published_at == "1970-01-01T00:00:00+00:00"


def test_google_news_rss_source_raises_on_http_and_parse_errors(monkeypatch) -> None:
    def failing_get(url: str, *, params, timeout: float, follow_redirects: bool):  # type: ignore[no-untyped-def]
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("src.adapters.sentiment.sources.google_news_rss.httpx.get", failing_get)

    try:
        GoogleNewsRSSSource().collect_signals("query", 5)
    except GoogleNewsRSSSourceError as exc:
        assert str(exc) == "Unable to load Google News RSS search results."
    else:
        raise AssertionError("Expected GoogleNewsRSSSourceError")

    monkeypatch.setattr(
        "src.adapters.sentiment.sources.google_news_rss.httpx.get",
        lambda *args, **kwargs: httpx.Response(200, request=httpx.Request("GET", "https://example.com"), text="<rss>"),  # type: ignore[no-untyped-def]
    )
    try:
        GoogleNewsRSSSource().collect_signals("query", 5)
    except GoogleNewsRSSSourceError as exc:
        assert str(exc) == "Google News RSS returned an invalid response."
    else:
        raise AssertionError("Expected GoogleNewsRSSSourceError")


def test_google_news_rss_source_handles_invalid_pubdate_parser(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.sentiment.sources.google_news_rss.httpx.get",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com"),
            text=(
                "<rss><channel>"
                "<item><title>ETF mood improves</title><link>https://example.com/1</link>"
                "<pubDate>Wed, 15 May 2026 10:00:00 GMT</pubDate></item>"
                "</channel></rss>"
            ),
        ),  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        "src.adapters.sentiment.sources.google_news_rss.parsedate_to_datetime",
        lambda value: (_ for _ in ()).throw(ValueError("bad")),
    )

    signals = GoogleNewsRSSSource().collect_signals("ETF market sentiment", 5)

    assert signals[0].published_at == "1970-01-01T00:00:00+00:00"
