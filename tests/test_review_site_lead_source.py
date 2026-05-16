from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.adapters.social.public_search_lead_source import PublicSearchLeadSourceError
from src.adapters.social.review_site_lead_source import ReviewSiteLeadSource


def test_review_site_lead_source_filters_to_review_domains(monkeypatch) -> None:
    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        query = kwargs["params"]["q"]
        assert "site:g2.com" in query
        assert "site:capterra.com" in query
        assert "site:apps.shopify.com" in query
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            text=(
                '<html><body>'
                '<a class="result__a" href="https://www.g2.com/products/example/reviews">Review complaints</a>'
                '<div class="result__snippet">Users hate manual reconciliation and missing notes.</div>'
                "</body></html>"
            ),
        )

    monkeypatch.setattr("src.adapters.social.duckduckgo_site_search.httpx.get", fake_get)
    fixed_now = datetime(2026, 5, 16, tzinfo=UTC)
    source = ReviewSiteLeadSource()
    source.search.now = lambda: fixed_now  # type: ignore[method-assign]

    posts = source.search_recent_posts("crm workflow pain", 5)

    assert posts[0].source == "reviews"
    assert posts[0].permalink == "https://www.g2.com/products/example/reviews"
    assert posts[0].created_at == fixed_now


def test_review_site_lead_source_raises_on_http_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.social.duckduckgo_site_search.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("boom")),  # type: ignore[no-untyped-def]
    )

    try:
        ReviewSiteLeadSource().search_recent_posts("query", 5)
    except PublicSearchLeadSourceError as exc:
        assert str(exc) == "Unable to load review-site search results."
    else:
        raise AssertionError("Expected PublicSearchLeadSourceError")
