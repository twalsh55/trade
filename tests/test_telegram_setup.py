from __future__ import annotations

import json
import os
from urllib.error import URLError

from src.adapters.notifications.telegram_setup import (
    TelegramSetupError,
    extract_chat_ids,
    fetch_updates,
    format_chat_id_report,
    get_env_secret,
)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_fetch_updates_reads_json_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.notifications.telegram_setup.request.urlopen",
        lambda url, timeout: FakeResponse({"ok": True, "result": []}),  # type: ignore[no-untyped-def]
    )

    payload = fetch_updates("bot-token")

    assert payload == {"ok": True, "result": []}


def test_get_env_secret_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-from-env")
    assert get_env_secret("TELEGRAM_BOT_TOKEN") == "token-from-env"


def test_get_env_secret_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert get_env_secret("TELEGRAM_BOT_TOKEN") is None


def test_fetch_updates_raises_on_network_error(monkeypatch) -> None:
    def fake_urlopen(url, timeout):  # type: ignore[no-untyped-def]
        raise URLError("offline")

    monkeypatch.setattr("src.adapters.notifications.telegram_setup.request.urlopen", fake_urlopen)

    try:
        fetch_updates("bot-token")
    except TelegramSetupError as exc:
        assert str(exc) == "Unable to fetch Telegram updates."
    else:
        raise AssertionError("Expected TelegramSetupError for network failure")


def test_fetch_updates_raises_on_unexpected_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.adapters.notifications.telegram_setup.request.urlopen",
        lambda url, timeout: FakeResponse(["unexpected"]),  # type: ignore[no-untyped-def]
    )

    try:
        fetch_updates("bot-token")
    except TelegramSetupError as exc:
        assert str(exc) == "Telegram returned an unexpected response."
    else:
        raise AssertionError("Expected TelegramSetupError for invalid payload")


def test_extract_chat_ids_and_format_report() -> None:
    payload = {
        "result": [
            {"message": {"chat": {"id": 123, "first_name": "Tom"}}},
            {"message": {"chat": {"id": -456, "title": "Alerts Group"}}},
            {"message": {"chat": {"id": 123, "first_name": "Tom"}}},
            {"message": {"chat": {"id": 999, "username": "market_bot_user"}}},
            {"message": {"chat": None}},
            {"message": {"chat": {"first_name": "No Id"}}},
            {"edited_message": {"chat": {"id": 111}}},
            "ignore-me",
        ]
    }

    chat_ids = extract_chat_ids(payload)

    assert chat_ids == [("123", "Tom"), ("-456", "Alerts Group"), ("999", "market_bot_user")]
    assert format_chat_id_report(chat_ids) == (
        "Telegram chat IDs:\n"
        "- 123 (Tom)\n"
        "- -456 (Alerts Group)\n"
        "- 999 (market_bot_user)"
    )


def test_extract_chat_ids_and_format_report_handle_empty_results() -> None:
    assert extract_chat_ids({"result": "invalid"}) == []
    assert format_chat_id_report([]) == (
        "No chat IDs found. Send your bot a message in Telegram, then run this helper again."
    )
