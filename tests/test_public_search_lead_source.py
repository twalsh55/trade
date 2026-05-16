from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.adapters.social.public_search_lead_source import PublicSearchLeadSource, PublicSearchLeadSourceError


def test_public_search_lead_source_parses_results(monkeypatch) -> None:
    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        assert url == "https://html.duckduckgo.com/html/"
        assert kwargs["params"]["q"] == "crm follow up"
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            text=(
                '<html><body>'
                '<a class="result__a" href="https://example.com/post">A useful workflow thread</a>'
                '<div class="result__snippet">Operators still track follow-ups manually.</div>'
                "</body></html>"
            ),
        )

    monkeypatch.setattr("src.adapters.social.duckduckgo_site_search.httpx.get", fake_get)
    fixed_now = datetime(2026, 5, 16, tzinfo=UTC)
    source = PublicSearchLeadSource(source_name="web", site_domains=(), user_agent="test-agent")
    source.search.now = lambda: fixed_now  # type: ignore[method-assign]

    posts = source.search_recent_posts("crm follow up", 5)

    assert posts[0].source == "web"
    assert posts[0].title == "A useful workflow thread"
    assert posts[0].body == "Operators still track follow-ups manually."
    assert posts[0].permalink == "https://example.com/post"
    assert posts[0].created_at == fixed_now


def test_public_search_lead_source_raises_on_http_error(monkeypatch) -> None:
    def failing_get(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("src.adapters.social.duckduckgo_site_search.httpx.get", failing_get)

    try:
        PublicSearchLeadSource(
            source_name="web",
            site_domains=(),
            user_agent="test-agent",
            failure_label="web search results",
        ).search_recent_posts("query", 5)
    except PublicSearchLeadSourceError as exc:
        assert str(exc) == "Unable to load web search results."
    else:
        raise AssertionError("Expected PublicSearchLeadSourceError")
