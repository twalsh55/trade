from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from psycopg import OperationalError

from src.adapters.founder_code import runtime as runtime_module
from src.adapters.founder_code.runtime import build_founder_code_request_repository, sync_founder_code_requests_from_api
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
