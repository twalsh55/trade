from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from typing import Any, Callable
from uuid import UUID

from psycopg import connect
from psycopg.rows import dict_row

from src.adapters.crm.in_memory_follow_up_repository import build_seed_follow_ups
from src.domain.auth import User
from src.domain.crm import LeadEmailThreadSummary, LeadFollowUp, LeadRelationshipReminder, LeadTimelineEntry, MailboxConnection


class PostgresLeadFollowUpRepository:
    def __init__(self, database_url: str, now: Callable[[], datetime] | None = None) -> None:
        self.database_url = database_url
        self.now = now or (lambda: datetime.now(tz=UTC))

    def ensure_schema(self) -> None:
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS crm_lead_follow_up (
                        user_id UUID NOT NULL,
                        follow_up_id TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, follow_up_id)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS crm_lead_follow_up_user_updated_idx
                    ON crm_lead_follow_up (user_id, updated_at DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS crm_mailbox_connection (
                        user_id UUID NOT NULL,
                        connection_id TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, connection_id)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS crm_mailbox_connection_user_updated_idx
                    ON crm_mailbox_connection (user_id, updated_at DESC)
                    """
                )
            connection.commit()

    def list_lead_follow_ups(self, user: User) -> list[LeadFollowUp]:
        items = self._list_lead_follow_ups_for_user(user.id)
        if items or user.auth_provider != "anonymous":
            return items
        self.import_lead_follow_ups(user, list(build_seed_follow_ups(self.now())))
        return self._list_lead_follow_ups_for_user(user.id)

    def complete_lead_follow_up(self, user: User, follow_up_id: str, completed_at: datetime) -> None:
        del completed_at
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM crm_lead_follow_up
                    WHERE user_id = %(user_id)s AND follow_up_id = %(follow_up_id)s
                    """,
                    {"user_id": user.id, "follow_up_id": follow_up_id},
                )
                deleted_count = max(0, int(getattr(cursor, "rowcount", 0) or 0))
            connection.commit()
        if deleted_count == 0:
            raise KeyError(follow_up_id)

    def snooze_lead_follow_up(self, user: User, follow_up_id: str, next_follow_up_at: datetime) -> None:
        item = self._require_follow_up(user.id, follow_up_id)
        self._upsert_follow_up(user.id, replace(item, next_follow_up_at=next_follow_up_at))

    def append_note_to_lead_follow_up(self, user: User, follow_up_id: str, note_body: str, noted_at: datetime) -> None:
        item = self._require_follow_up(user.id, follow_up_id)
        entry = LeadTimelineEntry(
            id=f"{follow_up_id}-note-{int(noted_at.timestamp())}",
            occurred_at=noted_at,
            kind="internal_note",
            channel="internal",
            summary=note_body,
        )
        self._upsert_follow_up(
            user.id,
            replace(
                item,
                notes=note_body,
                timeline=(entry, *item.timeline),
            ),
        )

    def import_lead_follow_ups(self, user: User, follow_ups: list[LeadFollowUp]) -> int:
        for item in follow_ups:
            self._upsert_follow_up(user.id, item)
        return len(follow_ups)

    def clear_lead_follow_ups(self, user: User) -> None:
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM crm_lead_follow_up
                    WHERE user_id = %(user_id)s
                    """,
                    {"user_id": user.id},
                )
            connection.commit()

    def list_mailbox_connections(self, user: User) -> list[MailboxConnection]:
        with connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT payload
                    FROM crm_mailbox_connection
                    WHERE user_id = %(user_id)s
                    ORDER BY updated_at DESC, connection_id ASC
                    """,
                    {"user_id": user.id},
                )
                rows = cursor.fetchall()
        return [_payload_to_mailbox_connection(_coerce_payload(row["payload"])) for row in rows]

    def save_mailbox_connection(self, user: User, connection: MailboxConnection) -> MailboxConnection:
        payload = json.dumps(asdict(connection), default=_json_default)
        with connect(self.database_url) as database_connection:
            with database_connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO crm_mailbox_connection (
                        user_id,
                        connection_id,
                        payload,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %(user_id)s,
                        %(connection_id)s,
                        %(payload)s::jsonb,
                        NOW(),
                        NOW()
                    )
                    ON CONFLICT (user_id, connection_id) DO UPDATE
                    SET
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    {
                        "user_id": user.id,
                        "connection_id": connection.id,
                        "payload": payload,
                    },
                )
            database_connection.commit()
        return connection

    def delete_mailbox_connection(self, user: User, connection_id: str) -> None:
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM crm_mailbox_connection
                    WHERE user_id = %(user_id)s AND connection_id = %(connection_id)s
                    """,
                    {"user_id": user.id, "connection_id": connection_id},
                )
                deleted_count = max(0, int(getattr(cursor, "rowcount", 0) or 0))
            connection.commit()
        if deleted_count == 0:
            raise KeyError(connection_id)

    def list_mailbox_connection_user_ids(self) -> list[UUID]:
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT user_id
                    FROM crm_mailbox_connection
                    ORDER BY user_id ASC
                    """
                )
                rows = cursor.fetchall()
        return [UUID(str(row[0])) for row in rows]

    def _list_lead_follow_ups_for_user(self, user_id: UUID) -> list[LeadFollowUp]:
        with connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT payload
                    FROM crm_lead_follow_up
                    WHERE user_id = %(user_id)s
                    ORDER BY updated_at DESC, follow_up_id ASC
                    """,
                    {"user_id": user_id},
                )
                rows = cursor.fetchall()
        return [_payload_to_follow_up(_coerce_payload(row["payload"])) for row in rows]

    def _require_follow_up(self, user_id: UUID, follow_up_id: str) -> LeadFollowUp:
        with connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT payload
                    FROM crm_lead_follow_up
                    WHERE user_id = %(user_id)s AND follow_up_id = %(follow_up_id)s
                    """,
                    {"user_id": user_id, "follow_up_id": follow_up_id},
                )
                row = cursor.fetchone()
        if row is None:
            raise KeyError(follow_up_id)
        return _payload_to_follow_up(_coerce_payload(row["payload"]))

    def _upsert_follow_up(self, user_id: UUID, item: LeadFollowUp) -> None:
        payload = json.dumps(asdict(item), default=_json_default)
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO crm_lead_follow_up (
                        user_id,
                        follow_up_id,
                        payload,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %(user_id)s,
                        %(follow_up_id)s,
                        %(payload)s::jsonb,
                        NOW(),
                        NOW()
                    )
                    ON CONFLICT (user_id, follow_up_id) DO UPDATE
                    SET
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    {
                        "user_id": user_id,
                        "follow_up_id": item.id,
                        "payload": payload,
                    },
                )
            connection.commit()


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Unsupported CRM payload value: {type(value)!r}")


def _coerce_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    raise TypeError(f"Unsupported CRM payload shape: {type(value)!r}")


def _payload_to_follow_up(payload: dict[str, Any]) -> LeadFollowUp:
    return LeadFollowUp(
        id=str(payload["id"]),
        lead_name=str(payload["lead_name"]),
        company_name=str(payload["company_name"]),
        owner_name=str(payload["owner_name"]),
        stage=str(payload["stage"]),
        priority=str(payload["priority"]),
        contact_channel=str(payload["contact_channel"]),
        last_contacted_at=_parse_datetime(payload.get("last_contacted_at")),
        next_follow_up_at=_require_datetime(payload["next_follow_up_at"]),
        next_step=str(payload["next_step"]),
        notes=str(payload["notes"]),
        timeline=tuple(_payload_to_timeline_entry(entry) for entry in payload.get("timeline", [])),
        email_address=str(payload.get("email_address", "")),
        referral_source_name=str(payload.get("referral_source_name", "")),
        birthday=_parse_date(payload.get("birthday")),
        company_milestone_name=str(payload.get("company_milestone_name", "")),
        company_milestone_date=_parse_date(payload.get("company_milestone_date")),
        last_meaningful_interaction_at=_parse_datetime(payload.get("last_meaningful_interaction_at")),
        relationship_health_score=int(payload.get("relationship_health_score", 0) or 0),
        relationship_health_label=str(payload.get("relationship_health_label", "")),
        relationship_state=str(payload.get("relationship_state", "")),
        relationship_timing_nudge=str(payload.get("relationship_timing_nudge", "")),
        relationship_context_summary=str(payload.get("relationship_context_summary", "")),
        relationship_recent_changes_summary=str(payload.get("relationship_recent_changes_summary", "")),
        relationship_recent_upload_summary=str(payload.get("relationship_recent_upload_summary", "")),
        relationship_upload_follow_through_hint=str(payload.get("relationship_upload_follow_through_hint", "")),
        relationship_last_30_days_summary=str(payload.get("relationship_last_30_days_summary", "")),
        relationship_meeting_prep_summary=str(payload.get("relationship_meeting_prep_summary", "")),
        relationship_reconnect_why_now=str(payload.get("relationship_reconnect_why_now", "")),
        relationship_reconnect_next_move=str(payload.get("relationship_reconnect_next_move", "")),
        relationship_reconnect_message_hint=str(payload.get("relationship_reconnect_message_hint", "")),
        dormant=bool(payload.get("dormant", False)),
        relationship_reminders=tuple(_payload_to_reminder(entry) for entry in payload.get("relationship_reminders", [])),
        recent_email_threads=tuple(_payload_to_thread(entry) for entry in payload.get("recent_email_threads", [])),
    )


def _payload_to_timeline_entry(payload: dict[str, Any]) -> LeadTimelineEntry:
    return LeadTimelineEntry(
        id=str(payload["id"]),
        occurred_at=_require_datetime(payload["occurred_at"]),
        kind=str(payload["kind"]),
        channel=str(payload["channel"]),
        summary=str(payload["summary"]),
    )


def _payload_to_reminder(payload: dict[str, Any]) -> LeadRelationshipReminder:
    return LeadRelationshipReminder(
        kind=str(payload["kind"]),
        title=str(payload["title"]),
        message=str(payload["message"]),
        due_at=_parse_datetime(payload.get("due_at")),
    )


def _payload_to_thread(payload: dict[str, Any]) -> LeadEmailThreadSummary:
    return LeadEmailThreadSummary(
        thread_id=str(payload["thread_id"]),
        subject=str(payload["subject"]),
        counterpart_name=str(payload["counterpart_name"]),
        counterpart_email=str(payload["counterpart_email"]),
        last_message_id=str(payload.get("last_message_id", "")),
        last_external_message_id=str(payload.get("last_external_message_id", "")),
        last_message_at=_require_datetime(payload["last_message_at"]),
        last_message_direction=str(payload["last_message_direction"]),
        message_count=int(payload["message_count"]),
        snippet=str(payload["snippet"]),
        needs_reply=bool(payload["needs_reply"]),
        waiting_on_contact=bool(payload["waiting_on_contact"]),
        memory_summary=str(payload.get("memory_summary", "")),
        next_touch_hint=str(payload.get("next_touch_hint", "")),
        open_loop=str(payload.get("open_loop", "")),
        relationship_pulse=str(payload.get("relationship_pulse", "")),
        continuity_span=str(payload.get("continuity_span", "")),
        recent_change_hint=str(payload.get("recent_change_hint", "")),
        carry_forward_hint=str(payload.get("carry_forward_hint", "")),
        unresolved_hint=str(payload.get("unresolved_hint", "")),
        continuity_memory=str(payload.get("continuity_memory", "")),
    )


def _payload_to_mailbox_connection(payload: dict[str, Any]) -> MailboxConnection:
    return MailboxConnection(
        id=str(payload["id"]),
        provider=str(payload["provider"]),
        email_address=str(payload["email_address"]),
        display_name=str(payload.get("display_name", "")),
        status=str(payload.get("status", "")),
        connected_at=_require_datetime(payload["connected_at"]),
        connection_mode=str(payload.get("connection_mode", "manual")),
        external_account_id=str(payload.get("external_account_id", "")),
        access_token=str(payload.get("access_token", "")),
        refresh_token=str(payload.get("refresh_token", "")),
        token_expires_at=_parse_datetime(payload.get("token_expires_at")),
        scope=str(payload.get("scope", "")),
        sync_cursor=str(payload.get("sync_cursor", "")),
        last_sync_at=_parse_datetime(payload.get("last_sync_at")),
        last_sync_status=str(payload.get("last_sync_status", "")),
        last_sync_error=str(payload.get("last_sync_error", "")),
        last_synced_thread_count=int(payload.get("last_synced_thread_count", 0) or 0),
        sent_message_count=int(payload.get("sent_message_count", 0) or 0),
        background_sync_enabled=bool(payload.get("background_sync_enabled", True)),
        last_watch_event_at=_parse_datetime(payload.get("last_watch_event_at")),
        watch_event_count=int(payload.get("watch_event_count", 0) or 0),
    )


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return _require_datetime(value)


def _require_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))
