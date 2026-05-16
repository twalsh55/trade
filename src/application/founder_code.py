from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from src.application.ports import FounderCodeRequestPort


@dataclass(frozen=True, slots=True)
class FounderCodeRequest:
    id: UUID
    created_at: datetime
    source_chat_id: str
    command_text: str
    guidance: str | None


class QueueFounderCodeRequestUseCase:
    def __init__(
        self,
        repository: FounderCodeRequestPort,
        now=lambda: datetime.now(tz=UTC),  # type: ignore[assignment]
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, chat_id: str, command_text: str, guidance: str | None) -> FounderCodeRequest:
        return self.repository.create_request(
            source_chat_id=chat_id,
            command_text=command_text,
            guidance=(guidance or "").strip() or None,
            created_at=self.now(),
        )


class ListFounderCodeRequestsUseCase:
    def __init__(self, repository: FounderCodeRequestPort) -> None:
        self.repository = repository

    def execute(self, since: datetime | None = None, limit: int = 50) -> list[FounderCodeRequest]:
        return self.repository.list_requests(since=since, limit=limit)
