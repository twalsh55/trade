from __future__ import annotations

from src.application.ports import EmailDeliveryPort


class CompositeEmailNotifier:
    def __init__(self, notifiers: tuple[EmailDeliveryPort, ...]) -> None:
        if not notifiers:
            raise ValueError("CompositeEmailNotifier requires at least one notifier.")
        self.notifiers = notifiers

    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        last_error: Exception | None = None
        delivered = False
        for notifier in self.notifiers:
            try:
                notifier.send_email(recipient, subject, text_body)
                delivered = True
            except Exception as exc:  # pragma: no cover - exercised via tests with synthetic notifiers
                last_error = exc
        if delivered:
            return
        if last_error is not None:
            raise last_error
