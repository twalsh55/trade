from __future__ import annotations

import importlib.util
from pathlib import Path


def load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "test_telegram_send.py"
    spec = importlib.util.spec_from_file_location("test_telegram_send_script_module", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load test_telegram_send.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_startup_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "send_telegram_startup.py"
    spec = importlib.util.spec_from_file_location("send_telegram_startup_script_module", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load send_telegram_startup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_test_telegram_send_script_requires_bot_token(monkeypatch, capsys) -> None:
    module = load_script_module()
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(module, "get_env_secret", lambda name: None)

    exit_code = module.main()

    assert exit_code == 1
    assert capsys.readouterr().out.strip() == "Missing TELEGRAM_BOT_TOKEN. Add it to .env first."


def test_test_telegram_send_script_requires_chat_id(monkeypatch, capsys) -> None:
    module = load_script_module()
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(module, "get_env_secret", lambda name: "bot-token" if name == "TELEGRAM_BOT_TOKEN" else None)

    exit_code = module.main()

    assert exit_code == 1
    assert capsys.readouterr().out.strip() == "Missing TELEGRAM_CHAT_ID. Add it to .env first."


def test_test_telegram_send_script_reports_send_failure(monkeypatch, capsys) -> None:
    module = load_script_module()
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(module, "get_env_secret", lambda name: "configured-value")

    class FailingNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            self.bot_token = bot_token
            self.chat_id = chat_id

        def send_message(self, text: str) -> None:
            raise module.TelegramNotificationError("Unable to send Telegram notification.")

    monkeypatch.setattr(module, "TelegramNotifier", FailingNotifier)

    exit_code = module.main()

    assert exit_code == 1
    assert capsys.readouterr().out.strip() == "Unable to send Telegram notification."


def test_test_telegram_send_script_reports_success(monkeypatch, capsys) -> None:
    module = load_script_module()
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(module, "get_env_secret", lambda name: "configured-value")
    sent: list[tuple[str, str, str]] = []

    class WorkingNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            self.bot_token = bot_token
            self.chat_id = chat_id

        def send_message(self, text: str) -> None:
            sent.append((self.bot_token, self.chat_id, text))

    monkeypatch.setattr(module, "TelegramNotifier", WorkingNotifier)

    exit_code = module.main()

    assert exit_code == 0
    assert sent == [("configured-value", "configured-value", "Telegram test message from Market Crash Monitor.")]
    assert capsys.readouterr().out.strip() == "Telegram test message sent successfully."


def test_startup_script_skips_when_missing_credentials(monkeypatch, capsys) -> None:
    module = load_startup_script_module()
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(module, "get_env_secret", lambda name: None)

    exit_code = module.main()

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "Skipping Telegram startup message: missing bot token or chat ID."


def test_startup_script_sends_message(monkeypatch, capsys) -> None:
    module = load_startup_script_module()
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(
        module,
        "get_env_secret",
        lambda name: {
            "TELEGRAM_BOT_TOKEN": "configured-value",
            "TELEGRAM_CHAT_ID": "configured-value",
            "APP_TIMEZONE": "Europe/Rome",
        }.get(name),
    )
    sent: list[tuple[str, str, str]] = []

    class WorkingNotifier:
        def __init__(self, bot_token: str, chat_id: str) -> None:
            self.bot_token = bot_token
            self.chat_id = chat_id

        def send_message(self, text: str) -> None:
            sent.append((self.bot_token, self.chat_id, text))

    monkeypatch.setattr(module, "TelegramNotifier", WorkingNotifier)
    monkeypatch.setattr(
        module,
        "datetime",
        type("FakeDatetime", (), {"now": staticmethod(lambda: __import__("datetime").datetime(2024, 5, 6, 12, 30, tzinfo=__import__("datetime").timezone.utc))}),
    )

    exit_code = module.main()

    assert exit_code == 0
    assert sent == [("configured-value", "configured-value", "Market Crash Monitor server started\nStartup time: 2024-05-06 14:30:00 CEST")]
    assert capsys.readouterr().out.strip() == "Telegram startup message sent successfully."
