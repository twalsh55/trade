from __future__ import annotations

import importlib.util
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.adapters.automation.runtime import (
    FileAutomationHeartbeatStore,
    FileAutomationStateStore,
    LocalAutomationWorker,
    _format_token_usage,
    _run_founder_code_sync_job,
    _run_job_with_timeout,
    _run_operator_briefing_job,
    _run_prospect_job,
    _run_prospect_with_template_fallback,
    _run_sentiment_job,
    acquire_worker_lock,
    build_jobs_from_env,
    build_worker_from_env,
    build_watchdog_cron_lines,
    collect_automation_config_errors,
    is_worker_healthy,
    read_heartbeat_from_file,
    run_worker_from_env,
)
from src.domain.prospecting import ProspectTokenUsage
from src.application.automation import AutomationJob, AutomationJobResult


def test_file_automation_state_store_round_trips_and_handles_invalid_payload(tmp_path) -> None:
    path = tmp_path / "state.json"
    store = FileAutomationStateStore(path)
    assert store.read_state() == {}

    path.write_text("[]", encoding="utf-8")
    assert store.read_state() == {}

    state = {"job": {"last_status": "ok"}}
    store.write_state(state)
    assert store.read_state() == state


def test_file_automation_heartbeat_store_and_health_checks(tmp_path) -> None:
    path = tmp_path / "heartbeat.json"
    store = FileAutomationHeartbeatStore(path)
    store.write_heartbeat(
        beat=__import__("src.application.automation", fromlist=["AutomationHeartbeat"]).AutomationHeartbeat(
            generated_at=datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
            process_id=123,
            active_job_names=("a", "b"),
        )
    )

    payload = read_heartbeat_from_file(path)
    assert payload["process_id"] == 123
    assert read_heartbeat_from_file(tmp_path / "missing.json") == {}
    assert is_worker_healthy(path, max_age_seconds=120, now=datetime(2026, 5, 16, 10, 1, tzinfo=UTC)) is True
    assert is_worker_healthy(path, max_age_seconds=10, now=datetime(2026, 5, 16, 10, 1, tzinfo=UTC)) is False

    path.write_text(json.dumps({"generated_at": 1}), encoding="utf-8")
    assert is_worker_healthy(path, max_age_seconds=10, now=datetime(2026, 5, 16, 10, 1, tzinfo=UTC)) is False


def test_local_automation_worker_runs_jobs_and_respects_max_iterations(tmp_path) -> None:
    state_store = FileAutomationStateStore(tmp_path / "state.json")
    heartbeat_store = FileAutomationHeartbeatStore(tmp_path / "heartbeat.json")
    seen: list[str] = []
    sleeps: list[int] = []
    times = iter(
        [
            datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
            datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
            datetime(2026, 5, 16, 10, 1, tzinfo=UTC),
            datetime(2026, 5, 16, 10, 2, tzinfo=UTC),
            datetime(2026, 5, 16, 10, 2, tzinfo=UTC),
            datetime(2026, 5, 16, 10, 2, tzinfo=UTC),
            datetime(2026, 5, 16, 10, 2, tzinfo=UTC),
            datetime(2026, 5, 16, 10, 3, tzinfo=UTC),
        ]
    )
    logs: list[str] = []
    worker = LocalAutomationWorker(
        jobs=(
            AutomationJob(
                name="job",
                interval=timedelta(hours=1),
                runner=lambda: seen.append("job") or AutomationJobResult(status="ok", detail="done"),
            ),
        ),
        state_store=state_store,
        heartbeat_store=heartbeat_store,
        poll_seconds=30,
        process_id=777,
        sleep=lambda seconds: sleeps.append(seconds),
        now=lambda: next(times),
        log=lambda line: logs.append(line),
    )

    assert worker.run_forever(max_iterations=2) == 0
    assert seen == ["job"]
    assert sleeps == [30]
    assert "job=job status=ok" in logs[0]


def test_collect_automation_config_errors_and_watchdog_lines(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_POLL_SECONDS", "bad")
    monkeypatch.setenv("AUTOMATION_PROSPECT_INTERVAL_MINUTES", "0")
    errors = collect_automation_config_errors()
    assert "AUTOMATION_POLL_SECONDS must be an integer" in errors
    assert "AUTOMATION_PROSPECT_INTERVAL_MINUTES must be greater than zero" in errors

    reboot_line, watchdog_line = build_watchdog_cron_lines(Path("/tmp/trade"))
    assert reboot_line.startswith("@reboot cd /tmp/trade")
    assert "PYTHONUNBUFFERED=1" in reboot_line
    assert "run_local_automation.py" in watchdog_line


def test_acquire_worker_lock_blocks_second_holder(tmp_path) -> None:
    lock_path = tmp_path / "worker.lock"
    with acquire_worker_lock(lock_path):
        with pytest.raises(RuntimeError, match="already running"):
            with acquire_worker_lock(lock_path):
                raise AssertionError("should not acquire twice")


def _load_script_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_local_automation_script_handles_success_and_errors(monkeypatch, capsys) -> None:
    module = _load_script_module(
        Path(__file__).resolve().parents[1] / "scripts" / "run_local_automation.py",
        "run_local_automation_script_module",
    )
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(module, "run_worker_from_env", lambda: 0)
    assert module.main() == 0

    monkeypatch.setattr(module, "run_worker_from_env", lambda: (_ for _ in ()).throw(RuntimeError("busy")))
    assert module.main() == 1
    assert "busy" in capsys.readouterr().out

    monkeypatch.setattr(module, "run_worker_from_env", lambda: (_ for _ in ()).throw(ValueError("bad config")))
    assert module.main() == 1
    assert "bad config" in capsys.readouterr().out


def test_local_automation_status_script_reports_health(monkeypatch, capsys) -> None:
    module = _load_script_module(
        Path(__file__).resolve().parents[1] / "scripts" / "local_automation_status.py",
        "local_automation_status_script_module",
    )
    monkeypatch.setattr(module, "load_env_file", lambda: None)
    monkeypatch.setattr(module, "read_heartbeat_from_file", lambda path: {"generated_at": "2026-05-16T10:00:00+00:00"})
    monkeypatch.setattr(module, "is_worker_healthy", lambda path, max_age_seconds, now: True)
    assert module.main() == 0
    assert '"healthy": true' in capsys.readouterr().out.lower()

    monkeypatch.setattr(module, "is_worker_healthy", lambda path, max_age_seconds, now: False)
    assert module.main() == 1


def test_build_jobs_worker_and_run_worker_from_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AUTOMATION_PROSPECT_INTERVAL_MINUTES", "720")
    monkeypatch.setenv("AUTOMATION_OPERATOR_BRIEFING_INTERVAL_HOURS", "12")
    monkeypatch.setenv("AUTOMATION_POLL_SECONDS", "9")
    monkeypatch.setenv("AUTOMATION_JOB_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("AUTOMATION_ENABLE_FOUNDER_CODE_SYNC", "false")
    monkeypatch.setenv("AUTOMATION_ENABLE_SCHEDULED_OPERATOR_BRIEFING", "false")
    monkeypatch.setenv("AUTOMATION_ENABLE_SENTIMENT_JOB", "false")
    monkeypatch.setenv("AUTOMATION_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("AUTOMATION_HEARTBEAT_FILE", str(tmp_path / "heartbeat.json"))
    jobs = build_jobs_from_env()
    assert jobs[0].interval == timedelta(minutes=720)
    assert len(jobs) == 1

    monkeypatch.setenv("AUTOMATION_ENABLE_FOUNDER_CODE_SYNC", "true")
    monkeypatch.setenv("AUTOMATION_FOUNDER_CODE_SYNC_INTERVAL_SECONDS", "60")
    jobs = build_jobs_from_env()
    assert jobs[1].name == "founder_code_sync"
    assert jobs[1].interval == timedelta(seconds=60)

    worker = build_worker_from_env()
    assert worker.poll_seconds == 9

    monkeypatch.setenv("AUTOMATION_ENABLE_SCHEDULED_OPERATOR_BRIEFING", "true")
    jobs = build_jobs_from_env()
    assert jobs[2].interval == timedelta(hours=12)

    monkeypatch.setenv("AUTOMATION_ENABLE_SENTIMENT_JOB", "true")
    monkeypatch.setenv("AUTOMATION_SENTIMENT_INTERVAL_HOURS", "6")
    jobs = build_jobs_from_env()
    assert jobs[3].name == "sentiment_daily"
    assert jobs[3].interval == timedelta(hours=6)

    class FakeWorker:
        def run_forever(self, max_iterations=None):
            return 7

    monkeypatch.setattr("src.adapters.automation.runtime.build_worker_from_env", lambda: FakeWorker())
    monkeypatch.setattr("src.adapters.automation.runtime.acquire_worker_lock", lambda path: __import__("contextlib").nullcontext())
    monkeypatch.setattr("src.adapters.automation.runtime.collect_automation_config_errors", lambda: [])
    assert run_worker_from_env(max_iterations=3) == 7

    monkeypatch.setattr("src.adapters.automation.runtime.collect_automation_config_errors", lambda: ["bad env"])
    with pytest.raises(ValueError, match="bad env"):
        run_worker_from_env()


def test_automation_job_runners_report_success_and_failure(monkeypatch) -> None:
    digest = type(
        "Digest",
        (),
        {
            "profile": "crm_direction",
            "scanned_post_count": 10,
            "shortlisted_count": 2,
            "token_usage": ProspectTokenUsage(model="gpt-5-nano", input_tokens=10, output_tokens=5, total_tokens=15),
        },
    )()
    monkeypatch.setattr("src.adapters.automation.runtime.run_prospecting_job", lambda: digest)
    result = _run_prospect_job()
    assert result.status == "ok"
    assert "profile=crm_direction" in result.detail
    assert "briefing=sent" in result.detail

    monkeypatch.setenv("APP_OPENAI_API_KEY", "sk-...")
    monkeypatch.setattr("src.adapters.automation.runtime.run_prospecting_job", lambda: digest)
    result = _run_prospect_job()
    assert "openai_key=placeholder" in result.detail

    calls = {"count": 0}

    def flaky_prospect():
        calls["count"] += 1
        if calls["count"] == 1:
            raise __import__("src.adapters.llm.openai_prospect_drafter", fromlist=["OpenAIProspectDrafterError"]).OpenAIProspectDrafterError(
                "unauthorized"
            )
        return digest

    monkeypatch.setenv("APP_OPENAI_API_KEY", "bad-key")
    monkeypatch.setattr("src.adapters.automation.runtime.run_prospecting_job", flaky_prospect)
    result = _run_prospect_job()
    assert result.status == "ok"
    assert "fallback=template" in result.detail
    assert os.environ["APP_OPENAI_API_KEY"] == "bad-key"

    monkeypatch.setenv("AUTOMATION_ALLOW_TEMPLATE_FALLBACK", "false")
    monkeypatch.setattr(
        "src.adapters.automation.runtime.run_prospecting_job",
        lambda: (_ for _ in ()).throw(
            __import__("src.adapters.llm.openai_prospect_drafter", fromlist=["OpenAIProspectDrafterError"]).OpenAIProspectDrafterError(
                "unauthorized"
            )
        ),
    )
    assert _run_prospect_job().status == "failed"
    monkeypatch.delenv("AUTOMATION_ALLOW_TEMPLATE_FALLBACK", raising=False)

    monkeypatch.setattr("src.adapters.automation.runtime.run_prospecting_job", lambda: (_ for _ in ()).throw(ValueError("nope")))
    assert _run_prospect_job().status == "failed"

    monkeypatch.setattr("src.adapters.automation.runtime.sync_founder_code_requests_from_api", lambda: 3)
    assert _run_founder_code_sync_job().detail == "synced=3"

    monkeypatch.setattr(
        "src.adapters.automation.runtime.sync_founder_code_requests_from_api",
        lambda: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert _run_founder_code_sync_job().status == "failed"

    briefing = type("Briefing", (), {"prospect_run_count": 2, "total_shortlisted_ideas": 5, "product_updates": (1, 2)})()
    monkeypatch.setattr("src.adapters.automation.runtime.run_daily_operator_briefing_job", lambda: briefing)
    result = _run_operator_briefing_job()
    assert result.status == "ok"
    assert "runs=2 ideas=5 updates=2" == result.detail

    monkeypatch.setattr(
        "src.adapters.automation.runtime.run_daily_operator_briefing_job",
        lambda: (_ for _ in ()).throw(RuntimeError("smtp broken")),
    )
    assert _run_operator_briefing_job().status == "failed"

    assert _run_sentiment_job(lambda: None).status == "ok"
    assert _run_sentiment_job(lambda: (_ for _ in ()).throw(RuntimeError("bad"))).status == "failed"
    assert _format_token_usage(None) == "template-mode"
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("src.adapters.automation.runtime.run_prospecting_job", lambda: digest)
    assert _run_prospect_with_template_fallback() == digest
    assert "APP_OPENAI_API_KEY" not in os.environ


def test_run_job_with_timeout_covers_success_and_timeout() -> None:
    result = _run_job_with_timeout("fast", lambda: AutomationJobResult(status="ok", detail="done"), 1)
    assert result.status == "ok"

    def slow():
        __import__("time").sleep(2)
        return AutomationJobResult(status="ok", detail="too late")

    timed_out = _run_job_with_timeout("slow", slow, 1)
    assert timed_out.status == "failed"
    assert "slow exceeded 1 seconds" == timed_out.detail
