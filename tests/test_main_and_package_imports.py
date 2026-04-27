from __future__ import annotations

import runpy

import main
import src
import src.adapters
import src.adapters.market_data
import src.adapters.ui
import src.application
import src.domain


def test_package_modules_import() -> None:
    assert src.__doc__ == "Trade dashboard package."
    assert src.adapters.__doc__ == "Adapters layer: external systems and UI."
    assert src.adapters.market_data.__doc__ == "Market data adapters."
    assert src.adapters.ui.__doc__ == "UI adapters."
    assert src.application.__doc__ == "Application layer: use-cases and ports."
    assert src.domain.__doc__ == "Domain layer: pure market-risk rules and models."


def test_main_module_import_is_safe() -> None:
    assert main.__name__ == "main"


def test_main_script_prints_cli_hint_when_not_in_streamlit(monkeypatch, capsys) -> None:
    monkeypatch.setattr("streamlit.runtime.exists", lambda: False)

    runpy.run_path("main.py", run_name="__main__")

    assert capsys.readouterr().out.strip() == "This is a Streamlit app. Run it with: uv run streamlit run main.py"


def test_main_script_calls_render_when_streamlit_runtime_exists(monkeypatch) -> None:
    called: list[str] = []
    monkeypatch.setattr("streamlit.runtime.exists", lambda: True)
    monkeypatch.setattr("src.adapters.ui.streamlit_dashboard.render", lambda: called.append("rendered"))

    runpy.run_path("main.py", run_name="__main__")

    assert called == ["rendered"]
