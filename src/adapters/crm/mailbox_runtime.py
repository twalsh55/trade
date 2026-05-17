from __future__ import annotations

from datetime import UTC, datetime

from src.adapters.crm.runtime import build_lead_follow_up_repository, build_mailbox_provider_from_env
from src.adapters.persistence.runtime import build_user_repository
from src.application.crm import SyncMailboxConnectionUseCase


def run_scheduled_mailbox_sync_job() -> tuple[int, int, int]:
    repository = build_lead_follow_up_repository()
    user_repository = build_user_repository()
    mailbox_provider = build_mailbox_provider_from_env()

    if user_repository is None or not callable(getattr(repository, "list_mailbox_connection_user_ids", None)):
        return (0, 0, 0)

    synced_connections = 0
    synced_threads = 0
    watch_ready_connections = 0
    user_ids = repository.list_mailbox_connection_user_ids()
    for user_id in user_ids:
        user = user_repository.get_user_by_id(user_id)
        if user is None:
            continue
        connections = repository.list_mailbox_connections(user)
        for connection in connections:
            if connection.connection_mode != "oauth" or connection.status != "connected" or not connection.background_sync_enabled:
                continue
            result = SyncMailboxConnectionUseCase(
                repository=repository,
                now=lambda: datetime.now(tz=UTC),
                mailbox_provider=mailbox_provider,
            ).execute(user, connection.id)
            synced_connections += 1
            synced_threads += result.synced_threads
            if result.connection.watch_status == "active":
                watch_ready_connections += 1
    return synced_connections, synced_threads, watch_ready_connections
