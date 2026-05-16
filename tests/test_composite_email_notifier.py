from __future__ import annotations

from src.adapters.notifications.composite_email_notifier import CompositeEmailNotifier


class FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        self.calls.append((recipient, subject, text_body))


class FailingNotifier:
    def __init__(self, message: str = "failed") -> None:
        self.message = message
        self.calls = 0

    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        self.calls += 1
        raise RuntimeError(self.message)




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


def test_composite_email_notifier_succeeds_when_one_channel_works() -> None:
    failing = FailingNotifier("smtp down")
    working = FakeNotifier()
    notifier = CompositeEmailNotifier((failing, working))

    notifier.send_email("tom@example.com", "Subject", "Body")

    assert failing.calls == 1
    assert working.calls == [("tom@example.com", "Subject", "Body")]


def test_composite_email_notifier_raises_when_all_channels_fail() -> None:
    first = FailingNotifier("smtp down")
    second = FailingNotifier("telegram down")
    notifier = CompositeEmailNotifier((first, second))

    try:
        notifier.send_email("tom@example.com", "Subject", "Body")
    except RuntimeError as exc:
        assert str(exc) == "telegram down"
    else:
        raise AssertionError("Expected RuntimeError")
