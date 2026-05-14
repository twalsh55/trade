from __future__ import annotations

import importlib.util
from pathlib import Path


def load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_daily_prospecting.py"
    spec = importlib.util.spec_from_file_location("daily_prospecting_script_module", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load run_daily_prospecting.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_config_from_env_uses_defaults(monkeypatch) -> None:
    module = load_script_module()
    assert module.build_config_from_env.__module__ == "src.adapters.prospecting.runtime"


def test_build_email_notifier_requires_env(monkeypatch) -> None:
    module = load_script_module()
    assert module.build_email_notifier_from_env.__module__ == "src.adapters.prospecting.runtime"


def test_build_drafter_from_env_uses_template_without_api_key(monkeypatch) -> None:
    module = load_script_module()
    assert module.build_drafter_from_env.__module__ == "src.adapters.prospecting.runtime"


def test_parse_positive_int_validates_input(monkeypatch) -> None:
    module = load_script_module()
    assert callable(module.run_prospecting_job)


def test_main_reports_success(monkeypatch, capsys) -> None:
    module = load_script_module()
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(
        module,
        "build_config_from_env",
        lambda: type("Config", (), {"recipient_email": "tom@example.com"})(),
    )
    monkeypatch.setattr(
        module,
        "run_prospecting_job",
        lambda: type("Digest", (), {"scanned_post_count": 12, "shortlisted_count": 2})(),
    )

    exit_code = module.main()

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "Prospecting digest emailed to tom@example.com. Scanned 12 posts and shortlisted 2."


def test_main_reports_known_failures(monkeypatch, capsys) -> None:
    module = load_script_module()
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(module, "build_config_from_env", lambda: (_ for _ in ()).throw(ValueError("broken config")))

    exit_code = module.main()

    assert exit_code == 1
    assert capsys.readouterr().out.strip() == "broken config"
