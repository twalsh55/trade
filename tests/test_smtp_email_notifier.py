from __future__ import annotations

from src.adapters.notifications.smtp_email_notifier import EmailNotificationError, SMTPEmailNotifier


class FakeSMTP:
    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in: tuple[str, str] | None = None
        self.sent_messages: list[object] = []

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    def ehlo(self) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def send_message(self, message) -> None:  # type: ignore[no-untyped-def]
        self.sent_messages.append(message)


def test_smtp_email_notifier_sends_email(monkeypatch) -> None:
    smtp = FakeSMTP("smtp.example.com", 587, 20)
    monkeypatch.setattr(
        "src.adapters.notifications.smtp_email_notifier.smtplib.SMTP",
        lambda host, port, timeout: smtp,
    )

    notifier = SMTPEmailNotifier(
        host="smtp.example.com",
        port=587,
        username="user",
        password="pass",
        from_email="alerts@example.com",
    )
    notifier.send_email("tom@example.com", "Subject", "Body")

    message = smtp.sent_messages[0]
    assert smtp.started_tls is True
    assert smtp.logged_in == ("user", "pass")
    assert message["To"] == "tom@example.com"
    assert message["Subject"] == "Subject"


def test_smtp_email_notifier_raises_on_network_error(monkeypatch) -> None:
    def failing_smtp(host: str, port: int, timeout: int):  # type: ignore[no-untyped-def]
        raise OSError("offline")

    monkeypatch.setattr("src.adapters.notifications.smtp_email_notifier.smtplib.SMTP", failing_smtp)

    try:
        SMTPEmailNotifier(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",
            from_email="alerts@example.com",
        ).send_email("tom@example.com", "Subject", "Body")
    except EmailNotificationError as exc:
        assert str(exc) == "Unable to send email notification."
    else:
        raise AssertionError("Expected EmailNotificationError")
