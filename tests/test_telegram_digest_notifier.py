from __future__ import annotations

from src.adapters.notifications.telegram_digest_notifier import TelegramDigestNotifier, _chunk_text


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_message(self, text: str) -> None:
        self.messages.append(text)


def test_telegram_digest_notifier_sends_single_message() -> None:
    notifier = FakeNotifier()
    digest = TelegramDigestNotifier(notifier=notifier, chunk_size=1000)

    digest.send_email("tom@example.com", "Subject", "Body")

    assert notifier.messages == ["Subject\nRecipient: tom@example.com\n\nBody"]


def test_telegram_digest_notifier_chunks_long_messages() -> None:
    notifier = FakeNotifier()
    digest = TelegramDigestNotifier(notifier=notifier, chunk_size=20)

    digest.send_email("tom@example.com", "Subject", "Line 1\nLine 2\nLine 3\nLine 4")

    assert len(notifier.messages) >= 2
    assert notifier.messages[0]


def test_chunk_text_validates_chunk_size() -> None:
    try:
        _chunk_text("hello", 0)
    except ValueError as exc:
        assert str(exc) == "chunk_size must be greater than zero."
    else:
        raise AssertionError("Expected ValueError")
