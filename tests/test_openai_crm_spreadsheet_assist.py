from __future__ import annotations

import httpx
import pytest

from src.adapters.llm.openai_crm_spreadsheet_assist import (
    OpenAICRMSpreadsheetAssistAgent,
    OpenAICRMSpreadsheetAssistError,
    _extract_text_from_response,
    _parse_clarification,
)


def test_openai_crm_spreadsheet_assist_uses_api_and_returns_mapping(monkeypatch) -> None:
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
                "output_text": '{"field_mapping":{"Person":"lead_name","Organisation":"company_name","Followup":"next_follow_up_at","Context":"notes"}}'
            },
        )

    monkeypatch.setattr("src.adapters.llm.openai_crm_spreadsheet_assist.httpx.post", fake_post)

    mapping, clarification = OpenAICRMSpreadsheetAssistAgent(api_key="secret").suggest_field_mapping(
        prompt="Focus on owner and next follow-up.",
        preferred_formats=["csv"],
        source_label="CSV upload",
        headers=["Person", "Organisation", "Followup", "Context"],
        sample_rows=[{"Person": "Taylor Brooks", "Organisation": "Beacon Ridge", "Followup": "2024-05-09", "Context": "Imported"}],
    )

    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["model"] == "gpt-4.1-mini"
    assert mapping["Person"] == "lead_name"
    assert mapping["Context"] == "notes"
    assert clarification is None


def test_openai_crm_spreadsheet_assist_rejects_missing_headers_and_transport_failures(monkeypatch) -> None:
    agent = OpenAICRMSpreadsheetAssistAgent(api_key="secret")

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="headers are required"):
        agent.suggest_field_mapping("prompt", [], "CSV upload", [], [])

    monkeypatch.setattr(
        "src.adapters.llm.openai_crm_spreadsheet_assist.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.HTTPError("boom")),  # type: ignore[no-untyped-def]
    )
    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="Unable to use AI to interpret this spreadsheet layout right now"):
        agent.suggest_field_mapping("prompt", [], "CSV upload", ["Person"], [{"Person": "Taylor"}])


def test_openai_crm_spreadsheet_assist_validates_response_shapes(monkeypatch) -> None:
    responses = iter(
        [
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={
                    "output": [
                        {
                            "content": [
                                {"text": '{"field_mapping":{"Person":"lead_name","Organisation":null}}'}
                            ]
                        }
                    ]
                },
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={
                    "output_text": '{"field_mapping":{"Person":"lead_name","Organisation":null},"assistant_message":"I can finish this once I know what the date column means.","questions":[{"id":"date-purpose","prompt":"What does the Touchpoint column represent?","choices":[{"value":"follow-up-date","label":"Next follow-up date"},{"value":"last-contact-date","label":"Last contact date"}]}]}'
                },
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={
                    "output_text": '{"field_mapping":{"Person":"lead_name"},"assistant_message":"I handled the ambiguous columns automatically.","questions":null}'
                },
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": "not-json"},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":"bad"}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"unsupported_field"}}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":123}}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"assistant_message":123}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"questions":"bad"}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"questions":["bad"]}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"questions":[{"id":"","prompt":"test","choices":[{"value":"a","label":"A"},{"value":"b","label":"B"}]}]}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"questions":[{"id":"q1","prompt":"","choices":[{"value":"a","label":"A"},{"value":"b","label":"B"}]}]}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"questions":[{"id":"q1","prompt":"test","choices":[{"value":"a","label":"A"}]}]}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"questions":[{"id":"q1","prompt":"test","choices":["bad",{"value":"b","label":"B"}]}]}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"questions":[{"id":"q1","prompt":"test","choices":[{"value":"","label":"A"},{"value":"b","label":"B"}]}]}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"questions":[{"id":"q1","prompt":"test","choices":[{"value":"a","label":""},{"value":"b","label":"B"}]}]}'},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output": "bad"},
            ),
            httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output": ["bad", {"content": "bad"}, {"content": ["bad", {"no_text": "x"}]}]},
            ),
        ]
    )

    monkeypatch.setattr("src.adapters.llm.openai_crm_spreadsheet_assist.httpx.post", lambda *args, **kwargs: next(responses))
    agent = OpenAICRMSpreadsheetAssistAgent(api_key="secret")

    mapping, clarification = agent.suggest_field_mapping("prompt", [], "CSV upload", ["Person", "Organisation"], [{"Person": "Taylor"}])
    assert mapping["Person"] == "lead_name"
    assert mapping["Organisation"] is None
    assert clarification is None

    mapping, clarification = agent.suggest_field_mapping(
        "prompt",
        [],
        "CSV upload",
        ["Person", "Organisation"],
        [{"Person": "Taylor"}],
    )
    assert mapping["Person"] == "lead_name"
    assert clarification is not None
    assert clarification.required is True
    assert clarification.questions[0].id == "date-purpose"

    mapping, clarification = agent.suggest_field_mapping(
        "prompt",
        [],
        "CSV upload",
        ["Person"],
        [{"Person": "Taylor"}],
    )
    assert mapping["Person"] == "lead_name"
    assert clarification is not None
    assert clarification.required is False

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        agent.suggest_field_mapping("prompt", [], "CSV upload", ["Person"], [{"Person": "Taylor"}])

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        agent.suggest_field_mapping("prompt", [], "CSV upload", ["Person"], [{"Person": "Taylor"}])

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="unsupported field mapping"):
        agent.suggest_field_mapping("prompt", [], "CSV upload", ["Person"], [{"Person": "Taylor"}])

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        agent.suggest_field_mapping("prompt", [], "CSV upload", ["Person"], [{"Person": "Taylor"}])


def test_openai_crm_spreadsheet_assist_internal_parsers_cover_sparse_payloads(monkeypatch) -> None:
    assert _extract_text_from_response({"output": [{"content": [{"text": " hello "}]}]}) == "hello"

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _extract_text_from_response({"output": "bad"})

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _extract_text_from_response({"output": ["bad", {"content": "bad"}, {"content": ["bad", {"no_text": "x"}]}]})

    clarification = _parse_clarification(None, "Need nothing else.")
    assert clarification is not None
    assert clarification.required is False

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _parse_clarification("bad", "message")

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _parse_clarification([123], "message")

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _parse_clarification([{"id": "", "prompt": "Test", "choices": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]}], "message")

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _parse_clarification([{"id": "q1", "prompt": "", "choices": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]}], "message")

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _parse_clarification([{"id": "q1", "prompt": "Test", "choices": [{"value": "a", "label": "A"}]}], "message")

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _parse_clarification([{"id": "q1", "prompt": "Test", "choices": ["bad", {"value": "b", "label": "B"}]}], "message")

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _parse_clarification([{"id": "q1", "prompt": "Test", "choices": [{"value": "", "label": "A"}, {"value": "b", "label": "B"}]}], "message")

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        _parse_clarification([{"id": "q1", "prompt": "Test", "choices": [{"value": "a", "label": ""}, {"value": "b", "label": "B"}]}], "message")

    with pytest.raises(OpenAICRMSpreadsheetAssistError, match="invalid payload"):
        monkeypatch.setattr(
            "src.adapters.llm.openai_crm_spreadsheet_assist.httpx.post",
            lambda *args, **kwargs: httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"output_text": '{"field_mapping":{"Person":"lead_name"},"assistant_message":123}'},
            ),
        )
        OpenAICRMSpreadsheetAssistAgent(api_key="secret").suggest_field_mapping(
            "prompt",
            [],
            "CSV upload",
            ["Person"],
            [{"Person": "Taylor"}],
        )
