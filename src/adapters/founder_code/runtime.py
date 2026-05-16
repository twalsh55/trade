from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import httpx
from psycopg import OperationalError

from src.adapters.persistence.postgres_founder_code_request_repository import PostgresFounderCodeRequestRepository


def build_founder_code_request_repository():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for founder code request storage.")
    repository = PostgresFounderCodeRequestRepository(database_url=database_url)
    try:
        repository.ensure_schema()
    except OperationalError as exc:
        raise RuntimeError(
            "Founder code request database is unavailable. Check DATABASE_URL. "
            "Railway internal hostnames such as 'postgres.railway.internal' only work inside Railway's private network."
        ) from exc
    return repository


def sync_founder_code_requests_from_api() -> int:
    base_url = (
        os.getenv("AUTONOMOUS_SYNC_API_BASE_URL", "").strip()
        or "https://api.brivoly.com"
    )
    internal_secret = (
        os.getenv("INTERNAL_CRON_SECRET", "").strip()
        or os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    )
    if not internal_secret:
        raise ValueError("Missing INTERNAL_CRON_SECRET or TELEGRAM_WEBHOOK_SECRET for founder code sync.")

    cursor_path = Path(
        os.getenv("AUTONOMOUS_CODE_CURSOR_FILE", "var/founder_code_cursor.txt").strip()
        or "var/founder_code_cursor.txt"
    )
    inbox_path = Path(
        os.getenv("AUTONOMOUS_CODE_INBOX_FILE", "var/founder_code_inbox.jsonl").strip()
        or "var/founder_code_inbox.jsonl"
    )
    limit = parse_positive_int("AUTONOMOUS_CODE_SYNC_LIMIT", default=25)
    since = _read_cursor(cursor_path)

    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/internal/founder-code-requests",
            headers={"X-Internal-Cron-Secret": internal_secret},
            params={"limit": limit, **({"since": since} if since else {})},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Unable to sync founder code requests from the API.") from exc
    requests = payload.get("requests", [])
    if not isinstance(requests, list):
        raise RuntimeError("Founder code sync returned an invalid payload.")

    if not requests:
        return 0

    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    latest_created_at = since
    with inbox_path.open("a", encoding="utf-8") as handle:
        for item in requests:
            if not isinstance(item, dict):
                continue
            handle.write(json.dumps(item, sort_keys=True))
            handle.write("\n")
            created_at = item.get("created_at")
            if isinstance(created_at, str):
                latest_created_at = created_at
    if latest_created_at:
        cursor_path.parent.mkdir(parents=True, exist_ok=True)
        cursor_path.write_text(latest_created_at, encoding="utf-8")
    return len(requests)


def stage_founder_code_requests_from_inbox() -> int:
    inbox_path = Path(
        os.getenv("AUTONOMOUS_CODE_INBOX_FILE", "var/founder_code_inbox.jsonl").strip()
        or "var/founder_code_inbox.jsonl"
    )
    if not inbox_path.exists():
        return 0

    cursor_path = Path(
        os.getenv("AUTONOMOUS_CODE_PENDING_CURSOR_FILE", "var/founder_code_pending_cursor.txt").strip()
        or "var/founder_code_pending_cursor.txt"
    )
    pending_path = Path(
        os.getenv("AUTONOMOUS_CODE_PENDING_FILE", "var/founder_code_pending.jsonl").strip()
        or "var/founder_code_pending.jsonl"
    )
    latest_path = Path(
        os.getenv("AUTONOMOUS_CODE_LATEST_FILE", "var/founder_code_latest.json").strip()
        or "var/founder_code_latest.json"
    )

    last_seen_id = _read_last_seen_request_id(cursor_path)
    pending_requests = _collect_requests_after_cursor(inbox_path, last_seen_id)
    if not pending_requests:
        return 0

    pending_path.parent.mkdir(parents=True, exist_ok=True)
    with pending_path.open("a", encoding="utf-8") as handle:
        for item in pending_requests:
            handle.write(json.dumps(item, sort_keys=True))
            handle.write("\n")

    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(pending_requests[-1], sort_keys=True, indent=2), encoding="utf-8")
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    cursor_path.write_text(str(pending_requests[-1]["id"]), encoding="utf-8")
    return len(pending_requests)


def launch_next_pending_founder_code_request() -> str:
    pending_path = Path(
        os.getenv("AUTONOMOUS_CODE_PENDING_FILE", "var/founder_code_pending.jsonl").strip()
        or "var/founder_code_pending.jsonl"
    )
    if not pending_path.exists():
        return "no_pending_file"

    pid_path = Path(
        os.getenv("AUTONOMOUS_CODE_EXECUTOR_PID_FILE", "var/founder_code_executor.pid").strip()
        or "var/founder_code_executor.pid"
    )
    active_path = Path(
        os.getenv("AUTONOMOUS_CODE_ACTIVE_FILE", "var/founder_code_active.json").strip()
        or "var/founder_code_active.json"
    )
    cursor_path = Path(
        os.getenv("AUTONOMOUS_CODE_EXECUTION_CURSOR_FILE", "var/founder_code_execution_cursor.txt").strip()
        or "var/founder_code_execution_cursor.txt"
    )
    if _is_executor_running(pid_path):
        return "already_running"

    last_seen_id = _read_last_seen_request_id(cursor_path)
    pending_requests = _collect_requests_after_cursor(pending_path, last_seen_id)
    if not pending_requests:
        return "no_new_requests"

    next_request = pending_requests[0]
    request_id = str(next_request["id"])
    codex_bin = shutil.which("codex")
    if not codex_bin:
        raise RuntimeError("Codex CLI is not installed or not on PATH.")

    workspace_root = Path(
        os.getenv("AUTONOMOUS_CODE_WORKSPACE_ROOT", os.getcwd()).strip()
        or os.getcwd()
    )
    run_dir = Path(
        os.getenv("AUTONOMOUS_CODE_RUN_DIR", "var/founder_code_runs").strip()
        or "var/founder_code_runs"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / f"{request_id}.last_message.txt"
    log_path = run_dir / f"{request_id}.log"

    prompt = _build_codex_exec_prompt(next_request)
    command = [
        codex_bin,
        "exec",
        "-C",
        str(workspace_root),
        "-a",
        "never",
        "-s",
        "danger-full-access",
        "-o",
        str(output_path),
        prompt,
    ]

    with log_path.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=workspace_root,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            text=True,
        )

    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(process.pid), encoding="utf-8")
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(
        json.dumps(
            {
                "id": request_id,
                "source_chat_id": next_request.get("source_chat_id"),
                "command_text": next_request.get("command_text"),
                "guidance": next_request.get("guidance"),
                "pid": process.pid,
                "started_at": datetime.now().isoformat(),
                "log_path": str(log_path),
                "output_path": str(output_path),
            },
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    cursor_path.write_text(request_id, encoding="utf-8")
    return f"launched={request_id} pid={process.pid}"


def parse_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _read_cursor(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        return None
    datetime.fromisoformat(value)
    return value


def _read_last_seen_request_id(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _collect_requests_after_cursor(inbox_path: Path, last_seen_id: str | None) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen_cursor = last_seen_id is None
    parsed_items: list[dict[str, object]] = []
    for raw_line in inbox_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        parsed_items.append(item)
        if not seen_cursor:
            if item_id == last_seen_id:
                seen_cursor = True
            continue
        items.append(item)
    if last_seen_id is not None and not seen_cursor:
        return parsed_items
    return items


def _is_executor_running(pid_path: Path) -> bool:
    pid_value = _read_last_seen_request_id(pid_path)
    if pid_value is None:
        return False
    try:
        pid = int(pid_value)
    except ValueError:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _build_codex_exec_prompt(request: dict[str, object]) -> str:
    guidance = str(request.get("guidance") or request.get("command_text") or "").strip()
    command_text = str(request.get("command_text") or "").strip()
    source_chat_id = str(request.get("source_chat_id") or "").strip()
    return (
        "Remote founder instruction received through the local automation bridge.\n"
        f"Source: {source_chat_id or 'unknown'}\n"
        f"Command: {command_text or '(missing)'}\n"
        f"Guidance: {guidance or '(missing)'}\n\n"
        "Work in the current repository and follow AGENTS.md. "
        "Implement the requested change if it does not harm the current goal of building a narrow, profitable CRM wedge. "
        "Run relevant tests, commit and push coherent change sets, and deploy when appropriate. "
        "If the request conflicts with the product goal or cannot be completed safely, explain that clearly instead of forcing a change."
    )
