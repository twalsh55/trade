from __future__ import annotations

import smtplib
from email.message import EmailMessage


class EmailNotificationError(RuntimeError):
    """Raised when email delivery fails."""


class SMTPEmailNotifier:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        use_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_tls = use_tls

    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text_body)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
                smtp.ehlo()
                if self.use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(self.username, self.password)
                smtp.send_message(message)
        except OSError as exc:
            raise EmailNotificationError("Unable to send email notification.") from exc
