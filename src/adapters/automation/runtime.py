from __future__ import annotations

import fcntl
import json
import os
import signal
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.adapters.notifications.smtp_email_notifier import EmailNotificationError
from src.adapters.founder_code.runtime import sync_founder_code_requests_from_api
from src.adapters.llm.openai_prospect_drafter import OpenAIProspectDrafterError
from src.adapters.operator_briefing.runtime import run_daily_operator_briefing_job
from src.adapters.prospecting.runtime import get_app_openai_api_key, is_placeholder_openai_key, parse_positive_int, run_prospecting_job
from src.adapters.social.reddit_lead_source import RedditLeadSourceError
from src.application.automation import (
    AutomationHeartbeat,
    AutomationHeartbeatPort,
    AutomationJob,
    AutomationJobResult,
    AutomationStatePort,
    RunAutomationTickUseCase,
)


class FileAutomationStateStore(AutomationStatePort):
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_state(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        if not isinstance(payload, dict):
            return {}
        return {str(key): value for key, value in payload.items() if isinstance(value, dict)}

    def write_state(self, state: dict[str, dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")


class FileAutomationHeartbeatStore(AutomationHeartbeatPort):
    def __init__(self, path: Path) -> None:
        self.path = path

    def write_heartbeat(self, beat: AutomationHeartbeat) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(beat)
        payload["generated_at"] = beat.generated_at.isoformat()
        self.path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


class LocalAutomationWorker:
    def __init__(
        self,
        jobs: tuple[AutomationJob, ...],
        state_store: AutomationStatePort,
        heartbeat_store: AutomationHeartbeatPort,
        poll_seconds: int,
        process_id: int | None = None,
        sleep: callable = time.sleep,  # type: ignore[assignment]
        now: callable = lambda: datetime.now(tz=UTC),  # type: ignore[assignment]
        log: callable = print,  # type: ignore[assignment]
    ) -> None:
        self.jobs = jobs
        self.state_store = state_store
        self.heartbeat_store = heartbeat_store
        self.poll_seconds = poll_seconds
        self.process_id = process_id or os.getpid()
        self.sleep = sleep
        self.now = now
        self.log = log
        self.use_case = RunAutomationTickUseCase(state_port=state_store, heartbeat_port=heartbeat_store, now=now)

    def run_forever(self, max_iterations: int | None = None) -> int:
        iteration = 0
        while True:
            iteration += 1
            result = self.use_case.execute(self.jobs, process_id=self.process_id)
            timestamp = self.now().isoformat()
            for job in result.executed_jobs:
                self.log(
                    f"[{timestamp}] job={job.name} status={job.result.status} detail={job.result.detail}"
                )
            if max_iterations is not None and iteration >= max_iterations:
                return 0
            self.sleep(self.poll_seconds)


def build_jobs_from_env() -> tuple[AutomationJob, ...]:
    timeout_seconds = parse_positive_int("AUTOMATION_JOB_TIMEOUT_SECONDS", default=45)
    jobs = [
        AutomationJob(
            name="prospect_hourly",
            interval=timedelta(minutes=parse_positive_int("AUTOMATION_PROSPECT_INTERVAL_MINUTES", default=720)),
            runner=lambda: _run_job_with_timeout("prospect_hourly", _run_prospect_job, timeout_seconds),
        ),
    ]
    if os.getenv("AUTOMATION_ENABLE_FOUNDER_CODE_SYNC", "false").strip().lower() == "true":
        jobs.append(
            AutomationJob(
                name="founder_code_sync",
                interval=timedelta(seconds=parse_positive_int("AUTOMATION_FOUNDER_CODE_SYNC_INTERVAL_SECONDS", default=60)),
                runner=lambda: _run_job_with_timeout("founder_code_sync", _run_founder_code_sync_job, timeout_seconds),
            )
        )
    if os.getenv("AUTOMATION_ENABLE_SCHEDULED_OPERATOR_BRIEFING", "false").strip().lower() == "true":
        jobs.append(
            AutomationJob(
                name="operator_briefing_daily",
                interval=timedelta(hours=parse_positive_int("AUTOMATION_OPERATOR_BRIEFING_INTERVAL_HOURS", default=24)),
                runner=lambda: _run_job_with_timeout("operator_briefing_daily", _run_operator_briefing_job, timeout_seconds),
            )
        )
    if os.getenv("AUTOMATION_ENABLE_SENTIMENT_JOB", "false").strip().lower() == "true":
        from src.adapters.sentiment.runtime import run_etf_sentiment_job

        jobs.append(
            AutomationJob(
                name="sentiment_daily",
                interval=timedelta(hours=parse_positive_int("AUTOMATION_SENTIMENT_INTERVAL_HOURS", default=24)),
                runner=lambda: _run_job_with_timeout(
                    "sentiment_daily",
                    lambda: _run_sentiment_job(run_etf_sentiment_job),
                    timeout_seconds,
                ),
            )
        )
    return tuple(jobs)


def build_worker_from_env() -> LocalAutomationWorker:
    return LocalAutomationWorker(
        jobs=build_jobs_from_env(),
        state_store=FileAutomationStateStore(Path(os.getenv("AUTOMATION_STATE_FILE", "var/automation_state.json"))),
        heartbeat_store=FileAutomationHeartbeatStore(
            Path(os.getenv("AUTOMATION_HEARTBEAT_FILE", "var/automation_heartbeat.json"))
        ),
        poll_seconds=parse_positive_int("AUTOMATION_POLL_SECONDS", default=30),
    )


def collect_automation_config_errors() -> list[str]:
    errors: list[str] = []
    for name in (
        "AUTOMATION_POLL_SECONDS",
        "AUTOMATION_PROSPECT_INTERVAL_MINUTES",
        "AUTOMATION_FOUNDER_CODE_SYNC_INTERVAL_SECONDS",
        "AUTOMATION_OPERATOR_BRIEFING_INTERVAL_HOURS",
        "AUTOMATION_SENTIMENT_INTERVAL_HOURS",
        "AUTOMATION_JOB_TIMEOUT_SECONDS",
    ):
        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            continue
        try:
            if int(raw_value) <= 0:
                errors.append(f"{name} must be greater than zero")
        except ValueError:
            errors.append(f"{name} must be an integer")
    return errors


@contextmanager
def acquire_worker_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("Automation worker is already running.") from exc
    handle.write(str(os.getpid()))
    handle.flush()
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def run_worker_from_env(max_iterations: int | None = None) -> int:
    errors = collect_automation_config_errors()
    if errors:
        raise ValueError("\n".join(errors))
    lock_path = Path(os.getenv("AUTOMATION_LOCK_FILE", "var/automation_worker.lock"))
    with acquire_worker_lock(lock_path):
        worker = build_worker_from_env()
        return worker.run_forever(max_iterations=max_iterations)


def _run_prospect_job() -> AutomationJobResult:
    fallback_suffix = ""
    placeholder_suffix = ""
    try:
        digest = run_prospecting_job()
    except OpenAIProspectDrafterError as exc:
        if os.getenv("AUTOMATION_ALLOW_TEMPLATE_FALLBACK", "true").strip().lower() == "false":
            return AutomationJobResult(status="failed", detail=str(exc))
        digest = _run_prospect_with_template_fallback()
        fallback_suffix = " fallback=template"
    except (ValueError, EmailNotificationError, RedditLeadSourceError, RuntimeError) as exc:
        return AutomationJobResult(status="failed", detail=str(exc))
    openai_api_key = get_app_openai_api_key()
    if openai_api_key and is_placeholder_openai_key(openai_api_key):
        placeholder_suffix = " openai_key=placeholder"
    return AutomationJobResult(
        status="ok",
        detail=(
            f"profile={digest.profile} scanned={digest.scanned_post_count} shortlisted={digest.shortlisted_count} "
            f"token_usage={_format_token_usage(digest.token_usage)} briefing=sent"
            f"{fallback_suffix}{placeholder_suffix}"
        ),
    )


def _run_operator_briefing_job() -> AutomationJobResult:
    try:
        briefing = run_daily_operator_briefing_job()
    except (ValueError, EmailNotificationError, RuntimeError) as exc:
        return AutomationJobResult(status="failed", detail=str(exc))
    return AutomationJobResult(
        status="ok",
        detail=(
            f"runs={briefing.prospect_run_count} ideas={briefing.total_shortlisted_ideas} "
            f"updates={len(briefing.product_updates)}"
        ),
    )


def _run_founder_code_sync_job() -> AutomationJobResult:
    try:
        synced_count = sync_founder_code_requests_from_api()
    except (ValueError, RuntimeError) as exc:
        return AutomationJobResult(status="failed", detail=str(exc))
    return AutomationJobResult(status="ok", detail=f"synced={synced_count}")


def _run_sentiment_job(runner) -> AutomationJobResult:  # type: ignore[no-untyped-def]
    try:
        runner()
    except (ValueError, EmailNotificationError, RuntimeError) as exc:
        return AutomationJobResult(status="failed", detail=str(exc))
    return AutomationJobResult(status="ok", detail="ETF sentiment job delivered")


def _format_token_usage(usage) -> str:  # type: ignore[no-untyped-def]
    if usage is None:
        return "template-mode"
    return f"{usage.total_tokens} total ({usage.input_tokens} in / {usage.output_tokens} out) via {usage.model}"


def _run_prospect_with_template_fallback():
    original_app_api_key = os.environ.get("APP_OPENAI_API_KEY")
    original_openai_api_key = os.environ.get("OPENAI_API_KEY")
    os.environ["APP_OPENAI_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    try:
        return run_prospecting_job()
    finally:
        if original_app_api_key is None:
            os.environ.pop("APP_OPENAI_API_KEY", None)
        else:
            os.environ["APP_OPENAI_API_KEY"] = original_app_api_key
        if original_openai_api_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = original_openai_api_key


def _run_job_with_timeout(job_name: str, runner, timeout_seconds: int) -> AutomationJobResult:  # type: ignore[no-untyped-def]
    previous_handler = signal.getsignal(signal.SIGALRM)

    def _timeout_handler(signum, frame):  # type: ignore[no-untyped-def]
        raise TimeoutError(f"{job_name} exceeded {timeout_seconds} seconds")

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)
    try:
        return runner()
    except TimeoutError as exc:
        return AutomationJobResult(status="failed", detail=str(exc))
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def build_watchdog_cron_lines(root_dir: Path) -> tuple[str, str]:
    python_bin = root_dir / ".venv" / "bin" / "python"
    log_file = root_dir / "var" / "local_automation.log"
    script_path = root_dir / "scripts" / "run_local_automation.py"
    command = (
        f"cd {root_dir} && PYTHONPATH={root_dir} PYTHONUNBUFFERED=1 {python_bin} {script_path} >> {log_file} 2>&1"
    )
    return (
        f"@reboot {command}",
        f"*/5 * * * * pgrep -f '{script_path}' >/dev/null || ({command})",
    )


def read_heartbeat_from_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    return payload if isinstance(payload, dict) else {}


def is_worker_healthy(path: Path, max_age_seconds: int, now: datetime | None = None) -> bool:
    payload = read_heartbeat_from_file(path)
    generated_at_raw = payload.get("generated_at")
    if not isinstance(generated_at_raw, str):
        return False
    generated_at = datetime.fromisoformat(generated_at_raw)
    reference_now = now or datetime.now(tz=UTC)
    return (reference_now - generated_at).total_seconds() <= max_age_seconds
