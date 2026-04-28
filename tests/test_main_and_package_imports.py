from __future__ import annotations

import os
import runpy
import logging
import sys
import types
from pathlib import Path

import main
import src
import src.adapters
import src.adapters.market_data
import src.adapters.notifications
import src.adapters.ui
import src.application
import src.domain


def test_package_modules_import() -> None:
    assert src.__doc__ == "Trade dashboard package."
    assert src.adapters.__doc__ == "Adapters layer: external systems and UI."
    assert src.adapters.market_data.__doc__ == "Market data adapters."
    assert src.adapters.notifications.__doc__ == "Notification adapters."
    assert src.adapters.ui.__doc__ == "UI adapters."
    assert src.application.__doc__ == "Application layer: use-cases and ports."
    assert src.domain.__doc__ == "Domain layer: pure market-risk rules and models."


def test_main_module_import_is_safe() -> None:
    assert main.__name__ == "main"


def test_load_env_file_sets_missing_variables(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nTELEGRAM_BOT_TOKEN=test-token\nTELEGRAM_CHAT_ID='chat-id'\nINVALID_LINE\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    main.load_env_file(str(env_file))

    assert os.environ["TELEGRAM_BOT_TOKEN"] == "test-token"
    assert os.environ["TELEGRAM_CHAT_ID"] == "chat-id"


def test_load_env_file_does_not_override_existing_variables(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=file-token\n", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "existing-token")

    main.load_env_file(str(env_file))

    assert os.environ["TELEGRAM_BOT_TOKEN"] == "existing-token"


def test_load_env_file_skips_missing_file(tmp_path) -> None:
    missing_file = tmp_path / ".env"
    main.load_env_file(str(missing_file))


def test_main_script_prints_cli_hint_when_not_in_streamlit(monkeypatch, capsys) -> None:
    monkeypatch.setattr("streamlit.runtime.exists", lambda: False)

    runpy.run_path("main.py", run_name="__main__")

    assert capsys.readouterr().out.strip() == "This is a Streamlit app. Run it with: uv run streamlit run main.py"


def test_main_script_calls_render_when_streamlit_runtime_exists(monkeypatch) -> None:
    called: list[str] = []
    monkeypatch.setattr("streamlit.runtime.exists", lambda: True)
    stub_module = types.SimpleNamespace(render=lambda: called.append("rendered"))
    monkeypatch.setitem(sys.modules, "src.adapters.ui.streamlit_dashboard", stub_module)

    runpy.run_path("main.py", run_name="__main__")

    assert called == ["rendered"]


def test_main_logging_configuration_exists() -> None:
    assert logging.getLogger().level in (logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)
