from __future__ import annotations

import importlib.util
from pathlib import Path


def load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_periodic_prospecting.py"
    spec = importlib.util.spec_from_file_location("periodic_prospecting_script_module", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load run_periodic_prospecting.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_periodic_main_reports_success(monkeypatch, capsys) -> None:
    module = load_script_module()
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(module, "parse_positive_int", lambda name, default: 2 if name == "PROSPECT_PERIODIC_MAX_RUNS" else 1)
    monkeypatch.setattr(
        module,
        "run_prospecting_job",
        lambda: type(
            "Digest",
            (),
            {
                "profile": "crm_direction",
                "scanned_post_count": 12,
                "shortlisted_count": 2,
                "token_usage": type("Usage", (), {"model": "gpt-5-nano", "input_tokens": 40, "output_tokens": 10, "total_tokens": 50})(),
            },
        )(),
    )
    sleeps: list[int] = []
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleeps.append(seconds))

    exit_code = module.main()

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Run 1/2: profile=crm_direction scanned=12 shortlisted=2 token_usage=50 total" in out
    assert "Run 2/2: profile=crm_direction scanned=12 shortlisted=2 token_usage=50 total" in out
    assert sleeps == [60]
