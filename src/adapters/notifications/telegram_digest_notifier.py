from __future__ import annotations

from src.adapters.notifications.telegram_notifier import TelegramNotifier

TELEGRAM_MESSAGE_LIMIT = 4000


class TelegramDigestNotifier:
    def __init__(self, notifier: TelegramNotifier, chunk_size: int = TELEGRAM_MESSAGE_LIMIT) -> None:
        self.notifier = notifier
        self.chunk_size = chunk_size

    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        prefix = f"{subject}\nRecipient: {recipient}\n\n"
        message = prefix + text_body
        for chunk in _chunk_text(message, self.chunk_size):
            self.notifier.send_message(chunk)


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            split_at = text.rfind("\n", start, end)
            if split_at > start:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end if end > start else start + chunk_size
    return chunks
