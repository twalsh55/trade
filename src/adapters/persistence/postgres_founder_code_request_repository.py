from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg import connect
from psycopg.rows import dict_row

from src.adapters.persistence.postgres_user_repository import _parse_uuid
from src.application.founder_code import FounderCodeRequest


class PostgresFounderCodeRequestRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def ensure_schema(self) -> None:
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS founder_code_request (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        created_at TIMESTAMPTZ NOT NULL,
                        source_chat_id TEXT NOT NULL,
                        command_text TEXT NOT NULL,
                        guidance TEXT
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS founder_code_request_created_at_idx
                    ON founder_code_request (created_at ASC)
                    """
                )
            connection.commit()

    def create_request(
        self,
        source_chat_id: str,
        command_text: str,
        guidance: str | None,
        created_at: datetime,
    ) -> FounderCodeRequest:
        with connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO founder_code_request (
                        created_at,
                        source_chat_id,
                        command_text,
                        guidance
                    )
                    VALUES (
                        %(created_at)s,
                        %(source_chat_id)s,
                        %(command_text)s,
                        %(guidance)s
                    )
                    RETURNING
                        id,
                        created_at,
                        source_chat_id,
                        command_text,
                        guidance
                    """,
                    {
                        "created_at": created_at,
                        "source_chat_id": source_chat_id,
                        "command_text": command_text,
                        "guidance": guidance,
                    },
                )
                row = cursor.fetchone()
            connection.commit()
        if row is None:
            raise RuntimeError("Founder code request insert did not return a row.")
        return _row_to_founder_code_request(row)

    def list_requests(self, since: datetime | None, limit: int) -> list[FounderCodeRequest]:
        query = """
            SELECT
                id,
                created_at,
                source_chat_id,
                command_text,
                guidance
            FROM founder_code_request
        """
        params: dict[str, object] = {"limit": limit}
        if since is not None:
            query += " WHERE created_at > %(since)s"
            params["since"] = since
        query += " ORDER BY created_at ASC LIMIT %(limit)s"
        with connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [_row_to_founder_code_request(row) for row in rows]


def _row_to_founder_code_request(row: dict[str, object]) -> FounderCodeRequest:
    return FounderCodeRequest(
        id=_parse_uuid(row["id"]),
        created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
        source_chat_id=str(row["source_chat_id"]),
        command_text=str(row["command_text"]),
        guidance=row["guidance"] if isinstance(row["guidance"], str) else None,
    )
