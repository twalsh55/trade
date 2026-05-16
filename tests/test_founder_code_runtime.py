from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from psycopg import OperationalError

from src.adapters.founder_code import runtime as runtime_module
from src.adapters.founder_code.runtime import (
    collect_new_founder_code_progress_messages,
    build_founder_code_request_repository,
    finalize_founder_code_request_if_complete,
    launch_next_pending_founder_code_request,
    parse_positive_int,
    read_active_founder_code_request,
    stage_founder_code_requests_from_inbox,
    sync_founder_code_requests_from_api,
)
from src.adapters.persistence import postgres_founder_code_request_repository as repo_module
from src.adapters.persistence.postgres_founder_code_request_repository import (
    PostgresFounderCodeRequestRepository,
    _row_to_founder_code_request,
)


class FakeCursor:
    def __init__(self, fetchone_result=None, fetchall_result=None) -> None:
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.executed: list[tuple[str, dict[str, object] | None]] = []

    def execute(self, query: str, params: dict[str, object] | None = None) -> None:
        self.executed.append((query, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_row_mapper_converts_database_shape() -> None:
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "created_at": "2026-05-16T10:00:00+00:00",
        "source_chat_id": "123",
        "command_text": "/code fix login",
        "guidance": "fix login",
    }
    request = _row_to_founder_code_request(row)
    assert request.id == UUID("11111111-1111-1111-1111-111111111111")
    assert request.guidance == "fix login"


def test_postgres_founder_code_request_repository_schema_and_round_trip(monkeypatch) -> None:
    ensure_connection = FakeConnection(FakeCursor())
    create_connection = FakeConnection(
        FakeCursor(
            fetchone_result={
                "id": UUID("11111111-1111-1111-1111-111111111111"),
                "created_at": datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
                "source_chat_id": "123",
                "command_text": "/code fix login",
                "guidance": "fix login",
            }
        )
    )
    list_connection = FakeConnection(
        FakeCursor(
            fetchall_result=[
                {
                    "id": UUID("11111111-1111-1111-1111-111111111111"),
                    "created_at": datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
                    "source_chat_id": "123",
                    "command_text": "/code fix login",
                    "guidance": "fix login",
                }
            ]
        )
    )
    calls = [ensure_connection, create_connection, list_connection]
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: calls.pop(0))

    repository = PostgresFounderCodeRequestRepository("postgres://example")
    repository.ensure_schema()
    created = repository.create_request(
        source_chat_id="123",
        command_text="/code fix login",
        guidance="fix login",
        created_at=datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
    )
    listed = repository.list_requests(since=datetime(2026, 5, 16, 9, 0, tzinfo=UTC), limit=5)

    assert len(ensure_connection.cursor_instance.executed) == 3
    assert created.guidance == "fix login"
    assert create_connection.committed is True
    assert listed[0].command_text == "/code fix login"


def test_postgres_founder_code_request_repository_requires_returned_row(monkeypatch) -> None:
    connection = FakeConnection(FakeCursor(fetchone_result=None))
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: connection)
    repository = PostgresFounderCodeRequestRepository("postgres://example")

    with pytest.raises(RuntimeError, match="Founder code request insert did not return a row."):
        repository.create_request(
            source_chat_id="123",
            command_text="/code",
            guidance=None,
            created_at=datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
        )


def test_build_founder_code_request_repository_uses_database_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    captured: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, database_url: str) -> None:
            captured["database_url"] = database_url

        def ensure_schema(self) -> None:
            captured["ensured"] = True

    monkeypatch.setattr(runtime_module, "PostgresFounderCodeRequestRepository", FakeRepository)
    repository = build_founder_code_request_repository()

    assert repository.__class__.__name__ == "FakeRepository"
    assert captured == {"database_url": "postgres://example", "ensured": True}


def test_build_founder_code_request_repository_handles_missing_or_unavailable_db(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        build_founder_code_request_repository()

    monkeypatch.setenv("DATABASE_URL", "postgres://example")

    class FailingRepository:
        def __init__(self, database_url: str) -> None:
            self.database_url = database_url

        def ensure_schema(self) -> None:
            raise OperationalError("down")

    monkeypatch.setattr(runtime_module, "PostgresFounderCodeRequestRepository", FailingRepository)
    with pytest.raises(RuntimeError, match="Founder code request database is unavailable"):
        build_founder_code_request_repository()


def test_sync_founder_code_requests_from_api_writes_inbox_and_cursor(tmp_path, monkeypatch) -> None:
    cursor_path = tmp_path / "cursor.txt"
    inbox_path = tmp_path / "inbox.jsonl"
    monkeypatch.setenv("AUTONOMOUS_CODE_CURSOR_FILE", str(cursor_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_INBOX_FILE", str(inbox_path))
    monkeypatch.setenv("AUTONOMOUS_SYNC_API_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "secret")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "requests": [
                    {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "created_at": "2026-05-16T10:00:00+00:00",
                        "source_chat_id": "123",
                        "command_text": "/code fix login",
                        "guidance": "fix login",
                    }
                ],
            }

    captured: dict[str, object] = {}

    def fake_get(url: str, headers: dict[str, str], params: dict[str, object], timeout: int):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(runtime_module.httpx, "get", fake_get)

    synced_count = sync_founder_code_requests_from_api()

    assert synced_count == 1
    assert captured["url"] == "https://api.example.com/api/internal/founder-code-requests"
    assert json.loads(inbox_path.read_text(encoding="utf-8").strip())["guidance"] == "fix login"
    assert cursor_path.read_text(encoding="utf-8") == "2026-05-16T10:00:00+00:00"


def test_sync_founder_code_requests_from_api_handles_empty_and_invalid_states(tmp_path, monkeypatch) -> None:
    cursor_path = tmp_path / "cursor.txt"
    inbox_path = tmp_path / "inbox.jsonl"
    monkeypatch.setenv("AUTONOMOUS_CODE_CURSOR_FILE", str(cursor_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_INBOX_FILE", str(inbox_path))
    monkeypatch.setenv("AUTONOMOUS_SYNC_API_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("AUTONOMOUS_CODE_SYNC_LIMIT", "3")

    class EmptyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True, "requests": []}

    captured_params: list[dict[str, object]] = []

    def fake_get(*args, **kwargs):
        captured_params.append(kwargs["params"])
        return EmptyResponse()

    monkeypatch.setattr(runtime_module.httpx, "get", fake_get)
    assert sync_founder_code_requests_from_api() == 0
    assert not inbox_path.exists()

    cursor_path.write_text("", encoding="utf-8")
    assert sync_founder_code_requests_from_api() == 0
    cursor_path.write_text("2026-05-16T10:00:00+00:00", encoding="utf-8")
    assert sync_founder_code_requests_from_api() == 0
    assert captured_params[-1]["since"] == "2026-05-16T10:00:00+00:00"

    cursor_path.write_text("not-a-date", encoding="utf-8")
    with pytest.raises(ValueError):
        sync_founder_code_requests_from_api()

    cursor_path.write_text("2026-05-16T10:00:00+00:00", encoding="utf-8")
    monkeypatch.delenv("INTERNAL_CRON_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    with pytest.raises(ValueError, match="Missing INTERNAL_CRON_SECRET"):
        sync_founder_code_requests_from_api()

    monkeypatch.setenv("INTERNAL_CRON_SECRET", "secret")
    monkeypatch.setenv("AUTONOMOUS_CODE_SYNC_LIMIT", "bad")
    with pytest.raises(ValueError, match="AUTONOMOUS_CODE_SYNC_LIMIT must be an integer."):
        sync_founder_code_requests_from_api()

    monkeypatch.setenv("AUTONOMOUS_CODE_SYNC_LIMIT", "0")
    with pytest.raises(ValueError, match="AUTONOMOUS_CODE_SYNC_LIMIT must be greater than zero."):
        sync_founder_code_requests_from_api()


def test_founder_code_parse_positive_int_uses_default_and_validates(monkeypatch) -> None:
    monkeypatch.delenv("AUTONOMOUS_CODE_SYNC_LIMIT", raising=False)
    assert parse_positive_int("AUTONOMOUS_CODE_SYNC_LIMIT", default=25) == 25


def test_stage_founder_code_requests_from_inbox_writes_pending_latest_and_cursor(tmp_path, monkeypatch) -> None:
    inbox_path = tmp_path / "inbox.jsonl"
    pending_path = tmp_path / "pending.jsonl"
    latest_path = tmp_path / "latest.json"
    cursor_path = tmp_path / "pending-cursor.txt"
    inbox_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "1", "command_text": "/code first", "source_chat_id": "123"}),
                json.dumps({"id": "2", "command_text": "/agent csv import", "source_chat_id": "agent:prospect"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTONOMOUS_CODE_INBOX_FILE", str(inbox_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_FILE", str(pending_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_LATEST_FILE", str(latest_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_CURSOR_FILE", str(cursor_path))

    assert stage_founder_code_requests_from_inbox() == 2
    pending_lines = pending_path.read_text(encoding="utf-8").splitlines()
    assert len(pending_lines) == 2
    assert json.loads(latest_path.read_text(encoding="utf-8"))["id"] == "2"
    assert cursor_path.read_text(encoding="utf-8") == "2"

    assert stage_founder_code_requests_from_inbox() == 0

    with inbox_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"id": "3", "command_text": "/code new", "source_chat_id": "123"}))
        handle.write("\n")

    assert stage_founder_code_requests_from_inbox() == 1
    assert pending_path.read_text(encoding="utf-8").splitlines()[-1]
    assert cursor_path.read_text(encoding="utf-8") == "3"


def test_stage_founder_code_requests_from_inbox_recovers_if_cursor_is_stale(tmp_path, monkeypatch) -> None:
    inbox_path = tmp_path / "inbox.jsonl"
    inbox_path.write_text(json.dumps({"id": "11", "command_text": "/code first", "source_chat_id": "123"}) + "\n", encoding="utf-8")
    cursor_path = tmp_path / "pending-cursor.txt"
    cursor_path.write_text("missing-id", encoding="utf-8")
    pending_path = tmp_path / "pending.jsonl"

    monkeypatch.setenv("AUTONOMOUS_CODE_INBOX_FILE", str(inbox_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_FILE", str(pending_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_LATEST_FILE", str(tmp_path / "latest.json"))
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_CURSOR_FILE", str(cursor_path))

    assert stage_founder_code_requests_from_inbox() == 1
    assert json.loads(pending_path.read_text(encoding="utf-8").strip())["id"] == "11"


def test_stage_founder_code_requests_from_inbox_handles_missing_inbox_and_sparse_lines(tmp_path, monkeypatch) -> None:
    inbox_path = tmp_path / "inbox.jsonl"
    monkeypatch.setenv("AUTONOMOUS_CODE_INBOX_FILE", str(inbox_path))
    assert stage_founder_code_requests_from_inbox() == 0

    inbox_path.write_text(
        "\n".join(
            [
                "",
                json.dumps(["not-a-dict"]),
                json.dumps({"command_text": "/code missing id", "source_chat_id": "123"}),
                json.dumps({"id": "22", "command_text": "/code valid", "source_chat_id": "123"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    pending_path = tmp_path / "pending.jsonl"
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_FILE", str(pending_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_LATEST_FILE", str(tmp_path / "latest.json"))
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_CURSOR_FILE", str(tmp_path / "cursor.txt"))

    assert stage_founder_code_requests_from_inbox() == 1
    assert json.loads(pending_path.read_text(encoding="utf-8").strip())["id"] == "22"


def test_launch_next_pending_founder_code_request_launches_one_job(tmp_path, monkeypatch) -> None:
    pending_path = tmp_path / "pending.jsonl"
    pending_path.write_text(
        json.dumps(
            {
                "id": "44",
                "command_text": "/code fix login",
                "guidance": "fix login",
                "source_chat_id": "123",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_FILE", str(pending_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTION_CURSOR_FILE", str(tmp_path / "exec-cursor.txt"))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTOR_PID_FILE", str(tmp_path / "executor.pid"))
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(tmp_path / "active.json"))
    monkeypatch.setenv("AUTONOMOUS_CODE_RUN_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("AUTONOMOUS_CODE_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(runtime_module.shutil, "which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr(runtime_module, "_is_executor_running", lambda path: False)

    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 9876

    def fake_popen(command, cwd, stdout, stderr, stdin, start_new_session, text):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr(runtime_module.subprocess, "Popen", fake_popen)

    result = launch_next_pending_founder_code_request()

    assert result == "launched=44 pid=9876"
    assert captured["command"][0] == "/usr/bin/codex"
    assert "-a" not in captured["command"]
    assert (tmp_path / "executor.pid").read_text(encoding="utf-8") == "9876"
    assert json.loads((tmp_path / "active.json").read_text(encoding="utf-8"))["id"] == "44"
    assert (tmp_path / "exec-cursor.txt").read_text(encoding="utf-8") == "44"


def test_launch_next_pending_founder_code_request_prefers_newest_founder_request(tmp_path, monkeypatch) -> None:
    pending_path = tmp_path / "pending.jsonl"
    pending_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "1", "command_text": "/agent import", "created_at": "2026-05-16T19:41:07+00:00", "source_chat_id": "agent:prospect"}),
                json.dumps({"id": "2", "command_text": "/code older founder", "created_at": "2026-05-16T19:42:00+00:00", "source_chat_id": "8213497118"}),
                json.dumps({"id": "3", "command_text": "/code newest founder", "created_at": "2026-05-16T19:43:00+00:00", "source_chat_id": "8213497118"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_FILE", str(pending_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTION_CURSOR_FILE", str(tmp_path / "exec-cursor.txt"))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTOR_PID_FILE", str(tmp_path / "executor.pid"))
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(tmp_path / "active.json"))
    monkeypatch.setenv("AUTONOMOUS_CODE_RUN_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("AUTONOMOUS_CODE_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(runtime_module.shutil, "which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr(runtime_module, "_is_executor_running", lambda path: False)

    class FakeProcess:
        pid = 9876

    monkeypatch.setattr(runtime_module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    result = launch_next_pending_founder_code_request()

    assert result == "launched=3 pid=9876"
    assert json.loads((tmp_path / "active.json").read_text(encoding="utf-8"))["command_text"] == "/code newest founder"


def test_pick_next_pending_request_handles_invalid_created_at() -> None:
    request = runtime_module._pick_next_pending_request(
        [
            {"id": "1", "source_chat_id": "agent:prospect", "created_at": "not-a-date"},
            {"id": "2", "source_chat_id": "", "created_at": None},
        ]
    )
    assert request["id"] == "1"


def test_launch_next_pending_founder_code_request_handles_idle_and_running_states(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_FILE", str(tmp_path / "missing.jsonl"))
    assert launch_next_pending_founder_code_request() == "no_pending_file"

    pending_path = tmp_path / "pending.jsonl"
    pending_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_FILE", str(pending_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTION_CURSOR_FILE", str(tmp_path / "exec-cursor.txt"))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTOR_PID_FILE", str(tmp_path / "executor.pid"))
    monkeypatch.setattr(runtime_module, "_is_executor_running", lambda path: True)
    assert launch_next_pending_founder_code_request() == "already_running"

    monkeypatch.setattr(runtime_module, "_is_executor_running", lambda path: False)
    assert launch_next_pending_founder_code_request() == "no_new_requests"


def test_read_and_finalize_active_founder_code_request(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(tmp_path / "missing.json"))
    assert read_active_founder_code_request() is None

    active_path = tmp_path / "active.json"
    pid_path = tmp_path / "executor.pid"
    output_path = tmp_path / "output.txt"
    log_path = tmp_path / "run.log"
    result_path = tmp_path / "result.json"
    active_payload = {
        "id": "77",
        "command_text": "/code fix login",
        "source_chat_id": "123",
        "output_path": str(output_path),
        "log_path": str(log_path),
    }
    active_path.write_text(json.dumps(active_payload), encoding="utf-8")
    pid_path.write_text("12345", encoding="utf-8")
    output_path.write_text("Final summary", encoding="utf-8")
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(active_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTOR_PID_FILE", str(pid_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_RESULT_FILE", str(result_path))
    monkeypatch.setattr(runtime_module, "_is_executor_running", lambda path: False)

    assert read_active_founder_code_request()["id"] == "77"
    result = finalize_founder_code_request_if_complete()
    assert result is not None
    assert result["status"] == "finished"
    assert "Final summary" in str(result["summary"])
    assert not active_path.exists()
    assert not pid_path.exists()
    assert json.loads(result_path.read_text(encoding="utf-8"))["id"] == "77"

    active_path.write_text("[]", encoding="utf-8")
    assert read_active_founder_code_request() is None


def test_finalize_active_founder_code_request_handles_running_and_failed_runs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTOR_PID_FILE", str(tmp_path / "missing.pid"))
    monkeypatch.setenv("AUTONOMOUS_CODE_RESULT_FILE", str(tmp_path / "result.json"))
    assert finalize_founder_code_request_if_complete() is None

    active_path = tmp_path / "active.json"
    pid_path = tmp_path / "executor.pid"
    log_path = tmp_path / "run.log"
    active_payload = {
        "id": "88",
        "command_text": "/code fix login",
        "source_chat_id": "123",
        "output_path": str(tmp_path / "missing.txt"),
        "log_path": str(log_path),
    }
    active_path.write_text(json.dumps(active_payload), encoding="utf-8")
    pid_path.write_text("12345", encoding="utf-8")
    log_path.write_text("Traceback-ish output", encoding="utf-8")
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(active_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTOR_PID_FILE", str(pid_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_RESULT_FILE", str(tmp_path / "result.json"))
    monkeypatch.setattr(runtime_module, "_is_executor_running", lambda path: True)
    assert finalize_founder_code_request_if_complete() is None

    monkeypatch.setattr(runtime_module, "_is_executor_running", lambda path: False)
    result = finalize_founder_code_request_if_complete()
    assert result is not None
    assert result["status"] == "failed"
    assert "Traceback-ish output" in str(result["summary"])


def test_finalize_founder_code_request_if_complete_handles_missing_output_and_unreadable_log(tmp_path, monkeypatch) -> None:
    active_path = tmp_path / "active.json"
    pid_path = tmp_path / "executor.pid"
    unreadable_path = tmp_path / "unreadable.log"
    active_path.write_text(
        json.dumps(
            {
                "id": "99",
                "command_text": "/code fix login",
                "source_chat_id": "123",
                "output_path": "",
                "log_path": str(unreadable_path),
            }
        ),
        encoding="utf-8",
    )
    pid_path.write_text("12345", encoding="utf-8")
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(active_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTOR_PID_FILE", str(pid_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_RESULT_FILE", str(tmp_path / "result.json"))
    monkeypatch.setattr(runtime_module, "_is_executor_running", lambda path: False)

    class FakeUnreadablePath:
        def __init__(self, raw: str) -> None:
            self.raw = raw

        def __str__(self) -> str:
            return self.raw

        def exists(self) -> bool:
            return True

        def read_text(self, encoding="utf-8") -> str:
            raise OSError("unreadable")

    monkeypatch.setattr(runtime_module, "Path", lambda value: FakeUnreadablePath(value) if str(value) == str(unreadable_path) else Path(value))
    result = finalize_founder_code_request_if_complete()
    assert result is not None
    assert result["summary"] == ""

    class EmptyPath:
        def __str__(self) -> str:
            return ""

    assert runtime_module._read_optional_text(EmptyPath()) == ""


def test_collect_new_founder_code_progress_messages_reads_json_agent_messages(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "run.log"
    cursor_path = tmp_path / "cursor.txt"
    active_path = tmp_path / "active.json"
    log_path.write_text(
        "\n".join(
            [
                "not-json",
                json.dumps({"type": "thread.started"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "First update"}}),
                json.dumps({"type": "item.completed", "item": {"type": "tool_call", "text": "ignore"}}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Second update"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    active_path.write_text(
        json.dumps({"log_path": str(log_path), "event_cursor_path": str(cursor_path)}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(active_path))

    assert collect_new_founder_code_progress_messages() == ["First update", "Second update"]
    assert cursor_path.read_text(encoding="utf-8") == "2"
    assert collect_new_founder_code_progress_messages() == []


def test_collect_new_founder_code_progress_messages_handles_missing_active_or_log(tmp_path, monkeypatch) -> None:
    active_path = tmp_path / "active.json"
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(active_path))
    assert collect_new_founder_code_progress_messages() == []

    active_path.write_text(
        json.dumps(
            {
                "log_path": str(tmp_path / "missing.log"),
                "event_cursor_path": str(tmp_path / "cursor.txt"),
            }
        ),
        encoding="utf-8",
    )
    assert collect_new_founder_code_progress_messages() == []


def test_collect_new_founder_code_progress_messages_recovers_from_invalid_cursor_and_sparse_events(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "run.log"
    cursor_path = tmp_path / "cursor.txt"
    active_path = tmp_path / "active.json"
    log_path.write_text(
        "\n".join(
            [
                "{bad json",
                json.dumps(["not-a-dict"]),
                json.dumps({"type": "item.completed", "item": "not-a-dict"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Useful update"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cursor_path.write_text("oops", encoding="utf-8")
    active_path.write_text(
        json.dumps({"log_path": str(log_path), "event_cursor_path": str(cursor_path)}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTONOMOUS_CODE_ACTIVE_FILE", str(active_path))

    assert collect_new_founder_code_progress_messages() == ["Useful update"]
    assert cursor_path.read_text(encoding="utf-8") == "1"


def test_extract_agent_messages_from_log_ignores_non_dict_json_payloads(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "run.log"
    log_path.write_text('{"type":"item.completed"}\n', encoding="utf-8")
    real_loads = runtime_module.json.loads
    seen = {"count": 0}

    def fake_loads(raw: str):
        seen["count"] += 1
        if seen["count"] == 1:
            return ["not-a-dict"]
        return real_loads(raw)

    monkeypatch.setattr(runtime_module.json, "loads", fake_loads)
    assert runtime_module._extract_agent_messages_from_log(log_path) == []


def test_launch_next_pending_founder_code_request_requires_codex_binary(tmp_path, monkeypatch) -> None:
    pending_path = tmp_path / "pending.jsonl"
    pending_path.write_text(json.dumps({"id": "55", "command_text": "/code fix", "source_chat_id": "123"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("AUTONOMOUS_CODE_PENDING_FILE", str(pending_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTION_CURSOR_FILE", str(tmp_path / "exec-cursor.txt"))
    monkeypatch.setenv("AUTONOMOUS_CODE_EXECUTOR_PID_FILE", str(tmp_path / "executor.pid"))
    monkeypatch.setattr(runtime_module, "_is_executor_running", lambda path: False)
    monkeypatch.setattr(runtime_module.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="Codex CLI is not installed"):
        launch_next_pending_founder_code_request()


def test_is_executor_running_handles_missing_invalid_and_dead_pid(tmp_path, monkeypatch) -> None:
    pid_path = tmp_path / "executor.pid"
    assert runtime_module._is_executor_running(pid_path) is False

    pid_path.write_text("abc", encoding="utf-8")
    assert runtime_module._is_executor_running(pid_path) is False

    pid_path.write_text("12345", encoding="utf-8")
    monkeypatch.setattr(runtime_module.os, "kill", lambda pid, signal: (_ for _ in ()).throw(OSError("dead")))
    assert runtime_module._is_executor_running(pid_path) is False

    monkeypatch.setattr(runtime_module.os, "kill", lambda pid, signal: None)
    proc_dir = tmp_path / "proc"
    proc_dir.mkdir()
    monkeypatch.setattr(runtime_module, "Path", lambda value: proc_dir / "12345" / "stat" if str(value) == "/proc/12345/stat" else Path(value))
    zombie_stat = proc_dir / "12345" / "stat"
    zombie_stat.parent.mkdir()
    zombie_stat.write_text("12345 (codex) Z 1", encoding="utf-8")
    assert runtime_module._is_executor_running(pid_path) is False

    zombie_stat.write_text("12345 (codex) S 1", encoding="utf-8")
    assert runtime_module._is_executor_running(pid_path) is True


def test_is_executor_running_handles_unreadable_proc_stat(tmp_path, monkeypatch) -> None:
    pid_path = tmp_path / "executor.pid"
    pid_path.write_text("12345", encoding="utf-8")
    monkeypatch.setattr(runtime_module.os, "kill", lambda pid, signal: None)

    class FakeProcPath:
        def exists(self) -> bool:
            return True

        def read_text(self, encoding="utf-8") -> str:
            raise OSError("unreadable")

    monkeypatch.setattr(runtime_module, "Path", lambda value: FakeProcPath() if str(value) == "/proc/12345/stat" else Path(value))
    assert runtime_module._is_executor_running(pid_path) is False


def test_sync_founder_code_requests_from_api_raises_for_http_or_bad_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_CODE_CURSOR_FILE", str(tmp_path / "cursor.txt"))
    monkeypatch.setenv("AUTONOMOUS_CODE_INBOX_FILE", str(tmp_path / "inbox.jsonl"))
    monkeypatch.setenv("AUTONOMOUS_SYNC_API_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "secret")

    monkeypatch.setattr(
        runtime_module.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(runtime_module.httpx.ConnectError("down")),
    )
    with pytest.raises(RuntimeError, match="Unable to sync founder code requests from the API."):
        sync_founder_code_requests_from_api()

    class BadPayloadResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            raise ValueError("bad json")

    monkeypatch.setattr(runtime_module.httpx, "get", lambda *args, **kwargs: BadPayloadResponse())
    with pytest.raises(RuntimeError, match="Unable to sync founder code requests from the API."):
        sync_founder_code_requests_from_api()

    class InvalidListPayloadResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": True, "requests": "bad"}

    monkeypatch.setattr(runtime_module.httpx, "get", lambda *args, **kwargs: InvalidListPayloadResponse())
    with pytest.raises(RuntimeError, match="Founder code sync returned an invalid payload."):
        sync_founder_code_requests_from_api()


def test_sync_founder_code_requests_from_api_skips_non_dict_items(tmp_path, monkeypatch) -> None:
    cursor_path = tmp_path / "cursor.txt"
    inbox_path = tmp_path / "inbox.jsonl"
    monkeypatch.setenv("AUTONOMOUS_CODE_CURSOR_FILE", str(cursor_path))
    monkeypatch.setenv("AUTONOMOUS_CODE_INBOX_FILE", str(inbox_path))
    monkeypatch.setenv("AUTONOMOUS_SYNC_API_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("INTERNAL_CRON_SECRET", "secret")

    class MixedResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "ok": True,
                "requests": [
                    "skip-me",
                    {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "created_at": "2026-05-16T10:00:00+00:00",
                        "source_chat_id": "123",
                        "command_text": "/code fix login",
                        "guidance": "fix login",
                    },
                ],
            }

    monkeypatch.setattr(runtime_module.httpx, "get", lambda *args, **kwargs: MixedResponse())
    assert sync_founder_code_requests_from_api() == 2
    assert inbox_path.read_text(encoding="utf-8").count("\n") == 1
