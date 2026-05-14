from __future__ import annotations

import logging
import os

import src
import src.adapters
import src.adapters.api
import src.adapters.auth
import src.adapters.market_data
import src.adapters.notifications
import src.adapters.persistence
import src.application
import src.domain
from src.env_utils import load_env_file


def test_package_modules_import() -> None:
    assert src.__doc__ == "Trade dashboard package."
    assert src.adapters.__doc__ == "Adapters layer: external systems and delivery adapters."
    assert src.adapters.api.__doc__ == "API adapters."
    assert src.adapters.auth.__doc__ == "Authentication adapters."
    assert src.adapters.market_data.__doc__ == "Market data adapters."
    assert src.adapters.notifications.__doc__ == "Notification adapters."
    assert src.adapters.persistence.__doc__ == "Persistence adapters."
    assert src.application.__doc__ == "Application layer: use-cases and ports."
    assert src.domain.__doc__ == "Domain layer: pure market-risk rules and models."


def test_load_env_file_sets_missing_variables(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nTELEGRAM_BOT_TOKEN=test-token\nTELEGRAM_CHAT_ID='chat-id'\nINVALID_LINE\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    load_env_file(str(env_file))

    assert load_env_file.__name__ == "load_env_file"
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "test-token"
    assert os.environ["TELEGRAM_CHAT_ID"] == "chat-id"


def test_load_env_file_does_not_override_existing_variables(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=file-token\n", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "existing-token")

    load_env_file(str(env_file))

    assert os.environ["TELEGRAM_BOT_TOKEN"] == "existing-token"


def test_load_env_file_skips_missing_file(tmp_path) -> None:
    missing_file = tmp_path / ".env"
    load_env_file(str(missing_file))
    assert logging.getLogger().level in (logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)
