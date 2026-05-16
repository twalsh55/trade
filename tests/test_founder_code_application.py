from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from src.application.founder_code import FounderCodeRequest, ListFounderCodeRequestsUseCase, QueueFounderCodeRequestUseCase


class FakeFounderCodeRepository:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str | None, datetime]] = []
        self.requests: list[FounderCodeRequest] = []

    def create_request(self, source_chat_id: str, command_text: str, guidance: str | None, created_at: datetime) -> FounderCodeRequest:
        self.created.append((source_chat_id, command_text, guidance, created_at))
        request = FounderCodeRequest(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            created_at=created_at,
            source_chat_id=source_chat_id,
            command_text=command_text,
            guidance=guidance,
        )
        self.requests.append(request)
        return request

    def list_requests(self, since: datetime | None, limit: int) -> list[FounderCodeRequest]:
        return self.requests[:limit]


def test_queue_founder_code_request_use_case_normalizes_guidance() -> None:
    repository = FakeFounderCodeRepository()
    use_case = QueueFounderCodeRequestUseCase(repository=repository, now=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=UTC))

    request = use_case.execute("123", "/code fix login", "  fix login  ")
    none_guidance_request = use_case.execute("123", "/code", "   ")

    assert request.guidance == "fix login"
    assert none_guidance_request.guidance is None


def test_list_founder_code_requests_use_case_delegates() -> None:
    repository = FakeFounderCodeRepository()
    repository.requests.append(
        FounderCodeRequest(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            created_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
            source_chat_id="123",
            command_text="/code fix login",
            guidance="fix login",
        )
    )
    use_case = ListFounderCodeRequestsUseCase(repository=repository)

    requests = use_case.execute(since=datetime(2026, 5, 16, 11, 0, tzinfo=UTC), limit=10)

    assert requests[0].command_text == "/code fix login"
