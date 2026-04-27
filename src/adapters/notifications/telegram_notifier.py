from __future__ import annotations

import json
from urllib import request


class TelegramNotificationError(RuntimeError):
    """Raised when Telegram rejects or fails a notification request."""


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str) -> None:
        payload = json.dumps(
            {
                "chat_id": self.chat_id,
                "text": text,
            }
        ).encode("utf-8")
        req = request.Request(
            url=f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10) as response:
                if response.status >= 400:
                    raise TelegramNotificationError(f"Telegram API returned status {response.status}")
        except OSError as exc:
            raise TelegramNotificationError("Unable to send Telegram notification.") from exc
