from __future__ import annotations

import json
import os
from urllib import request


class TelegramSetupError(RuntimeError):
    """Raised when Telegram setup helpers cannot retrieve updates."""


def get_env_secret(name: str) -> str | None:
    value = os.getenv(name)
    return value if value else None


def fetch_updates(bot_token: str) -> dict[str, object]:
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        with request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        raise TelegramSetupError("Unable to fetch Telegram updates.") from exc

    if not isinstance(payload, dict):
        raise TelegramSetupError("Telegram returned an unexpected response.")
    return payload


def extract_chat_ids(payload: dict[str, object]) -> list[tuple[str, str]]:
    results = payload.get("result", [])
    if not isinstance(results, list):
        return []

    chat_ids: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        message = item.get("message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict):
            continue

        chat_id = chat.get("id")
        if chat_id is None:
            continue

        chat_id_text = str(chat_id)
        if chat_id_text in seen:
            continue

        title = chat.get("title") or chat.get("username") or chat.get("first_name") or "Unknown"
        chat_ids.append((chat_id_text, str(title)))
        seen.add(chat_id_text)

    return chat_ids


def format_chat_id_report(chat_ids: list[tuple[str, str]]) -> str:
    if not chat_ids:
        return "No chat IDs found. Send your bot a message in Telegram, then run this helper again."

    lines = ["Telegram chat IDs:"]
    lines.extend(f"- {chat_id} ({title})" for chat_id, title in chat_ids)
    return "\n".join(lines)
