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
