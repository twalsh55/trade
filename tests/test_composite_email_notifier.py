from __future__ import annotations

from src.adapters.notifications.composite_email_notifier import CompositeEmailNotifier


class FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        self.calls.append((recipient, subject, text_body))


def test_composite_email_notifier_sends_to_all_notifiers() -> None:
    first = FakeNotifier()
    second = FakeNotifier()
    notifier = CompositeEmailNotifier((first, second))

    notifier.send_email("tom@example.com", "Subject", "Body")

    assert first.calls == [("tom@example.com", "Subject", "Body")]
    assert second.calls == [("tom@example.com", "Subject", "Body")]


def test_composite_email_notifier_requires_notifiers() -> None:
    try:
        CompositeEmailNotifier(())
    except ValueError as exc:
        assert str(exc) == "CompositeEmailNotifier requires at least one notifier."
    else:
        raise AssertionError("Expected ValueError")
