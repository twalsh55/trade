from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.adapters.llm.openai_prospect_drafter import (
    OpenAIProspectDrafter,
    OpenAIProspectDrafterError,
    TemplateProspectDrafter,
    _extract_text_from_response,
)
from src.domain.prospecting import ProspectMatch, SocialPost


def build_match(external_id: str) -> ProspectMatch:
    post = SocialPost(
        source="reddit",
        external_id=external_id,
        title="Looking for a crash dashboard?",
        body="I need a tool for monitoring portfolio risk.",
        author="alice",
        permalink="https://example.com/post",
        created_at=datetime(2026, 5, 14, tzinfo=UTC),
    )
    return ProspectMatch(post=post, matched_query="query", score=12, reasons=("mentions crash",))


def test_template_prospect_drafter_builds_reply() -> None:
    drafter = TemplateProspectDrafter()
    replies = drafter.draft_promotional_replies("summary", (build_match("1"),), "https://www.brivoly.com")
    assert "Potential SaaS idea:" in replies[0]
    assert "https://www.brivoly.com" in replies[0]
    assert drafter.get_last_usage() is None


def test_openai_prospect_drafter_uses_api_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, *, headers, json, timeout: float):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 30,
                    "total_tokens": 150,
                },
                "output": [
                    {
                        "content": [
                            {
                                "text": '{"drafts":[{"post_id":"1","idea":"Helpful idea"}]}'
                            }
                        ]
                    }
                ]
            },
        )

    monkeypatch.setattr("src.adapters.llm.openai_prospect_drafter.httpx.post", fake_post)

    replies = OpenAIProspectDrafter(api_key="secret").draft_promotional_replies(
        "summary",
        (build_match("1"),),
        "https://www.brivoly.com",
    )

    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["model"] == "gpt-5-nano"
    assert "opportunity discovery" in captured["json"]["instructions"]
    assert replies == ["Helpful idea"]


def test_openai_prospect_drafter_tracks_last_usage(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.llm.openai_prospect_drafter.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={
                "usage": {"input_tokens": 90, "output_tokens": 10, "total_tokens": 100},
                "output_text": '{"drafts":[{"post_id":"1","idea":"Helpful idea"}]}',
            },
        ),  # type: ignore[no-untyped-def]
    )

    drafter = OpenAIProspectDrafter(api_key="secret")
    replies = drafter.draft_promotional_replies("summary", (build_match("1"),), None)

    assert replies == ["Helpful idea"]
    usage = drafter.get_last_usage()
    assert usage is not None
    assert usage.total_tokens == 100
    assert usage.model == "gpt-5-nano"


def test_openai_prospect_drafter_ignores_invalid_usage_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.llm.openai_prospect_drafter.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={
                "usage": {"input_tokens": "bad", "output_tokens": 10, "total_tokens": 100},
                "output_text": '{"drafts":[{"post_id":"1","idea":"Helpful idea"}]}',
            },
        ),  # type: ignore[no-untyped-def]
    )

    drafter = OpenAIProspectDrafter(api_key="secret")
    replies = drafter.draft_promotional_replies("summary", (build_match("1"),), None)

    assert replies == ["Helpful idea"]
    assert drafter.get_last_usage() is None


def test_openai_prospect_drafter_falls_back_when_post_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.llm.openai_prospect_drafter.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": '{"drafts":[]}'},
        ),  # type: ignore[no-untyped-def]
    )

    replies = OpenAIProspectDrafter(api_key="secret").draft_promotional_replies("summary", (build_match("1"),), None)

    assert "Potential SaaS idea:" in replies[0]


def test_openai_prospect_drafter_returns_empty_list_when_no_matches() -> None:
    replies = OpenAIProspectDrafter(api_key="secret").draft_promotional_replies("summary", (), None)
    assert replies == []


def test_openai_prospect_drafter_raises_on_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.llm.openai_prospect_drafter.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": "not-json"},
        ),  # type: ignore[no-untyped-def]
    )

    try:
        OpenAIProspectDrafter(api_key="secret").draft_promotional_replies("summary", (build_match("1"),), None)
    except OpenAIProspectDrafterError as exc:
        assert str(exc) == "OpenAI returned an invalid drafting payload."
    else:
        raise AssertionError("Expected OpenAIProspectDrafterError")


def test_openai_prospect_drafter_raises_on_http_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("src.adapters.llm.openai_prospect_drafter.httpx.post", fake_post)

    try:
        OpenAIProspectDrafter(api_key="secret").draft_promotional_replies("summary", (build_match("1"),), None)
    except OpenAIProspectDrafterError as exc:
        assert str(exc) == "Unable to generate opportunity ideas."
    else:
        raise AssertionError("Expected OpenAIProspectDrafterError")


def test_openai_prospect_drafter_raises_on_non_list_drafts(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.llm.openai_prospect_drafter.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": '{"drafts":{}}'},
        ),  # type: ignore[no-untyped-def]
    )

    try:
        OpenAIProspectDrafter(api_key="secret").draft_promotional_replies("summary", (build_match("1"),), None)
    except OpenAIProspectDrafterError as exc:
        assert str(exc) == "OpenAI returned an invalid drafting payload."
    else:
        raise AssertionError("Expected OpenAIProspectDrafterError")


def test_openai_prospect_drafter_ignores_invalid_draft_items(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.llm.openai_prospect_drafter.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": '{"drafts":["bad", {"post_id":"1","idea":"Helpful idea"}]}'},
        ),  # type: ignore[no-untyped-def]
    )

    replies = OpenAIProspectDrafter(api_key="secret").draft_promotional_replies("summary", (build_match("1"),), None)

    assert replies == ["Helpful idea"]


def test_openai_prospect_drafter_accepts_legacy_reply_field(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.llm.openai_prospect_drafter.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": '{"drafts":[{"post_id":"1","reply":"Legacy reply field"}]}'},
        ),  # type: ignore[no-untyped-def]
    )

    replies = OpenAIProspectDrafter(api_key="secret").draft_promotional_replies("summary", (build_match("1"),), None)

    assert replies == ["Legacy reply field"]


def test_extract_text_from_response_rejects_invalid_shapes() -> None:
    invalid_payloads = (
        {"output": {}},
        {"output": [123]},
        {"output": [{"content": "bad"}]},
        {"output": [{"content": [123]}]},
        {"output": [{"content": [{"text": "   "}]}]},
    )

    for payload in invalid_payloads:
        try:
            _extract_text_from_response(payload)
        except OpenAIProspectDrafterError as exc:
            assert str(exc) == "OpenAI returned an invalid drafting payload."
        else:
            raise AssertionError("Expected OpenAIProspectDrafterError")
