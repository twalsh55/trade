from __future__ import annotations

from src.application.ports import EmailDeliveryPort


class CompositeEmailNotifier:
    def __init__(self, notifiers: tuple[EmailDeliveryPort, ...]) -> None:
        if not notifiers:
            raise ValueError("CompositeEmailNotifier requires at least one notifier.")
        self.notifiers = notifiers

    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        for notifier in self.notifiers:
            notifier.send_email(recipient, subject, text_body)
