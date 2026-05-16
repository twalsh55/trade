from __future__ import annotations

import httpx
import pytest

from src.adapters.llm.openai_crm_image_intake import OpenAICRMImageIntakeAgent, OpenAICRMImageIntakeError


def test_openai_crm_image_intake_uses_api_and_returns_csv(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, *, headers, json, timeout: float):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "output_text": '{"rows":[{"lead_name":"Taylor Brooks","company_name":"Beacon Ridge","owner_name":"Samir Patel","stage":"Discovery","next_follow_up_at":"2024-05-09","notes":"From note image","priority":"high","contact_channel":"image","next_step":"Follow up"}]}'
            },
        )

    monkeypatch.setattr("src.adapters.llm.openai_crm_image_intake.httpx.post", fake_post)

    csv_content = OpenAICRMImageIntakeAgent(api_key="secret").extract_spreadsheet_rows_from_image(
        prompt="Focus on owner and next follow-up.",
        preferred_formats=["spreadsheet_screenshot"],
        file_name="note.png",
        file_bytes=b"image-bytes",
    )

    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["model"] == "gpt-4.1-mini"
    assert "Taylor Brooks" in csv_content
    assert "Beacon Ridge" in csv_content


def test_openai_crm_image_intake_rejects_unsupported_images_and_bad_payloads(monkeypatch) -> None:
    agent = OpenAICRMImageIntakeAgent(api_key="secret")

    with pytest.raises(OpenAICRMImageIntakeError, match="supported image file"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.gif", b"image")

    with pytest.raises(OpenAICRMImageIntakeError, match="Image file content is required"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.png", b"")

    monkeypatch.setattr(
        "src.adapters.llm.openai_crm_image_intake.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": "not-json"},
        ),  # type: ignore[no-untyped-def]
    )
    with pytest.raises(OpenAICRMImageIntakeError, match="invalid payload"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.png", b"image")

    monkeypatch.setattr(
        "src.adapters.llm.openai_crm_image_intake.httpx.post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": '{"rows":[]}'},
        ),  # type: ignore[no-untyped-def]
    )
    with pytest.raises(OpenAICRMImageIntakeError, match="No CRM-relevant notes"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.png", b"image")

    monkeypatch.setattr(
        "src.adapters.llm.openai_crm_image_intake.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("boom")),  # type: ignore[no-untyped-def]
    )
    with pytest.raises(OpenAICRMImageIntakeError, match="Unable to read this note image with AI right now"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.png", b"image")


def test_openai_crm_image_intake_supports_multiple_extensions_and_response_shapes(monkeypatch) -> None:
    responses = iter(
        [
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={
                    "output": [
                        {
                            "content": [
                                {"text": '{"rows":[{"lead_name":"Taylor Brooks","company_name":"Beacon Ridge","owner_name":null,"stage":"Discovery","next_follow_up_at":"2024-05-09","notes":"From webp","priority":3,"contact_channel":"image","next_step":"Follow up"}]}'}
                            ]
                        }
                    ]
                },
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output": "bad"},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output": [{}]},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output": ["bad", {"content": "bad"}, {"content": ["bad", {"no_text": "x"}]}]},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"rows":"bad"}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"rows":[123]}'},
            ),
        ]
    )

    monkeypatch.setattr("src.adapters.llm.openai_crm_image_intake.httpx.post", lambda *args, **kwargs: next(responses))
    agent = OpenAICRMImageIntakeAgent(api_key="secret")

    csv_content = agent.extract_spreadsheet_rows_from_image("prompt", [], "note.webp", b"image")
    assert "From webp" in csv_content

    with pytest.raises(OpenAICRMImageIntakeError, match="invalid payload"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.jpg", b"image")

    with pytest.raises(OpenAICRMImageIntakeError, match="invalid payload"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.jpeg", b"image")

    with pytest.raises(OpenAICRMImageIntakeError, match="invalid payload"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.jpg", b"image")

    with pytest.raises(OpenAICRMImageIntakeError, match="invalid payload"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.jpg", b"image")

    with pytest.raises(OpenAICRMImageIntakeError, match="No CRM-relevant notes"):
        agent.extract_spreadsheet_rows_from_image("prompt", [], "note.jpg", b"image")
