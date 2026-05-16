from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.adapters.social.indie_hackers_lead_source import IndieHackersLeadSource
from src.adapters.social.public_search_lead_source import PublicSearchLeadSourceError


def test_indie_hackers_lead_source_filters_to_indie_hackers(monkeypatch) -> None:
    def fake_get(url: str, **kwargs):  # type: ignore[no-untyped-def]
        assert "site:indiehackers.com" in kwargs["params"]["q"]
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            text=(
                '<html><body>'
                '<a class="result__a" href="https://www.indiehackers.com/post/crm-notes-workflow">Indie Hackers CRM notes</a>'
                '<div class="result__snippet">Still using spreadsheets for CRM follow-up.</div>'
                "</body></html>"
            ),
        )

    monkeypatch.setattr("src.adapters.social.duckduckgo_site_search.httpx.get", fake_get)
    fixed_now = datetime(2026, 5, 16, tzinfo=UTC)
    source = IndieHackersLeadSource()
    source.search.now = lambda: fixed_now  # type: ignore[method-assign]

    posts = source.search_recent_posts("crm notes", 5)

    assert posts[0].source == "indie_hackers"
    assert posts[0].permalink == "https://www.indiehackers.com/post/crm-notes-workflow"
    assert posts[0].created_at == fixed_now


def test_indie_hackers_lead_source_raises_on_http_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.social.duckduckgo_site_search.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("boom")),  # type: ignore[no-untyped-def]
    )

    try:
        IndieHackersLeadSource().search_recent_posts("query", 5)
    except PublicSearchLeadSourceError as exc:
        assert str(exc) == "Unable to load Indie Hackers search results."
    else:
        raise AssertionError("Expected PublicSearchLeadSourceError")
