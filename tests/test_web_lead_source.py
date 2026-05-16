from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.adapters.social.public_search_lead_source import PublicSearchLeadSourceError
from src.adapters.social.web_lead_source import WebLeadSource


def test_web_lead_source_runs_unscoped_query(monkeypatch) -> None:
    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["params"]["q"] == "crm spreadsheet pain"
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            text=(
                '<html><body>'
                '<a class="result__a" href="https://example.com/blog/crm-pain">CRM pain roundup</a>'
                '<div class="result__snippet">Teams still use email and spreadsheets for follow-up.</div>'
                "</body></html>"
            ),
        )

    monkeypatch.setattr("src.adapters.social.duckduckgo_site_search.httpx.get", fake_get)
    fixed_now = datetime(2026, 5, 16, tzinfo=UTC)
    source = WebLeadSource()
    source.search.now = lambda: fixed_now  # type: ignore[method-assign]

    posts = source.search_recent_posts("crm spreadsheet pain", 5)

    assert posts[0].source == "web"
    assert posts[0].permalink == "https://example.com/blog/crm-pain"
    assert posts[0].created_at == fixed_now


def test_web_lead_source_raises_on_http_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.social.duckduckgo_site_search.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("boom")),  # type: ignore[no-untyped-def]
    )

    try:
        WebLeadSource().search_recent_posts("query", 5)
    except PublicSearchLeadSourceError as exc:
        assert str(exc) == "Unable to load web search results."
    else:
        raise AssertionError("Expected PublicSearchLeadSourceError")
