from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Callable

from src.application.account import UserDashboardSettings
from src.application.ports import LeadFollowUpRepositoryPort, MailboxProviderPort
from src.domain.auth import User
from src.domain.crm import (
    LeadAmbientMemorySummary,
    CalendarConnection,
    LeadEmailThreadSummary,
    LeadFollowUp,
    LeadFollowUpActionResult,
    LeadFollowUpEmailDraft,
    LeadInboxSummary,
    LeadFollowUpOverview,
    MailboxConnection,
    MailboxSendResult,
    MailboxSyncResult,
    LeadPipelineStageSummary,
    LeadPipelineSummary,
    LeadRelationshipReminder,
    LeadRelationshipSummary,
    LeadTimelineEntry,
    LeadWarmIntroConnection,
    MailboxThreadSnapshot,
)


@dataclass(frozen=True)
class CalendarEventInput:
    event_id: str
    title: str
    starts_at: datetime
    attendee_emails: tuple[str, ...]
    notes: str = ""


class GetLeadFollowUpOverviewUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User) -> LeadFollowUpOverview:
        current_time = self.now()
        items = [_enrich_follow_up(item, current_time) for item in self.repository.list_lead_follow_ups(user)]
        ordered_items = sorted(items, key=lambda item: (item.next_follow_up_at, item.priority != "high", item.lead_name))
        current_date = current_time.date()
        mailbox_connections = (
            self.repository.list_mailbox_connections(user)
            if callable(getattr(self.repository, "list_mailbox_connections", None))
            else []
        )
        calendar_connections = (
            self.repository.list_calendar_connections(user)
            if callable(getattr(self.repository, "list_calendar_connections", None))
            else []
        )

        return LeadFollowUpOverview(
            generated_at=current_time,
            total_open=len(ordered_items),
            due_today=sum(1 for item in ordered_items if item.next_follow_up_at.date() == current_date),
            overdue=sum(1 for item in ordered_items if item.next_follow_up_at < current_time),
            high_priority=sum(1 for item in ordered_items if item.priority == "high"),
            items=[_clone_follow_up(item) for item in ordered_items],
            relationship_summary=_build_relationship_summary(ordered_items),
            pipeline_summary=_build_pipeline_summary(ordered_items, current_time),
            inbox_summary=_build_inbox_summary(ordered_items, current_time),
            ambient_memory_summary=_build_ambient_memory_summary(mailbox_connections, calendar_connections),
        )


def _clone_follow_up(item: LeadFollowUp) -> LeadFollowUp:
    return replace(item)


MEANINGFUL_TIMELINE_KINDS = frozenset({"call", "inbound", "outreach", "proposal", "qualification", "negotiation", "referral", "meeting", "email"})


def _enrich_follow_up(item: LeadFollowUp, current_time: datetime) -> LeadFollowUp:
    enriched_threads = _build_enriched_threads(item, current_time)
    item_with_threads = replace(item, recent_email_threads=tuple(enriched_threads))
    last_meaningful = _resolve_last_meaningful_interaction(item)
    health_score = _compute_relationship_health_score(item, last_meaningful, current_time)
    dormant = _is_dormant(item, last_meaningful, current_time)
    reminders = _build_relationship_reminders(item_with_threads, last_meaningful, current_time)
    item_with_reminders = replace(item_with_threads, relationship_reminders=tuple(reminders))
    recent_upload_summary = _build_recent_upload_summary(item_with_reminders, current_time)
    item_with_upload_context = replace(item_with_reminders, relationship_recent_upload_summary=recent_upload_summary)
    upload_follow_through_hint = _build_upload_follow_through_hint(item_with_upload_context, current_time)
    context_summary = _build_relationship_context_summary(item_with_upload_context)
    timing_nudge = _build_relationship_timing_nudge(item_with_upload_context, current_time)
    recent_changes_summary = _build_recent_changes_summary(item_with_upload_context, current_time)
    last_30_days_summary = _build_last_30_days_summary(item_with_upload_context, current_time)
    meeting_prep_summary = _build_meeting_prep_summary(item_with_upload_context, current_time)
    upcoming_meeting_at, upcoming_meeting_label, upcoming_meeting_source = _resolve_upcoming_meeting(item_with_upload_context, current_time)
    reconnect_why_now = _build_reconnect_why_now(item_with_upload_context, current_time)
    reconnect_next_move = _build_reconnect_next_move(item_with_upload_context, current_time)
    reconnect_message_hint = _build_reconnect_message_hint(item_with_upload_context, current_time)
    return replace(
        item_with_upload_context,
        last_meaningful_interaction_at=last_meaningful,
        relationship_health_score=health_score,
        relationship_health_label=_health_label(health_score),
        relationship_state=_relationship_state(health_score, dormant, item_with_upload_context, current_time),
        relationship_timing_nudge=timing_nudge,
        relationship_context_summary=context_summary,
        relationship_recent_changes_summary=recent_changes_summary,
        relationship_recent_upload_summary=recent_upload_summary,
        relationship_upload_follow_through_hint=upload_follow_through_hint,
        relationship_last_30_days_summary=last_30_days_summary,
        relationship_meeting_prep_summary=meeting_prep_summary,
        relationship_upcoming_meeting_at=upcoming_meeting_at,
        relationship_upcoming_meeting_label=upcoming_meeting_label,
        relationship_upcoming_meeting_source=upcoming_meeting_source,
        relationship_reconnect_why_now=reconnect_why_now,
        relationship_reconnect_next_move=reconnect_next_move,
        relationship_reconnect_message_hint=reconnect_message_hint,
        dormant=dormant,
    )


def _build_enriched_threads(item: LeadFollowUp, current_time: datetime) -> list[LeadEmailThreadSummary]:
    return [
        replace(
            thread,
            memory_summary=_build_thread_memory_summary(item, thread),
            next_touch_hint=_build_thread_next_touch_hint(item, thread, current_time),
            open_loop=_build_thread_open_loop(item, thread),
            relationship_pulse=_build_thread_relationship_pulse(item, thread, current_time),
            continuity_span=_build_thread_continuity_span(thread, current_time),
            recent_change_hint=_build_thread_recent_change_hint(item, thread, current_time),
            carry_forward_hint=_build_thread_carry_forward_hint(item, thread),
            unresolved_hint=_build_thread_unresolved_hint(item, thread),
            continuity_memory=_build_thread_continuity_memory(item, thread),
        )
        for thread in item.recent_email_threads
    ]


def _build_thread_memory_summary(item: LeadFollowUp, thread: LeadEmailThreadSummary) -> str:
    snippet = thread.snippet.strip().rstrip(".")
    if snippet:
        return _sentence_case(snippet) + "."
    if item.next_step.strip():
        return f"This thread is tied to {_sentence_case(item.next_step.strip().rstrip('.'))}."
    if item.notes.strip():
        return _sentence_case(item.notes.strip().rstrip(".")) + "."
    return "Brivoly has not captured enough thread context yet."


def _build_thread_next_touch_hint(item: LeadFollowUp, thread: LeadEmailThreadSummary, current_time: datetime) -> str:
    counterpart = thread.counterpart_name or item.lead_name
    if thread.needs_reply:
        return f"Reply to {counterpart}. The latest message has been waiting since {_relative_days(thread.last_message_at, current_time).lower()}."
    if thread.waiting_on_contact:
        return f"Hold steady for now. You sent the latest note {_relative_days(thread.last_message_at, current_time).lower()}."
    if thread.last_message_at <= current_time - timedelta(days=7):
        return f"Reconnect with {counterpart}. This thread has gone quiet."
    if item.next_step.strip():
        return _sentence_case(item.next_step.strip().rstrip(".")) + "."
    return "Keep this relationship warm with a light check-in."


def _build_thread_open_loop(item: LeadFollowUp, thread: LeadEmailThreadSummary) -> str:
    snippet = thread.snippet.strip().rstrip(".")
    if snippet:
        return _sentence_case(snippet) + "."
    if item.next_step.strip():
        return _sentence_case(item.next_step.strip().rstrip(".")) + "."
    upload_context = _build_upload_memory_snippet(item)
    if upload_context:
        return upload_context
    if item.notes.strip():
        return _sentence_case(item.notes.strip().rstrip(".")) + "."
    return "Brivoly has not isolated the open loop here yet."


def _build_thread_relationship_pulse(item: LeadFollowUp, thread: LeadEmailThreadSummary, current_time: datetime) -> str:
    counterpart = thread.counterpart_name or item.lead_name
    if thread.needs_reply:
        return f"{counterpart} replied {_relative_days(thread.last_message_at, current_time).lower()} and this conversation is waiting on you."
    if thread.waiting_on_contact:
        return f"You sent the latest note {_relative_days(thread.last_message_at, current_time).lower()} and are waiting on {counterpart}."
    if thread.last_message_at <= current_time - timedelta(days=7):
        return f"This thread has been quiet since {_relative_days(thread.last_message_at, current_time).lower()}."
    if thread.message_count >= 3:
        return "There is active back-and-forth here, so Brivoly is keeping the context easy to re-enter."
    return "This conversation is still light, but Brivoly is keeping the thread context warm."


def _build_thread_continuity_span(thread: LeadEmailThreadSummary, current_time: datetime) -> str:
    recency = _relative_days(thread.last_message_at, current_time).lower()
    if thread.message_count >= 4:
        return f"{thread.message_count}-message thread, latest turn {recency}."
    if thread.message_count >= 2:
        return f"{thread.message_count}-message exchange, latest turn {recency}."
    return f"Single-message thread, latest turn {recency}."


def _build_thread_recent_change_hint(item: LeadFollowUp, thread: LeadEmailThreadSummary, current_time: datetime) -> str:
    snippet = thread.snippet.strip().rstrip(".")
    if snippet:
        condensed = _truncate_sentence(_sentence_case(snippet), 120)
        if thread.needs_reply:
            return f"New since your last touch: {condensed}"
        if thread.waiting_on_contact:
            return f"Last thing you sent: {condensed}"
        return f"Most recent turn: {condensed}"
    upload_context = _build_upload_memory_snippet(item)
    if upload_context:
        return f"Fresh context around this thread: {upload_context}"
    if item.relationship_recent_changes_summary.strip():
        return _truncate_sentence(item.relationship_recent_changes_summary.strip(), 120)
    if item.next_step.strip():
        return f"Still orbiting: {_ensure_sentence(_sentence_case(item.next_step.strip().rstrip('.')))}"
    return f"Not much shifted here since {_relative_days(thread.last_message_at, current_time).lower()}."


def _build_thread_carry_forward_hint(item: LeadFollowUp, thread: LeadEmailThreadSummary) -> str:
    snippet = thread.snippet.strip().rstrip(".")
    if thread.message_count >= 4 and snippet:
        return f"Carry this forward: {_truncate_sentence(_sentence_case(snippet), 110)}"
    if thread.waiting_on_contact and item.next_step.strip():
        return f"If they reply, pick back up from {_ensure_sentence(item.next_step)}"
    if thread.needs_reply and snippet:
        return f"Ground your reply in {_truncate_sentence(_sentence_case(snippet), 90)}"
    upload_context = _build_upload_memory_snippet(item)
    if upload_context:
        return f"Weave in the new client context: {upload_context}"
    if item.relationship_context_summary.strip() and item.relationship_context_summary != "Brivoly has not captured enough relationship context yet.":
        return f"Carry forward the context around {_truncate_sentence(item.relationship_context_summary, 95)}"
    return ""


def _build_thread_unresolved_hint(item: LeadFollowUp, thread: LeadEmailThreadSummary) -> str:
    snippet = thread.snippet.strip().rstrip(".")
    if thread.needs_reply and snippet:
        return f"Still waiting on your reply about {_truncate_sentence(_sentence_case(snippet), 100)}"
    if thread.needs_reply and item.next_step.strip():
        return f"Your reply should move {_ensure_sentence(item.next_step)}"
    if thread.waiting_on_contact and snippet:
        return f"If they come back, restart from {_truncate_sentence(_sentence_case(snippet), 100)}"
    if thread.waiting_on_contact and item.next_step.strip():
        return f"If they reply, come back to {_ensure_sentence(item.next_step)}"
    if thread.message_count >= 4 and snippet:
        return f"This thread already has enough context around {_truncate_sentence(_sentence_case(snippet), 100)}"
    upload_context = _build_upload_memory_snippet(item)
    if upload_context:
        return f"Keep the new client context tied to this thread: {upload_context}"
    if item.relationship_recent_changes_summary.strip():
        return f"Carry forward what changed: {_truncate_sentence(item.relationship_recent_changes_summary.strip(), 100)}"
    return ""


def _build_thread_continuity_memory(item: LeadFollowUp, thread: LeadEmailThreadSummary) -> str:
    snippet = thread.snippet.strip().rstrip(".")
    if thread.message_count >= 5 and thread.needs_reply and snippet:
        return f"Longer thread to re-enter: they are still circling around {_truncate_sentence(_sentence_case(snippet), 110)} A brief reply can move it forward."
    if thread.message_count >= 4 and thread.waiting_on_contact and snippet:
        return f"Longer thread to re-enter: you already covered {_truncate_sentence(_sentence_case(snippet), 110)} If they come back, restart there instead of rebuilding the thread."
    if thread.message_count >= 4 and item.relationship_recent_changes_summary.strip():
        return f"Thread through-line: {_truncate_sentence(item.relationship_recent_changes_summary.strip(), 130)}"
    if thread.message_count >= 4 and item.next_step.strip():
        return f"Thread through-line: {_truncate_sentence(_ensure_sentence(_sentence_case(item.next_step.strip().rstrip('.'))), 130)}"
    return ""


def _resolve_last_meaningful_interaction(item: LeadFollowUp) -> datetime | None:
    meaningful = [entry.occurred_at for entry in item.timeline if entry.kind in MEANINGFUL_TIMELINE_KINDS]
    candidates = meaningful + ([item.last_contacted_at] if item.last_contacted_at else [])
    if not candidates:
        return None
    return max(candidates)


def _compute_relationship_health_score(item: LeadFollowUp, last_meaningful: datetime | None, current_time: datetime) -> int:
    score = 82
    if last_meaningful is None:
        score -= 22
    else:
        days_since = max(0, int((current_time - last_meaningful).total_seconds() // 86400))
        if days_since <= 3:
            score += 8
        elif days_since <= 7:
            score += 2
        elif days_since <= 14:
            score -= 8
        elif days_since <= 21:
            score -= 18
        else:
            score -= 30

    overdue_days = max(0, int((current_time - item.next_follow_up_at).total_seconds() // 86400))
    if overdue_days >= 14:
        score -= 26
    elif overdue_days >= 7:
        score -= 18
    elif overdue_days >= 1:
        score -= 10
    elif item.next_follow_up_at <= current_time + timedelta(days=2):
        score += 4

    if item.priority == "high":
        score += 3
    if item.referral_source_name.strip():
        score += 4
    if not item.next_step.strip():
        score -= 12
    if item.stage.lower() in {"proposal", "negotiation"}:
        score += 4
    return max(0, min(100, score))


def _health_label(score: int) -> str:
    if score >= 75:
        return "healthy"
    if score >= 50:
        return "watch"
    return "at_risk"


def _relationship_state(
    score: int,
    dormant: bool,
    item: LeadFollowUp,
    current_time: datetime,
) -> str:
    if dormant:
        return "stale"
    if item.next_follow_up_at < current_time - timedelta(days=7) or score < 45:
        return "at_risk"
    if score >= 86:
        return "active"
    if score >= 70:
        return "warm"
    return "drifting"


def _is_dormant(item: LeadFollowUp, last_meaningful: datetime | None, current_time: datetime) -> bool:
    if last_meaningful is None:
        return current_time - item.next_follow_up_at > timedelta(days=7)
    return current_time - last_meaningful >= timedelta(days=21)


def _build_relationship_reminders(
    item: LeadFollowUp,
    last_meaningful: datetime | None,
    current_time: datetime,
) -> list[LeadRelationshipReminder]:
    reminders: list[LeadRelationshipReminder] = []
    if item.referral_source_name.strip() and last_meaningful and current_time - last_meaningful >= timedelta(days=5):
        reminders.append(
            LeadRelationshipReminder(
                kind="referral",
                title="Referral reminder",
                message=f"Send {item.referral_source_name} a quick update before this introduction cools down.",
                due_at=item.next_follow_up_at,
            )
        )
    birthday_due = _next_occurrence(item.birthday, current_time.date())
    if birthday_due and 0 <= (birthday_due - current_time.date()).days <= 30:
        reminders.append(
            LeadRelationshipReminder(
                kind="birthday",
                title="Birthday reminder",
                message=f"{item.lead_name}'s birthday is coming up. Queue a personal touch instead of a generic follow-up.",
                due_at=_combine_date_with_time(birthday_due, current_time),
            )
        )
    milestone_due = _next_occurrence(item.company_milestone_date, current_time.date())
    if milestone_due and 0 <= (milestone_due - current_time.date()).days <= 30:
        milestone_name = item.company_milestone_name.strip() or "Company milestone"
        reminders.append(
            LeadRelationshipReminder(
                kind="company_milestone",
                title=milestone_name,
                message=f"{item.company_name} has {milestone_name.lower()} coming up. Use it as a natural reason to reconnect.",
                due_at=_combine_date_with_time(milestone_due, current_time),
            )
        )
    return reminders


def _build_relationship_context_summary(item: LeadFollowUp) -> str:
    parts: list[str] = []
    upload_context = _build_upload_memory_snippet(item)
    if upload_context:
        parts.append(upload_context.rstrip("."))

    latest_timeline = sorted(
        (entry for entry in item.timeline if entry.kind != "import"),
        key=lambda entry: entry.occurred_at,
        reverse=True,
    )
    if latest_timeline:
        timeline_summary = latest_timeline[0].summary.rstrip(".")
        if not any(timeline_summary.lower() in existing.lower() for existing in parts):
            parts.append(timeline_summary)

    latest_reply_thread = next((thread for thread in sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True) if thread.snippet.strip()), None)
    if latest_reply_thread and latest_reply_thread.snippet.strip():
        snippet = latest_reply_thread.snippet.strip().rstrip(".")
        if not any(snippet.lower() in existing.lower() for existing in parts):
            parts.append(snippet)

    if item.notes.strip() and not _looks_like_imported_context(item.notes):
        note = item.notes.strip().rstrip(".")
        if not any(note.lower() in existing.lower() for existing in parts):
            parts.append(note)

    if not parts:
        return "Brivoly has not captured enough relationship context yet."

    return " ".join(_sentence_case(part) for part in parts[:2])


def _build_relationship_timing_nudge(item: LeadFollowUp, current_time: datetime) -> str:
    latest_thread = sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True)[:1]
    if latest_thread:
        thread = latest_thread[0]
        if thread.needs_reply:
            return f"You have not replied to {thread.counterpart_name or item.lead_name} since {_relative_days(thread.last_message_at, current_time).lower()}."
        if thread.waiting_on_contact:
            return f"You sent the latest note {_relative_days(thread.last_message_at, current_time).lower()} and are waiting on them."

    stage = item.stage.strip().lower()
    if stage == "proposal":
        return f"Proposal sent {_relative_days(item.last_meaningful_interaction_at or item.next_follow_up_at, current_time).lower()} - consider following up."
    if stage == "negotiation":
        return f"This relationship is still in active discussion. A quick check-in now could keep momentum up."
    if item.relationship_state == "stale":
        return f"You have not meaningfully reconnected with {item.lead_name} in a while."
    if item.relationship_state == "at_risk":
        return "This relationship may be going cold."
    if item.relationship_state == "drifting":
        return "A light follow-up soon would help keep momentum."
    if item.relationship_reminders:
        return _sentence_case(item.relationship_reminders[0].message.rstrip(".")) + "."
    return "Things are active here. Brivoly is keeping the context ready."


def _build_recent_changes_summary(item: LeadFollowUp, current_time: datetime) -> str:
    latest_entries = sorted(item.timeline, key=lambda entry: entry.occurred_at, reverse=True)[:2]
    changes: list[str] = []
    latest_upload = _get_latest_upload_entry(item)
    upload_context = _build_upload_memory_snippet(item)

    if latest_upload and upload_context:
        changes.append(
            f"{_relative_days(latest_upload.occurred_at, current_time)} new client context landed: {upload_context}"
        )

    if latest_entries:
        latest = latest_entries[0]
        latest_change = f"{_relative_days(latest.occurred_at, current_time)} Brivoly logged {summarize_timeline_kind(latest.kind)}: {_sentence_case(latest.summary.rstrip('.'))}."
        if latest_change not in changes:
            changes.append(latest_change)

    latest_thread = sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True)[:1]
    if latest_thread:
        thread = latest_thread[0]
        if thread.needs_reply:
            changes.append(f"{_relative_days(thread.last_message_at, current_time)} {thread.counterpart_name or item.lead_name} sent a message that still needs a reply.")
        elif thread.waiting_on_contact:
            changes.append(f"{_relative_days(thread.last_message_at, current_time)} you sent the latest note and are waiting on them.")

    if item.relationship_reminders:
        reminder = item.relationship_reminders[0]
        changes.append(_sentence_case(reminder.message.rstrip(".")) + ".")

    if not changes:
        return "No major relationship changes were captured recently."

    return " ".join(changes[:2])


def _build_recent_upload_summary(item: LeadFollowUp, current_time: datetime) -> str:
    latest_upload = _get_latest_upload_entry(item)
    if latest_upload is None:
        return ""

    source = _describe_upload_source(latest_upload.channel, latest_upload.summary, item.notes)
    summary = _build_upload_memory_snippet(item)
    return f"{_relative_days(latest_upload.occurred_at, current_time)} new client context came in through {source}: {summary}"


def _build_upload_follow_through_hint(item: LeadFollowUp, current_time: datetime) -> str:
    latest_upload = _get_latest_upload_entry(item)
    if latest_upload is None:
        return ""

    latest_thread = sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True)[:1]
    if latest_thread:
        thread = latest_thread[0]
        if thread.needs_reply:
            return "Reply while the new client context is still fresh and tie it back to the last thread."
        if thread.waiting_on_contact:
            return "If the thread stays quiet, use the new client context in your next check-in."

    if item.next_step.strip():
        return f"Best next touch from this new context: {_ensure_sentence(item.next_step)}"

    if item.relationship_state in {"stale", "at_risk", "drifting"}:
        return "Use this new client context as the easiest reason to reopen the relationship while it is still fresh."

    if latest_upload.occurred_at >= current_time - timedelta(days=2):
        return "Use this new client context while it is still fresh and turn it into a short follow-through note."
    return "Keep this new client context in view the next time you reach back out."


def _build_last_30_days_summary(item: LeadFollowUp, current_time: datetime) -> str:
    window_start = current_time - timedelta(days=30)
    recent_entries = [entry for entry in sorted(item.timeline, key=lambda entry: entry.occurred_at, reverse=True) if entry.occurred_at >= window_start]
    if not recent_entries and not item.recent_email_threads:
        return "There has not been much relationship activity in the last 30 days."

    parts: list[str] = []
    if recent_entries:
        latest = recent_entries[0]
        parts.append(f"Over the last 30 days, the most important shift was {_sentence_case(latest.summary.rstrip('.'))}.")
    if len(recent_entries) > 1:
        second = recent_entries[1]
        parts.append(f"Before that, Brivoly logged {summarize_timeline_kind(second.kind)}: {_sentence_case(second.summary.rstrip('.'))}.")
    upload_context = _build_upload_memory_snippet(item)
    if upload_context:
        parts.append(f"Client-shared context recently added: {upload_context}")
        upload_follow_through_hint = _build_upload_follow_through_hint(item, current_time)
        if upload_follow_through_hint:
            parts.append(upload_follow_through_hint)
    latest_thread = sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True)[:1]
    if latest_thread:
        thread = latest_thread[0]
        if thread.snippet.strip():
            parts.append(f"Recent email context: {_sentence_case(thread.snippet.strip().rstrip('.'))}.")
    return " ".join(parts[:3])


def _build_meeting_prep_summary(item: LeadFollowUp, current_time: datetime) -> str:
    latest_entries = sorted(item.timeline, key=lambda entry: entry.occurred_at, reverse=True)[:2]
    thread = sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True)[:1]
    parts: list[str] = []
    upload_context = _build_upload_memory_snippet(item)
    if upload_context:
        parts.append(f"Latest client-sent context: {upload_context}")
        upload_follow_through_hint = _build_upload_follow_through_hint(item, current_time)
        if upload_follow_through_hint:
            parts.append(f"Best use of it right now: {upload_follow_through_hint}")
        if not item.next_step.strip():
            parts.append("Walk in ready to reference the new client context first, then make the next step feel easy.")
    if latest_entries:
        parts.append(f"The last meaningful discussion centered on {_sentence_case(latest_entries[0].summary.rstrip('.'))}.")
    if item.next_step.strip():
        parts.append(f"Best next move: {_sentence_case(item.next_step.rstrip('.'))}.")
    if thread:
        latest_thread = thread[0]
        if latest_thread.needs_reply:
            parts.append(f"You still owe a reply from {_relative_days(latest_thread.last_message_at, current_time).lower()}.")
        elif latest_thread.waiting_on_contact:
            parts.append("You already sent the latest message and are waiting on them.")
    if item.relationship_reminders:
        parts.append(_sentence_case(item.relationship_reminders[0].message.rstrip(".")) + ".")
    if not parts:
        return "Brivoly does not have enough context yet to prep this meeting."
    return " ".join(parts[:3])


MEETING_KEYWORDS = (
    "meeting",
    "call",
    "sync",
    "demo",
    "review",
    "kickoff",
    "walkthrough",
    "check-in",
    "check in",
    "standup",
)


def _resolve_upcoming_meeting(item: LeadFollowUp, current_time: datetime) -> tuple[datetime | None, str, str]:
    if item.next_follow_up_at < current_time:
        return (None, "", "")
    if item.next_follow_up_at > current_time + timedelta(days=14):
        return (None, "", "")

    next_step = item.next_step.strip()
    latest_thread = sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True)[:1]
    latest_entry = sorted(item.timeline, key=lambda entry: entry.occurred_at, reverse=True)[:1]

    thread_subject = latest_thread[0].subject.strip() if latest_thread else ""
    thread_snippet = latest_thread[0].snippet.strip() if latest_thread else ""
    latest_summary = latest_entry[0].summary.strip() if latest_entry else ""
    latest_kind = latest_entry[0].kind.strip().lower() if latest_entry else ""

    if _looks_like_meeting_context(next_step):
        return (
            item.next_follow_up_at,
            _truncate_sentence(_sentence_case(next_step), 120),
            "next step",
        )
    if _looks_like_meeting_context(thread_subject):
        return (
            item.next_follow_up_at,
            _truncate_sentence(_sentence_case(thread_subject), 120),
            "email thread",
        )
    if _looks_like_meeting_context(thread_snippet):
        return (
            item.next_follow_up_at,
            _truncate_sentence(_sentence_case(thread_snippet), 120),
            "email thread",
        )
    if latest_kind in {"meeting", "call"}:
        return (
            item.next_follow_up_at,
            _truncate_sentence(_sentence_case(latest_summary or f"{latest_kind} with {item.lead_name}"), 120),
            "relationship history",
        )
    return (None, "", "")


def _build_reconnect_why_now(item: LeadFollowUp, current_time: datetime) -> str:
    upload_context = _build_upload_memory_snippet(item)
    latest_upload = _get_latest_upload_entry(item)
    if upload_context and latest_upload:
        return f"{_relative_days(latest_upload.occurred_at, current_time)} the client shared new context, which gives you a natural way back in."
    if item.relationship_state == "stale":
        if item.last_meaningful_interaction_at:
            return f"It has been {_relative_days(item.last_meaningful_interaction_at, current_time).lower()} since the last meaningful touch."
        if item.company_name.strip():
            return f"Things have been quiet with {item.company_name} long enough that a light check-in would feel natural."
        return "This relationship has been quiet long enough that a gentle restart would help."
    if item.relationship_state == "at_risk":
        return item.relationship_timing_nudge or "Momentum is slipping and this relationship could go cold without a light touch."
    if item.relationship_state == "drifting":
        return "The relationship is still warm enough to reopen naturally, but momentum is starting to fade."
    if item.relationship_reminders:
        return _sentence_case(item.relationship_reminders[0].message.rstrip(".")) + "."
    latest_entries = sorted(item.timeline, key=lambda entry: entry.occurred_at, reverse=True)[:1]
    if latest_entries:
        return f"Brivoly is still holding context around {_sentence_case(latest_entries[0].summary.rstrip('.'))}, so this does not need to feel like a cold restart."
    if _has_thin_reconnect_context(item):
        if item.company_name.strip():
            return f"A brief check-in with {item.company_name} is still a natural way to reopen this without overexplaining the gap."
        return "A brief low-pressure check-in is still enough to reopen this naturally."
    return "Brivoly is keeping a low-pressure reconnect path ready."


def _build_reconnect_next_move(item: LeadFollowUp, current_time: datetime) -> str:
    if item.relationship_reminders:
        reminder = item.relationship_reminders[0]
        if reminder.kind == "referral":
            return f"Reopen the conversation by referencing {item.referral_source_name} and offering one simple next step."
        if reminder.kind in {"birthday", "company_milestone"}:
            return "Use the upcoming personal or company moment as a natural reason to reach out."

    latest_thread = sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True)[:1]
    if latest_thread:
        thread = latest_thread[0]
        if thread.waiting_on_contact:
            return "Pick back up from the last note you sent and make the reply feel easy."
        if thread.snippet.strip():
            return f"Restart around the last open thread: {_truncate_sentence(thread.snippet.strip(), 120)}"

    upload_context = _build_upload_memory_snippet(item)
    if upload_context:
        return f"Reopen around the fresh client context: {_truncate_sentence(upload_context, 120)}"

    if item.next_step.strip():
        return _sentence_case(_ensure_sentence(item.next_step))
    if item.last_meaningful_interaction_at:
        return f"Reference the last meaningful touch from {_relative_days(item.last_meaningful_interaction_at, current_time).lower()} and suggest one small next step."
    if item.company_name.strip() and _has_thin_reconnect_context(item):
        return f"Send a short check-in to {item.company_name}, keep it easy, and offer one simple next step."
    if item.company_name.strip():
        return f"Keep it light: ask where things stand with {item.company_name} and offer one easy next step."
    latest_entries = sorted(item.timeline, key=lambda entry: entry.occurred_at, reverse=True)[:1]
    if latest_entries:
        return f"Use the last bit of saved context around {_truncate_sentence(latest_entries[0].summary.strip(), 100)} and make the next step easy."
    if _has_thin_reconnect_context(item):
        return "Send a short check-in, acknowledge the gap lightly, and offer one easy way to pick this back up."
    return "Keep it simple: acknowledge the gap, offer context, and make the next move easy."


def _build_reconnect_message_hint(item: LeadFollowUp, current_time: datetime) -> str:
    if item.relationship_reminders:
        reminder = item.relationship_reminders[0]
        if reminder.kind == "referral" and item.referral_source_name.strip():
            return f'Quick angle: "Wanted to follow up on the introduction from {item.referral_source_name} and make the next step easy."'
        if reminder.kind in {"birthday", "company_milestone"}:
            return 'Quick angle: "This felt like a natural moment to check back in and see where things stand."'

    latest_thread = sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True)[:1]
    if latest_thread:
        thread = latest_thread[0]
        if thread.snippet.strip():
            return f'Quick angle: "Wanted to circle back on {_truncate_sentence(thread.snippet.strip(), 90)}"'

    upload_context = _build_upload_memory_snippet(item)
    if upload_context:
        return f'Quick angle: "Wanted to follow up while the new context around {_truncate_sentence(upload_context, 90)} is still fresh."'

    if item.relationship_context_summary.strip() and item.relationship_context_summary != "Brivoly has not captured enough relationship context yet.":
        return f'Quick angle: "Wanted to circle back while the context around {_truncate_sentence(item.relationship_context_summary, 90)} is still fresh."'
    if item.last_meaningful_interaction_at:
        return f'Quick angle: "Wanted to reconnect after {_relative_days(item.last_meaningful_interaction_at, current_time).lower()} and make the next step easy from here."'
    if item.company_name.strip() and _has_thin_reconnect_context(item):
        return f'Quick angle: "Wanted to check in on {item.company_name} and see if now is a good time to pick this back up."'
    if item.company_name.strip():
        return f'Quick angle: "Wanted to check back in on {item.company_name} and see if this is worth picking back up."'
    latest_entries = sorted(item.timeline, key=lambda entry: entry.occurred_at, reverse=True)[:1]
    if latest_entries:
        return f'Quick angle: "Wanted to circle back on {_truncate_sentence(latest_entries[0].summary.strip(), 90)} and see if it makes sense to pick this up again."'
    if _has_thin_reconnect_context(item):
        return 'Quick angle: "Wanted to check in briefly and see if now is a good time to pick this back up."'
    return 'Quick angle: "Wanted to check back in and see if this is worth picking up again."'


def _has_thin_reconnect_context(item: LeadFollowUp) -> bool:
    has_saved_summary = item.relationship_context_summary.strip() and item.relationship_context_summary != "Brivoly has not captured enough relationship context yet."
    return (
        not item.next_step.strip()
        and not item.notes.strip()
        and not item.timeline
        and not item.recent_email_threads
        and not item.relationship_reminders
        and not item.last_meaningful_interaction_at
        and not has_saved_summary
    )


def _looks_like_meeting_context(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in MEETING_KEYWORDS)


def summarize_timeline_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    mapping = {
        "call": "a call",
        "meeting": "a meeting",
        "proposal": "a proposal update",
        "qualification": "a qualification update",
        "negotiation": "a negotiation update",
        "referral": "a referral note",
        "outreach": "an outreach touch",
        "inbound": "an inbound message",
        "email": "an email update",
    }
    return mapping.get(normalized, "an update")


def _get_latest_upload_entry(item: LeadFollowUp) -> LeadTimelineEntry | None:
    return next(
        (
            entry
            for entry in sorted(item.timeline, key=lambda entry: entry.occurred_at, reverse=True)
            if entry.kind == "import" or entry.channel in {"image", "magic_link", "telegram"}
        ),
        None,
    )


def _build_upload_memory_snippet(item: LeadFollowUp) -> str:
    latest_upload = _get_latest_upload_entry(item)
    if latest_upload is None:
        return ""
    summary = _sentence_case(latest_upload.summary.rstrip("."))
    if item.notes.strip() and _looks_like_imported_context(item.notes):
        note = _sentence_case(item.notes.strip().rstrip("."))
        if note.lower() not in summary.lower():
            return f"{summary}. Notes captured: {note}."
        return f"{summary}."
    return _ensure_sentence(summary)


def _describe_upload_source(channel: str, summary: str, notes: str = "") -> str:
    normalized = channel.strip().lower()
    if normalized == "magic_link":
        return "the shared upload link"
    if normalized == "image":
        return "an uploaded image"
    if normalized == "telegram":
        return "a shared mobile upload"
    if normalized in {"csv_upload", "excel_upload", "google_sheets", "sheet"}:
        return "an imported client file"
    summary_lower = summary.lower()
    notes_lower = notes.lower()
    if "magic link" in notes_lower:
        return "the shared upload link"
    if "magic link" in summary_lower:
        return "the shared upload link"
    if "image" in summary_lower or "photo" in summary_lower or any(ext in summary_lower for ext in (".jpg", ".jpeg", ".png", ".heic", ".webp")):
        return "an uploaded image"
    if "sheet" in summary_lower or "csv" in summary_lower or "excel" in summary_lower:
        return "an imported client file"
    return "a recent upload"


def _looks_like_imported_context(value: str) -> bool:
    return value.strip().lower().startswith("imported from ")


def _relative_days(occurred_at: datetime, current_time: datetime) -> str:
    day_delta = max(0, int((current_time - occurred_at).total_seconds() // 86400))
    if day_delta == 0:
        return "Today"
    if day_delta == 1:
        return "Yesterday"
    return f"{day_delta} days ago"


def _sentence_case(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return stripped
    return stripped[0].upper() + stripped[1:]


def _next_occurrence(value: date | None, current_date: date) -> date | None:
    if value is None:
        return None
    try:
        candidate = date(current_date.year, value.month, value.day)
    except ValueError:
        return None
    if candidate < current_date:
        try:
            candidate = date(current_date.year + 1, value.month, value.day)
        except ValueError:
            return None
    return candidate


def _combine_date_with_time(value: date, current_time: datetime) -> datetime:
    return datetime.combine(value, time(hour=9, minute=0), tzinfo=current_time.tzinfo or UTC)


def _build_relationship_summary(items: list[LeadFollowUp]) -> LeadRelationshipSummary:
    active_count = sum(1 for item in items if item.relationship_state == "active")
    warm_count = sum(1 for item in items if item.relationship_state == "warm")
    drifting_count = sum(1 for item in items if item.relationship_state == "drifting")
    stale_count = sum(1 for item in items if item.relationship_state == "stale")
    at_risk_count = sum(1 for item in items if item.relationship_health_label == "at_risk")
    referral_reminder_count = sum(
        1
        for item in items
        for reminder in item.relationship_reminders
        if reminder.kind == "referral"
    )
    milestone_reminder_count = sum(
        1
        for item in items
        for reminder in item.relationship_reminders
        if reminder.kind in {"birthday", "company_milestone"}
    )
    warm_intro_connections = [
        LeadWarmIntroConnection(
            source_name=item.referral_source_name,
            target_lead_id=item.id,
            target_lead_name=item.lead_name,
            target_company_name=item.company_name,
            owner_name=item.owner_name,
        )
        for item in items
        if item.referral_source_name.strip()
    ]
    return LeadRelationshipSummary(
        active_count=active_count,
        warm_count=warm_count,
        drifting_count=drifting_count,
        stale_count=stale_count,
        at_risk_count=at_risk_count,
        referral_reminder_count=referral_reminder_count,
        milestone_reminder_count=milestone_reminder_count,
        warm_intro_connections=warm_intro_connections,
    )


PIPELINE_STAGE_ORDER = {
    "inbox": 5,
    "lead": 10,
    "inbound": 20,
    "qualification": 30,
    "discovery": 40,
    "proposal": 50,
    "negotiation": 60,
    "closed won": 90,
    "closed lost": 100,
}


def _build_pipeline_summary(items: list[LeadFollowUp], current_time: datetime) -> LeadPipelineSummary:
    grouped: dict[str, list[LeadFollowUp]] = {}
    for item in items:
        grouped.setdefault(item.stage, []).append(item)

    ordered_stages = sorted(
        grouped,
        key=lambda stage: (PIPELINE_STAGE_ORDER.get(stage.strip().lower(), 70), stage.strip().lower()),
    )
    stage_summaries = [
        LeadPipelineStageSummary(
            stage=stage,
            lead_count=len(grouped[stage]),
            overdue_count=sum(1 for item in grouped[stage] if item.next_follow_up_at < current_time),
            due_this_week_count=sum(
                1 for item in grouped[stage] if current_time <= item.next_follow_up_at <= current_time + timedelta(days=7)
            ),
            high_priority_count=sum(1 for item in grouped[stage] if item.priority == "high"),
            dormant_count=sum(1 for item in grouped[stage] if item.dormant),
        )
        for stage in ordered_stages
    ]
    return LeadPipelineSummary(stage_summaries=stage_summaries)


def _build_inbox_summary(items: list[LeadFollowUp], current_time: datetime) -> LeadInboxSummary:
    threads = [thread for item in items for thread in item.recent_email_threads]
    return LeadInboxSummary(
        connected_contact_count=sum(1 for item in items if item.email_address.strip()),
        active_thread_count=len(threads),
        needs_reply_count=sum(1 for thread in threads if thread.needs_reply),
        waiting_on_contact_count=sum(1 for thread in threads if thread.waiting_on_contact),
        stale_thread_count=sum(
            1 for thread in threads if thread.last_message_at <= current_time - timedelta(days=5)
        ),
        auto_created_contact_count=sum(1 for item in items if item.stage.strip().lower() == "inbox"),
    )


def _build_ambient_memory_summary(
    mailbox_connections: list[MailboxConnection],
    calendar_connections: list[CalendarConnection],
) -> LeadAmbientMemorySummary:
    active_mailboxes = [
        item for item in mailbox_connections if item.background_sync_enabled and item.status == "connected"
    ]
    active_calendars = [
        item for item in calendar_connections if item.background_sync_enabled and item.status == "connected"
    ]
    paused_mailboxes = [item for item in mailbox_connections if not item.background_sync_enabled]
    paused_calendars = [item for item in calendar_connections if not item.background_sync_enabled]
    attention_mailboxes = [
        item for item in mailbox_connections if item.reauth_required or item.status in {"attention_needed", "needs_reauth"}
    ]
    attention_calendars = [item for item in calendar_connections if item.status not in {"", "connected"}]
    event_ready_mailboxes = [
        item
        for item in active_mailboxes
        if item.watch_status == "active" and item.last_watch_event_at is not None
    ]
    quiet_mailboxes = [
        item
        for item in active_mailboxes
        if item.last_sync_at is not None and not (item.watch_status == "active" and item.last_watch_event_at is not None)
    ]
    warm_calendars = [
        item for item in active_calendars if item.last_event_ingested_at is not None
    ]
    quiet_calendars = [
        item
        for item in active_calendars
        if item.last_sync_at is not None and item.last_event_ingested_at is None
    ]
    warm_source_labels = tuple(
        [
            *[_format_mailbox_source_label(item) for item in event_ready_mailboxes],
            *[_format_calendar_source_label(item) for item in warm_calendars],
        ][:4]
    )
    quiet_source_labels = tuple(
        [
            *[_format_mailbox_source_label(item) for item in quiet_mailboxes],
            *[_format_calendar_source_label(item) for item in quiet_calendars],
        ][:4]
    )
    attention_source_labels = tuple(
        [
            *[_format_mailbox_source_label(item) for item in attention_mailboxes],
            *[_format_calendar_source_label(item) for item in attention_calendars],
        ][:4]
    )
    paused_source_labels = tuple(
        [
            *[_format_mailbox_source_label(item) for item in paused_mailboxes],
            *[_format_calendar_source_label(item) for item in paused_calendars],
        ][:4]
    )
    active_mailbox_count = len(active_mailboxes)
    paused_mailbox_count = len(paused_mailboxes)
    attention_mailbox_count = len(attention_mailboxes)
    event_ready_mailbox_count = len(event_ready_mailboxes)
    active_calendar_count = len(active_calendars)
    paused_calendar_count = len(paused_calendars)
    attention_calendar_count = len(attention_calendars)
    warm_calendar_count = len(warm_calendars)

    active_memory_count = active_mailbox_count + active_calendar_count
    paused_memory_count = paused_mailbox_count + paused_calendar_count
    attention_count = attention_mailbox_count + attention_calendar_count

    suggested_action_route = "/clientos/inbox?connections=all"
    suggested_action_focus = "all"
    suggested_action_kind = "check"
    suggested_action_note = ""
    if active_mailbox_count and not active_calendar_count:
        waiting_action_label = "Open inbox"
        waiting_action_route = "/clientos/inbox?connections=mailbox"
        waiting_action_focus = "mailbox"
        waiting_action_kind = "sync"
        waiting_action_note = "A fresh inbox event should be enough to warm the next thread back up."
    elif active_calendar_count and not active_mailbox_count:
        waiting_action_label = "Check calendars"
        waiting_action_route = "/clientos/inbox?connections=calendar"
        waiting_action_focus = "calendar"
        waiting_action_kind = "ingest"
        waiting_action_note = "A fresh meeting event should be enough to warm the next prep moment back up."
    else:
        waiting_action_label = "Open inbox"
        waiting_action_route = "/clientos/inbox?connections=all"
        waiting_action_focus = "all"
        waiting_action_kind = "check"
        waiting_action_note = "One quick check is enough to see whether new inbox or meeting context has landed."

    if paused_mailbox_count and not paused_calendar_count:
        paused_action_label = "Resume inbox memory"
        paused_action_route = "/clientos/inbox?connections=mailbox"
        paused_action_focus = "mailbox"
        paused_action_kind = "resume"
        paused_action_note = "Turn inbox memory back on when you want Brivoly to quietly hold email context again."
    elif paused_calendar_count and not paused_mailbox_count:
        paused_action_label = "Resume meeting memory"
        paused_action_route = "/clientos/inbox?connections=calendar"
        paused_action_focus = "calendar"
        paused_action_kind = "resume"
        paused_action_note = "Turn meeting memory back on when you want Brivoly to quietly prep upcoming conversations again."
    else:
        paused_action_label = "Resume memory"
        paused_action_route = "/clientos/inbox?connections=all"
        paused_action_focus = "all"
        paused_action_kind = "resume"
        paused_action_note = "Resume one source and Brivoly can start holding more of the relationship context again."

    if attention_mailbox_count and not attention_calendar_count:
        attention_action_label = "Check inboxes"
        attention_action_route = "/clientos/inbox?connections=mailbox"
        attention_action_focus = "mailbox"
        attention_action_kind = "reconnect"
        attention_action_note = "Reconnect one inbox and the thread memory should settle back down."
    elif attention_calendar_count and not attention_mailbox_count:
        attention_action_label = "Check calendars"
        attention_action_route = "/clientos/inbox?connections=calendar"
        attention_action_focus = "calendar"
        attention_action_kind = "check"
        attention_action_note = "Reconnect one calendar and Brivoly can warm meeting context quietly again."
    else:
        attention_action_label = "Check connections"
        attention_action_route = "/clientos/inbox?connections=all"
        attention_action_focus = "all"
        attention_action_kind = "check"
        attention_action_note = "A quick connection check should restore the parts of Brivoly that are losing context."

    if active_mailbox_count and not active_calendar_count:
        disconnected_action_label = "Connect an inbox"
        disconnected_action_route = "/clientos/inbox?connections=mailbox"
        disconnected_action_focus = "mailbox"
        disconnected_action_kind = "connect"
        disconnected_action_note = "One inbox connection is enough for Brivoly to start holding onto email context for you."
    elif active_calendar_count and not active_mailbox_count:
        disconnected_action_label = "Connect a calendar"
        disconnected_action_route = "/clientos/inbox?connections=calendar"
        disconnected_action_focus = "calendar"
        disconnected_action_kind = "connect"
        disconnected_action_note = "One calendar connection is enough for Brivoly to start holding onto meeting context for you."
    else:
        disconnected_action_label = "Connect one source"
        disconnected_action_route = "/clientos/inbox?connections=all"
        disconnected_action_focus = "all"
        disconnected_action_kind = "connect"
        disconnected_action_note = "Connect whichever source you already live in most and Brivoly can start holding onto the relationship for you."

    if attention_count:
        continuity_state = "attention_needed"
        continuity_summary = (
            f"{attention_count} connection{'s' if attention_count != 1 else ''} need attention, "
            f"but Brivoly is still holding context from {active_memory_count} live source{'s' if active_memory_count != 1 else ''} in the background."
            if active_memory_count
            else f"{attention_count} connection{'s' if attention_count != 1 else ''} need attention before Brivoly can hold relationship memory quietly again."
        )
        suggested_action_label = attention_action_label
        suggested_action_route = attention_action_route
        suggested_action_focus = attention_action_focus
        suggested_action_kind = attention_action_kind
        suggested_action_note = attention_action_note
    elif event_ready_mailbox_count or warm_calendar_count:
        continuity_state = "warm"
        continuity_summary = (
            f"Brivoly is quietly holding fresh context from {event_ready_mailbox_count} event-ready inbox{'es' if event_ready_mailbox_count != 1 else ''} "
            f"and {warm_calendar_count} warm calendar{'s' if warm_calendar_count != 1 else ''}."
        )
        suggested_action_label = ""
        suggested_action_route = ""
        suggested_action_focus = ""
        suggested_action_kind = ""
        suggested_action_note = ""
    elif active_memory_count:
        continuity_state = "waiting"
        continuity_summary = (
            f"Background memory is on across {active_mailbox_count} inbox{'es' if active_mailbox_count != 1 else ''} "
            f"and {active_calendar_count} calendar{'s' if active_calendar_count != 1 else ''}, and Brivoly is waiting for the next live context to land."
        )
        suggested_action_label = waiting_action_label
        suggested_action_route = waiting_action_route
        suggested_action_focus = waiting_action_focus
        suggested_action_kind = waiting_action_kind
        suggested_action_note = waiting_action_note
    elif paused_memory_count:
        continuity_state = "paused"
        continuity_summary = (
            f"Background memory is paused on {paused_mailbox_count} inbox{'es' if paused_mailbox_count != 1 else ''} "
            f"and {paused_calendar_count} calendar{'s' if paused_calendar_count != 1 else ''}. Resume one if you want quieter continuity."
        )
        suggested_action_label = paused_action_label
        suggested_action_route = paused_action_route
        suggested_action_focus = paused_action_focus
        suggested_action_kind = paused_action_kind
        suggested_action_note = paused_action_note
    else:
        continuity_state = "disconnected"
        continuity_summary = "Connect an inbox or calendar once and Brivoly can keep more of this context warm for you."
        suggested_action_label = disconnected_action_label
        suggested_action_route = disconnected_action_route
        suggested_action_focus = disconnected_action_focus
        suggested_action_kind = disconnected_action_kind
        suggested_action_note = disconnected_action_note

    return LeadAmbientMemorySummary(
        continuity_state=continuity_state,
        continuity_summary=continuity_summary,
        active_mailbox_count=active_mailbox_count,
        paused_mailbox_count=paused_mailbox_count,
        attention_mailbox_count=attention_mailbox_count,
        event_ready_mailbox_count=event_ready_mailbox_count,
        active_calendar_count=active_calendar_count,
        paused_calendar_count=paused_calendar_count,
        attention_calendar_count=attention_calendar_count,
        warm_calendar_count=warm_calendar_count,
        suggested_action_label=suggested_action_label,
        suggested_action_route=suggested_action_route,
        suggested_action_focus=suggested_action_focus,
        suggested_action_kind=suggested_action_kind,
        suggested_action_note=suggested_action_note,
        warm_source_labels=warm_source_labels,
        quiet_source_labels=quiet_source_labels,
        attention_source_labels=attention_source_labels,
        paused_source_labels=paused_source_labels,
    )


def _format_mailbox_source_label(connection: MailboxConnection) -> str:
    provider_label = "Gmail" if connection.provider == "gmail" else "Outlook"
    return f"{provider_label} · {connection.email_address}"


def _format_calendar_source_label(connection: CalendarConnection) -> str:
    provider_label = "Google Calendar" if connection.provider == "google_calendar" else "Outlook Calendar"
    return f"{provider_label} · {connection.calendar_address}"


class CompleteLeadFollowUpUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User, follow_up_id: str) -> LeadFollowUpActionResult:
        completed_at = self.now()
        self.repository.complete_lead_follow_up(user, follow_up_id, completed_at)
        return LeadFollowUpActionResult(
            follow_up_id=follow_up_id,
            action="complete",
            effective_at=completed_at,
        )


class SnoozeLeadFollowUpUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User, follow_up_id: str, snooze_hours: int) -> LeadFollowUpActionResult:
        effective_at = self.now()
        self.repository.snooze_lead_follow_up(user, follow_up_id, effective_at + timedelta(hours=snooze_hours))
        return LeadFollowUpActionResult(
            follow_up_id=follow_up_id,
            action="snooze",
            effective_at=effective_at,
        )


class AddLeadFollowUpNoteUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User, follow_up_id: str, note_body: str) -> LeadFollowUpActionResult:
        normalized_note = note_body.strip()
        if not normalized_note:
            raise ValueError("Note body is required.")
        effective_at = self.now()
        self.repository.append_note_to_lead_follow_up(user, follow_up_id, normalized_note, effective_at)
        return LeadFollowUpActionResult(
            follow_up_id=follow_up_id,
            action="note",
            effective_at=effective_at,
        )


@dataclass(frozen=True)
class EmailThreadMessageInput:
    message_id: str
    sent_at: datetime
    direction: str
    from_email: str
    from_name: str
    to_emails: tuple[str, ...]
    subject: str
    body_text: str
    snippet: str
    external_message_id: str = ""


class IngestLeadEmailThreadUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(
        self,
        user: User,
        *,
        source: str,
        thread_id: str,
        messages: list[EmailThreadMessageInput],
    ) -> LeadFollowUpOverview:
        normalized_source = source.strip().lower() or "api"
        normalized_thread_id = thread_id.strip()
        if not normalized_thread_id:
            raise ValueError("thread_id is required.")
        if not messages:
            raise ValueError("At least one email message is required.")

        normalized_messages = sorted((_normalize_email_message(message) for message in messages), key=lambda item: item.sent_at)
        counterpart_email, counterpart_name = _resolve_thread_counterpart(user, normalized_messages)
        if not counterpart_email:
            raise ValueError("Brivoly could not identify the external contact for this thread.")

        items = self.repository.list_lead_follow_ups(user)
        lead = _find_follow_up_by_email(items, counterpart_email) or _build_auto_created_follow_up(
            counterpart_email=counterpart_email,
            counterpart_name=counterpart_name,
            owner_name=_resolve_owner_name(user),
            current_time=self.now(),
        )
        updated_lead = _merge_email_thread_into_follow_up(
            lead,
            user=user,
            source=normalized_source,
            thread_id=normalized_thread_id,
            counterpart_email=counterpart_email,
            counterpart_name=counterpart_name,
            messages=normalized_messages,
            current_time=self.now(),
        )
        self.repository.import_lead_follow_ups(user, [updated_lead])
        return GetLeadFollowUpOverviewUseCase(repository=self.repository, now=self.now).execute(user)


class IngestCalendarEventUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(
        self,
        user: User,
        *,
        source: str,
        event: CalendarEventInput,
        connection_id: str | None = None,
    ) -> LeadFollowUpOverview:
        normalized_source = source.strip().lower()
        if normalized_source not in {"google_calendar", "outlook_calendar"}:
            raise ValueError("Unsupported calendar provider.")
        normalized_event_id = event.event_id.strip()
        normalized_title = event.title.strip()
        if not normalized_event_id:
            raise ValueError("event_id is required.")
        if not normalized_title:
            raise ValueError("title is required.")
        attendee_emails = tuple(
            email.strip().lower()
            for email in event.attendee_emails
            if email and email.strip() and "@" in email
        )
        if not attendee_emails:
            raise ValueError("At least one attendee email is required.")
        if connection_id:
            _require_calendar_connection(self.repository.list_calendar_connections(user), connection_id)

        items = self.repository.list_lead_follow_ups(user)
        matched_lead = next((item for item in items if item.email_address.strip().lower() in attendee_emails), None)
        counterpart_email = next(
            (email for email in attendee_emails if not _email_matches_user(user, email)),
            attendee_emails[0],
        )
        lead = matched_lead or _build_auto_created_follow_up(
            counterpart_email=counterpart_email,
            counterpart_name="",
            owner_name=_resolve_owner_name(user),
            current_time=self.now(),
        )
        updated_lead = _merge_calendar_event_into_follow_up(
            lead,
            source=normalized_source,
            event_id=normalized_event_id,
            title=normalized_title,
            starts_at=event.starts_at,
            notes=event.notes,
            current_time=self.now(),
        )
        self.repository.import_lead_follow_ups(user, [updated_lead])

        if connection_id:
            connection = _require_calendar_connection(self.repository.list_calendar_connections(user), connection_id)
            self.repository.save_calendar_connection(
                user,
                replace(
                    connection,
                    last_sync_at=self.now(),
                    last_sync_status="ok",
                    last_sync_error="",
                    last_event_ingested_at=self.now(),
                    health_note="",
                ),
            )

        return GetLeadFollowUpOverviewUseCase(repository=self.repository, now=self.now).execute(user)


class DesignLeadFollowUpEmailUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        settings_loader: Callable[[User], UserDashboardSettings],
    ) -> None:
        self.repository = repository
        self.settings_loader = settings_loader

    def execute(
        self,
        user: User,
        follow_up_id: str,
        *,
        objective: str,
        tone: str,
        length: str,
    ) -> LeadFollowUpEmailDraft:
        normalized_objective = _normalize_email_objective(objective)
        normalized_tone = _normalize_email_tone(tone)
        normalized_length = _normalize_email_length(length)
        lead = _require_follow_up(self.repository.list_lead_follow_ups(user), follow_up_id)
        settings = self.settings_loader(user)
        return _build_email_draft(
            lead,
            user=user,
            settings=settings,
            objective=normalized_objective,
            tone=normalized_tone,
            length=normalized_length,
        )


class ListMailboxConnectionsUseCase:
    def __init__(self, repository: LeadFollowUpRepositoryPort) -> None:
        self.repository = repository

    def execute(self, user: User) -> list[MailboxConnection]:
        return list(self.repository.list_mailbox_connections(user))


class ListCalendarConnectionsUseCase:
    def __init__(self, repository: LeadFollowUpRepositoryPort) -> None:
        self.repository = repository

    def execute(self, user: User) -> list[CalendarConnection]:
        return list(self.repository.list_calendar_connections(user))


class UpdateMailboxConnectionSyncUseCase:
    def __init__(self, repository: LeadFollowUpRepositoryPort) -> None:
        self.repository = repository

    def execute(self, user: User, connection_id: str, *, background_sync_enabled: bool) -> MailboxConnection:
        connection = _require_mailbox_connection(self.repository.list_mailbox_connections(user), connection_id)
        return self.repository.save_mailbox_connection(
            user,
            replace(connection, background_sync_enabled=bool(background_sync_enabled)),
        )


class UpdateCalendarConnectionSyncUseCase:
    def __init__(self, repository: LeadFollowUpRepositoryPort) -> None:
        self.repository = repository

    def execute(self, user: User, connection_id: str, *, background_sync_enabled: bool) -> CalendarConnection:
        connection = _require_calendar_connection(self.repository.list_calendar_connections(user), connection_id)
        return self.repository.save_calendar_connection(
            user,
            replace(connection, background_sync_enabled=bool(background_sync_enabled)),
        )


class DisconnectMailboxConnectionUseCase:
    def __init__(self, repository: LeadFollowUpRepositoryPort) -> None:
        self.repository = repository

    def execute(self, user: User, connection_id: str) -> None:
        _require_mailbox_connection(self.repository.list_mailbox_connections(user), connection_id)
        self.repository.delete_mailbox_connection(user, connection_id)


class ConnectCalendarUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User, *, provider: str, calendar_address: str, display_name: str) -> CalendarConnection:
        normalized_provider = provider.strip().lower()
        if normalized_provider not in {"google_calendar", "outlook_calendar"}:
            raise ValueError("Unsupported calendar provider.")
        normalized_address = calendar_address.strip().lower()
        if "@" not in normalized_address:
            raise ValueError("A valid calendar address is required.")
        normalized_name = display_name.strip() or _derive_name_from_email(normalized_address)
        existing = next(
            (
                item
                for item in self.repository.list_calendar_connections(user)
                if item.provider == normalized_provider and item.calendar_address.lower() == normalized_address
            ),
            None,
        )
        connection = CalendarConnection(
            id=existing.id if existing else f"calendar-{normalized_provider}-{hashlib.sha1(normalized_address.encode('utf-8')).hexdigest()[:10]}",
            provider=normalized_provider,
            calendar_address=normalized_address,
            display_name=normalized_name,
            status="connected",
            connected_at=existing.connected_at if existing else self.now(),
            last_sync_at=existing.last_sync_at if existing else None,
            last_sync_status=existing.last_sync_status if existing else "",
            last_sync_error=existing.last_sync_error if existing else "",
            last_event_ingested_at=existing.last_event_ingested_at if existing else None,
            background_sync_enabled=existing.background_sync_enabled if existing else True,
            health_note=existing.health_note if existing else "",
        )
        return self.repository.save_calendar_connection(user, connection)


class DisconnectCalendarConnectionUseCase:
    def __init__(self, repository: LeadFollowUpRepositoryPort) -> None:
        self.repository = repository

    def execute(self, user: User, connection_id: str) -> None:
        _require_calendar_connection(self.repository.list_calendar_connections(user), connection_id)
        self.repository.delete_calendar_connection(user, connection_id)


class EraseRelationshipMemoryUseCase:
    def __init__(self, repository: LeadFollowUpRepositoryPort) -> None:
        self.repository = repository

    def execute(self, user: User, *, scope: str) -> None:
        normalized_scope = scope.strip().lower()
        if normalized_scope not in {"relationship_memory", "all_memory"}:
            raise ValueError("Unsupported privacy erase scope.")
        self.repository.clear_lead_follow_ups(user)
        if normalized_scope == "all_memory":
            for connection in list(self.repository.list_mailbox_connections(user)):
                self.repository.delete_mailbox_connection(user, connection.id)
            for connection in list(self.repository.list_calendar_connections(user)):
                self.repository.delete_calendar_connection(user, connection.id)


class ProcessMailboxWatchEventUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
        mailbox_provider: MailboxProviderPort | None = None,
    ) -> None:
        self.repository = repository
        self.now = now
        self.mailbox_provider = mailbox_provider

    def execute(
        self,
        user: User,
        *,
        provider: str,
        connection_id: str | None = None,
        external_account_id: str | None = None,
        email_address: str | None = None,
    ) -> MailboxSyncResult:
        normalized_provider = provider.strip().lower()
        normalized_connection_id = (connection_id or "").strip()
        normalized_external_account_id = (external_account_id or "").strip()
        normalized_email_address = (email_address or "").strip().lower()
        connections = [
            item
            for item in self.repository.list_mailbox_connections(user)
            if item.provider == normalized_provider and item.connection_mode == "oauth" and item.status == "connected"
        ]
        if normalized_connection_id:
            connection = _require_mailbox_connection(connections, normalized_connection_id)
        else:
            connection = next(
                (
                    item
                    for item in connections
                    if (
                        normalized_external_account_id
                        and item.external_account_id.strip() == normalized_external_account_id
                    )
                    or (
                        normalized_email_address
                        and item.email_address.strip().lower() == normalized_email_address
                    )
                ),
                None,
            )
            if connection is None:
                raise KeyError(normalized_external_account_id or normalized_email_address or normalized_provider)

        result = SyncMailboxConnectionUseCase(
            repository=self.repository,
            now=self.now,
            mailbox_provider=self.mailbox_provider,
        ).execute(user, connection.id)
        saved_connection = self.repository.save_mailbox_connection(
            user,
            replace(
                result.connection,
                last_watch_event_at=self.now(),
                watch_event_count=result.connection.watch_event_count + 1,
                last_sync_status="watch_event",
                last_sync_error="",
            ),
        )
        return replace(result, connection=saved_connection)


MAILBOX_PROVIDERS = {"gmail", "outlook"}


class BeginMailboxOAuthUseCase:
    def __init__(self, mailbox_provider: MailboxProviderPort) -> None:
        self.mailbox_provider = mailbox_provider

    def execute(self, *, provider: str, redirect_uri: str, state: str) -> str:
        normalized_provider = provider.strip().lower()
        if normalized_provider not in MAILBOX_PROVIDERS:
            raise ValueError("Unsupported mailbox provider.")
        if not redirect_uri.strip():
            raise ValueError("redirect_uri is required.")
        if not state.strip():
            raise ValueError("state is required.")
        return self.mailbox_provider.build_authorization_url(normalized_provider, redirect_uri.strip(), state.strip())


class CompleteMailboxOAuthUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        mailbox_provider: MailboxProviderPort,
    ) -> None:
        self.repository = repository
        self.mailbox_provider = mailbox_provider

    def execute(self, user: User, *, provider: str, code: str, redirect_uri: str) -> MailboxConnection:
        normalized_provider = provider.strip().lower()
        if normalized_provider not in MAILBOX_PROVIDERS:
            raise ValueError("Unsupported mailbox provider.")
        existing = next(
            (
                item
                for item in self.repository.list_mailbox_connections(user)
                if item.provider == normalized_provider and item.connection_mode == "oauth"
            ),
            None,
        )
        connection = self.mailbox_provider.exchange_authorization_code(
            normalized_provider,
            code.strip(),
            redirect_uri.strip(),
            existing_connection=existing,
        )
        try:
            connection = self.mailbox_provider.ensure_watch_subscription(connection)
        except RuntimeError:
            # Leave the mailbox connected even if watch renewal is not available yet.
            pass
        return self.repository.save_mailbox_connection(
            user,
            replace(connection, background_sync_enabled=existing.background_sync_enabled if existing else True),
        )


class ConnectMailboxUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
    ) -> None:
        self.repository = repository
        self.now = now

    def execute(self, user: User, *, provider: str, email_address: str, display_name: str) -> MailboxConnection:
        normalized_provider = provider.strip().lower()
        if normalized_provider not in MAILBOX_PROVIDERS:
            raise ValueError("Unsupported mailbox provider.")
        normalized_email = email_address.strip().lower()
        if "@" not in normalized_email:
            raise ValueError("A valid mailbox email address is required.")
        normalized_name = display_name.strip() or _derive_name_from_email(normalized_email)
        existing = next(
            (
                item
                for item in self.repository.list_mailbox_connections(user)
                if item.provider == normalized_provider and item.email_address.lower() == normalized_email
            ),
            None,
        )
        connection = MailboxConnection(
            id=existing.id if existing else f"mailbox-{normalized_provider}-{hashlib.sha1(normalized_email.encode('utf-8')).hexdigest()[:10]}",
            provider=normalized_provider,
            email_address=normalized_email,
            display_name=normalized_name,
            status="connected",
            connected_at=existing.connected_at if existing else self.now(),
            last_sync_at=existing.last_sync_at if existing else None,
            last_sync_status=existing.last_sync_status if existing else "",
            last_sync_error=existing.last_sync_error if existing else "",
            last_synced_thread_count=existing.last_synced_thread_count if existing else 0,
            sent_message_count=existing.sent_message_count if existing else 0,
            background_sync_enabled=existing.background_sync_enabled if existing else True,
        )
        return self.repository.save_mailbox_connection(user, connection)


class EnsureMailboxWatchUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        mailbox_provider: MailboxProviderPort | None,
    ) -> None:
        self.repository = repository
        self.mailbox_provider = mailbox_provider

    def execute(self, user: User, connection_id: str) -> MailboxConnection:
        connection = _require_mailbox_connection(self.repository.list_mailbox_connections(user), connection_id)
        if connection.connection_mode != "oauth":
            return self.repository.save_mailbox_connection(
                user,
                replace(
                    connection,
                    watch_status="inactive",
                    health_note="Provider watch coverage only applies to OAuth-linked mailboxes.",
                ),
            )
        if self.mailbox_provider is None:
            raise ValueError("Mailbox provider integration is not configured.")
        try:
            updated = self.mailbox_provider.ensure_watch_subscription(connection)
        except RuntimeError as exc:
            failed = _mark_mailbox_attention_needed(connection, str(exc))
            self.repository.save_mailbox_connection(user, failed)
            raise
        return self.repository.save_mailbox_connection(user, updated)


class SyncMailboxConnectionUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
        mailbox_provider: MailboxProviderPort | None = None,
    ) -> None:
        self.repository = repository
        self.now = now
        self.mailbox_provider = mailbox_provider

    def execute(self, user: User, connection_id: str) -> MailboxSyncResult:
        current_time = self.now()
        connection = _require_mailbox_connection(self.repository.list_mailbox_connections(user), connection_id)
        before_ids = {item.id for item in self.repository.list_lead_follow_ups(user)}
        synced_threads = 0
        updated_connection = connection

        if connection.connection_mode == "oauth":
            if self.mailbox_provider is None:
                raise ValueError("Mailbox provider integration is not configured.")
            try:
                hydrated_connection = self.mailbox_provider.refresh_connection(connection)
                if _mailbox_watch_renewal_due(hydrated_connection):
                    hydrated_connection = self.mailbox_provider.ensure_watch_subscription(hydrated_connection)
                thread_snapshots = self.mailbox_provider.pull_thread_updates(hydrated_connection, max_results=10)
            except RuntimeError as exc:
                failed_connection = _mark_mailbox_attention_needed(connection, str(exc))
                self.repository.save_mailbox_connection(user, failed_connection)
                raise
            updated_connection = hydrated_connection
            for snapshot in thread_snapshots:
                if not snapshot.messages:
                    continue
                synced_threads += 1
                IngestLeadEmailThreadUseCase(repository=self.repository, now=self.now).execute(
                    user,
                    source=snapshot.source,
                    thread_id=snapshot.thread_id,
                    messages=[
                        EmailThreadMessageInput(
                            message_id=message.message_id,
                            external_message_id=message.external_message_id,
                            sent_at=message.sent_at,
                            direction=message.direction,
                            from_email=message.from_email,
                            from_name=message.from_name,
                            to_emails=message.to_emails,
                            subject=message.subject,
                            body_text=message.body_text,
                            snippet=message.snippet,
                        )
                        for message in snapshot.messages
                    ],
                )
            sync_cursor = _resolve_mailbox_sync_cursor(thread_snapshots, current_time)
            updated_connection = replace(
                updated_connection,
                sync_cursor=sync_cursor,
            )
        else:
            candidates = [item for item in self.repository.list_lead_follow_ups(user) if item.email_address.strip()]
            if candidates:
                for index, lead in enumerate(candidates[:2]):
                    synced_threads += 1
                    direction = "inbound" if index == 0 else "outbound"
                    subject = _build_mailbox_sync_subject(lead)
                    message = EmailThreadMessageInput(
                        message_id=f"{connection.id}-{lead.id}-{current_time.strftime('%Y%m%d%H')}-{direction}",
                        external_message_id=f"<{connection.id}-{lead.id}-{current_time.strftime('%Y%m%d%H')}-{direction}@brivoly.local>",
                        sent_at=current_time - timedelta(minutes=index * 12),
                        direction=direction,
                        from_email=lead.email_address.strip().lower() if direction == "inbound" else connection.email_address,
                        from_name=lead.lead_name if direction == "inbound" else connection.display_name,
                        to_emails=(connection.email_address,) if direction == "inbound" else (lead.email_address.strip().lower(),),
                        subject=subject,
                        body_text=_build_mailbox_sync_body(lead, direction),
                        snippet=_build_mailbox_sync_snippet(lead, direction),
                    )
                    IngestLeadEmailThreadUseCase(repository=self.repository, now=self.now).execute(
                        user,
                        source=connection.provider,
                        thread_id=f"{connection.provider}-{lead.id}",
                        messages=[message],
                    )
            else:
                synced_threads = 1
                sample_domain = connection.email_address.split("@", 1)[1] if "@" in connection.email_address else "client.example"
                IngestLeadEmailThreadUseCase(repository=self.repository, now=self.now).execute(
                    user,
                    source=connection.provider,
                    thread_id=f"{connection.provider}-{connection.id}-welcome",
                    messages=[
                        EmailThreadMessageInput(
                            message_id=f"{connection.id}-{current_time.strftime('%Y%m%d%H')}-welcome",
                            external_message_id=f"<{connection.id}-{current_time.strftime('%Y%m%d%H')}-welcome@brivoly.local>",
                            sent_at=current_time,
                            direction="inbound",
                            from_email=f"hello@{sample_domain}",
                            from_name="New client",
                            to_emails=(connection.email_address,),
                            subject="Quick follow-up",
                            body_text="Wanted to check in and keep this thread moving.",
                            snippet="Wanted to check in and keep this thread moving.",
                        )
                    ],
                )

        overview = GetLeadFollowUpOverviewUseCase(repository=self.repository, now=self.now).execute(user)
        created_contacts = max(0, len({item.id for item in overview.items} - before_ids))
        saved_connection = self.repository.save_mailbox_connection(
            user,
            replace(
                updated_connection,
                last_sync_at=current_time,
                last_sync_status="ok",
                last_sync_error="",
                last_synced_thread_count=synced_threads,
            ),
        )
        return MailboxSyncResult(
            connection=saved_connection,
            synced_threads=synced_threads,
            created_contacts=created_contacts,
            updated_relationships=max(0, synced_threads - created_contacts),
            overview=overview,
        )


class SendLeadFollowUpEmailUseCase:
    def __init__(
        self,
        repository: LeadFollowUpRepositoryPort,
        now: Callable[[], datetime],
        mailbox_provider: MailboxProviderPort | None = None,
    ) -> None:
        self.repository = repository
        self.now = now
        self.mailbox_provider = mailbox_provider

    def execute(
        self,
        user: User,
        follow_up_id: str,
        *,
        subject: str,
        body: str,
        connection_id: str | None = None,
        thread_id: str | None = None,
    ) -> MailboxSendResult:
        normalized_subject = subject.strip()
        normalized_body = body.strip()
        if not normalized_subject:
            raise ValueError("Email subject is required.")
        if not normalized_body:
            raise ValueError("Email body is required.")

        items = self.repository.list_lead_follow_ups(user)
        lead = _require_follow_up(items, follow_up_id)
        if not lead.email_address.strip():
            raise ValueError("This relationship does not have an email address yet.")

        connections = self.repository.list_mailbox_connections(user)
        selected_thread = next((item for item in lead.recent_email_threads if thread_id and item.thread_id == thread_id), None)
        connection = None
        if connection_id:
            connection = _require_mailbox_connection(connections, connection_id)
        elif selected_thread:
            connection = next(
                (
                    item
                    for item in connections
                    if item.status == "connected" and item.provider == selected_thread.source
                ),
                None,
            )
        if connection is None:
            connection = next((item for item in connections if item.status == "connected"), None)
        if connection is None:
            raise ValueError("Connect a mailbox before sending from Brivoly.")
        _ensure_mailbox_connection_sendable(connection)

        current_time = self.now()
        resolved_thread_id = (
            thread_id
            or next(
                (
                    item.thread_id
                    for item in lead.recent_email_threads
                    if item.counterpart_email.strip().lower() == lead.email_address.strip().lower()
                ),
                None,
            )
            or f"{connection.provider}-{lead.id}-outbound"
        )

        if connection.connection_mode == "oauth":
            if self.mailbox_provider is None:
                raise ValueError("Mailbox provider integration is not configured.")
            try:
                receipt = self.mailbox_provider.send_message(
                    connection,
                    to_email=lead.email_address.strip().lower(),
                    to_name=lead.lead_name,
                    subject=normalized_subject,
                    body=normalized_body,
                    thread_id=resolved_thread_id,
                    reply_to_external_message_id=next(
                        (
                            item.last_external_message_id
                            for item in lead.recent_email_threads
                            if item.thread_id == resolved_thread_id and item.last_external_message_id.strip()
                        ),
                        "",
                    ) or None,
                )
            except RuntimeError as exc:
                failed_connection = _mark_mailbox_attention_needed(connection, str(exc))
                self.repository.save_mailbox_connection(user, failed_connection)
                raise
            resolved_thread_id = receipt.thread_id
            outbound_message = receipt.message
            updated_connection = receipt.connection
        else:
            outbound_message = EmailThreadMessageInput(
                message_id=f"{connection.id}-{lead.id}-{current_time.strftime('%Y%m%d%H%M%S')}",
                external_message_id=f"<{connection.id}-{lead.id}-{current_time.strftime('%Y%m%d%H%M%S')}@brivoly.local>",
                sent_at=current_time,
                direction="outbound",
                from_email=connection.email_address,
                from_name=connection.display_name,
                to_emails=(lead.email_address.strip().lower(),),
                subject=normalized_subject,
                body_text=normalized_body,
                snippet=normalized_body[:280],
            )
            updated_connection = connection

        overview = IngestLeadEmailThreadUseCase(repository=self.repository, now=self.now).execute(
            user,
            source=connection.provider,
            thread_id=resolved_thread_id,
            messages=[
                EmailThreadMessageInput(
                    message_id=outbound_message.message_id,
                    external_message_id=outbound_message.external_message_id,
                    sent_at=outbound_message.sent_at,
                    direction=outbound_message.direction,
                    from_email=outbound_message.from_email,
                    from_name=outbound_message.from_name,
                    to_emails=outbound_message.to_emails,
                    subject=outbound_message.subject,
                    body_text=outbound_message.body_text,
                    snippet=outbound_message.snippet,
                )
            ],
        )
        saved_connection = self.repository.save_mailbox_connection(
            user,
            replace(
                updated_connection,
                last_sync_at=current_time,
                last_sync_status="sent",
                last_sync_error="",
                sent_message_count=connection.sent_message_count + 1,
            ),
        )
        return MailboxSendResult(
            connection=saved_connection,
            follow_up_id=follow_up_id,
            thread_id=resolved_thread_id,
            sent_at=current_time,
            overview=overview,
            continuity_note=receipt.continuity_note if connection.connection_mode == "oauth" else "Saved as an outbound note inside Brivoly's relationship memory.",
        )


def _require_follow_up(items: list[LeadFollowUp], follow_up_id: str) -> LeadFollowUp:
    for item in items:
        if item.id == follow_up_id:
            return item
    raise KeyError(follow_up_id)


def _require_mailbox_connection(items: list[MailboxConnection], connection_id: str | None) -> MailboxConnection:
    normalized_connection_id = (connection_id or "").strip()
    if not normalized_connection_id:
        raise ValueError("mailbox connection id is required.")
    for item in items:
        if item.id == normalized_connection_id:
            return item
    raise KeyError(normalized_connection_id)


def _require_calendar_connection(items: list[CalendarConnection], connection_id: str | None) -> CalendarConnection:
    normalized_connection_id = (connection_id or "").strip()
    if not normalized_connection_id:
        raise ValueError("calendar connection id is required.")
    for item in items:
        if item.id == normalized_connection_id:
            return item
    raise KeyError(normalized_connection_id)


def _ensure_mailbox_connection_sendable(connection: MailboxConnection) -> None:
    if connection.status != "connected":
        if connection.reauth_required:
            raise ValueError("Reconnect this mailbox before sending from Brivoly.")
        raise ValueError("This mailbox needs attention before Brivoly can send from it.")


def _mailbox_watch_renewal_due(connection: MailboxConnection) -> bool:
    if connection.connection_mode != "oauth":
        return False
    if connection.provider == "gmail":
        if connection.watch_status != "active" or connection.watch_expires_at is None:
            return True
        return connection.watch_expires_at <= datetime.now(tz=UTC) + timedelta(hours=1)
    return False


def _mark_mailbox_attention_needed(connection: MailboxConnection, reason: str) -> MailboxConnection:
    normalized_reason = reason.strip() or "Mailbox provider action is required."
    lower_reason = normalized_reason.lower()
    needs_reauth = any(
        token in lower_reason
        for token in ("token", "oauth", "auth", "unauthorized", "forbidden", "expired", "refresh", "reconnect")
    )
    status = "needs_reauth" if needs_reauth else "attention_needed"
    return replace(
        connection,
        status=status,
        reauth_required=needs_reauth,
        last_sync_status=status,
        last_sync_error=normalized_reason,
        health_note=normalized_reason,
        watch_status="inactive" if needs_reauth else connection.watch_status,
    )


def _resolve_mailbox_sync_cursor(thread_snapshots: list[MailboxThreadSnapshot], current_time: datetime) -> str:
    latest_message_at = max(
        (message.sent_at for snapshot in thread_snapshots for message in snapshot.messages),
        default=current_time,
    )
    return latest_message_at.isoformat()


def _build_mailbox_sync_subject(lead: LeadFollowUp) -> str:
    if lead.recent_email_threads:
        return lead.recent_email_threads[0].subject
    if lead.company_name.strip():
        return f"Checking in on {lead.company_name}"
    return f"Checking in with {lead.lead_name}"


def _build_mailbox_sync_body(lead: LeadFollowUp, direction: str) -> str:
    if direction == "inbound":
        return lead.relationship_upload_follow_through_hint or lead.relationship_timing_nudge or lead.next_step or "Wanted to keep this moving."
    return lead.next_step or lead.relationship_reconnect_next_move or "Following up and making the next step easy from here."


def _build_mailbox_sync_snippet(lead: LeadFollowUp, direction: str) -> str:
    if direction == "inbound":
        return (lead.relationship_recent_changes_summary or lead.relationship_context_summary or lead.next_step or "Wanted to keep this moving.")[:220]
    return (lead.next_step or lead.relationship_reconnect_message_hint or "Following up and making the next step easy from here.")[:220]


EMAIL_OBJECTIVES = {"follow_up", "recap", "revive", "close_loop"}
EMAIL_TONES = {"warm", "direct", "confident"}
EMAIL_LENGTHS = {"short", "medium"}
EMAIL_DIRECTIONS = {"inbound", "outbound"}


def _normalize_email_objective(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in EMAIL_OBJECTIVES:
        raise ValueError("Unsupported email objective.")
    return normalized


def _normalize_email_tone(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in EMAIL_TONES:
        raise ValueError("Unsupported email tone.")
    return normalized


def _normalize_email_length(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in EMAIL_LENGTHS:
        raise ValueError("Unsupported email length.")
    return normalized


def _normalize_email_message(message: EmailThreadMessageInput) -> EmailThreadMessageInput:
    message_id = message.message_id.strip()
    if not message_id:
        raise ValueError("Each email message needs a message_id.")
    direction = message.direction.strip().lower()
    if direction not in EMAIL_DIRECTIONS:
        raise ValueError("Each email message needs direction 'inbound' or 'outbound'.")
    from_email = message.from_email.strip().lower()
    if not from_email:
        raise ValueError("Each email message needs a from_email value.")
    to_emails = tuple(item.strip().lower() for item in message.to_emails if item.strip())
    if not to_emails:
        raise ValueError("Each email message needs at least one recipient email.")
    return EmailThreadMessageInput(
        message_id=message_id,
        external_message_id=message.external_message_id.strip(),
        sent_at=message.sent_at,
        direction=direction,
        from_email=from_email,
        from_name=message.from_name.strip(),
        to_emails=to_emails,
        subject=message.subject.strip() or "(no subject)",
        body_text=message.body_text.strip(),
        snippet=(message.snippet.strip() or message.body_text.strip())[:280],
    )


def _resolve_thread_counterpart(user: User, messages: list[EmailThreadMessageInput]) -> tuple[str, str]:
    user_email = (user.email or "").strip().lower()
    latest_message = messages[-1]
    if latest_message.direction == "inbound":
        return latest_message.from_email, latest_message.from_name or _derive_name_from_email(latest_message.from_email)
    for email in latest_message.to_emails:
        if email != user_email:
            return email, latest_message.from_name or _derive_name_from_email(email)
    return "", ""


def _email_matches_user(user: User, email_address: str) -> bool:
    return bool(user.email and user.email.strip().lower() == email_address.strip().lower())


def _find_follow_up_by_email(items: list[LeadFollowUp], email_address: str) -> LeadFollowUp | None:
    for item in items:
        if item.email_address.strip().lower() == email_address:
            return item
    return None


def _resolve_owner_name(user: User) -> str:
    return user.display_name or user.given_name or user.email or "Brivoly"


def _build_auto_created_follow_up(
    *,
    counterpart_email: str,
    counterpart_name: str,
    owner_name: str,
    current_time: datetime,
) -> LeadFollowUp:
    lead_name = counterpart_name or _derive_name_from_email(counterpart_email)
    return LeadFollowUp(
        id=f"lead-email-{hashlib.sha1(counterpart_email.encode('utf-8')).hexdigest()[:10]}",
        lead_name=lead_name,
        company_name=_derive_company_from_email(counterpart_email),
        owner_name=owner_name,
        email_address=counterpart_email,
        stage="Inbox",
        priority="medium",
        contact_channel="email",
        last_contacted_at=None,
        next_follow_up_at=current_time,
        next_step=f"Review the latest email thread with {lead_name}.",
        notes="Auto-created from inbox activity so Brivoly can keep the relationship in memory.",
        timeline=(),
    )


def _merge_email_thread_into_follow_up(
    lead: LeadFollowUp,
    *,
    user: User,
    source: str,
    thread_id: str,
    counterpart_email: str,
    counterpart_name: str,
    messages: list[EmailThreadMessageInput],
    current_time: datetime,
) -> LeadFollowUp:
    existing_timeline_ids = {entry.id for entry in lead.timeline}
    new_entries = []
    for message in messages:
        entry_id = f"email-{message.message_id}"
        if entry_id in existing_timeline_ids:
            continue
        new_entries.append(
            LeadTimelineEntry(
                id=entry_id,
                occurred_at=message.sent_at,
                kind="email",
                channel=source,
                summary=_build_email_timeline_summary(message),
            )
        )

    all_entries = tuple(sorted((*lead.timeline, *new_entries), key=lambda entry: entry.occurred_at, reverse=True))
    latest_message = messages[-1]
    thread_history = _upsert_thread_summary(
        lead.recent_email_threads,
        source=source,
        thread_id=thread_id,
        counterpart_email=counterpart_email,
        counterpart_name=counterpart_name,
        messages=messages,
        new_message_count=len(new_entries),
    )
    next_follow_up_at, next_step, priority = _resolve_follow_up_from_latest_email(
        lead=lead,
        counterpart_name=counterpart_name or lead.lead_name,
        latest_message=latest_message,
        current_time=current_time,
    )
    latest_snippet = latest_message.snippet or latest_message.body_text or lead.notes
    latest_contacted_at = latest_message.sent_at
    normalized_email_address = lead.email_address.strip() or counterpart_email
    if not normalized_email_address:
        normalized_email_address = counterpart_email
    return replace(
        lead,
        lead_name=lead.lead_name or counterpart_name or _derive_name_from_email(counterpart_email),
        company_name=lead.company_name or _derive_company_from_email(counterpart_email),
        email_address=normalized_email_address,
        stage=lead.stage if lead.stage.strip() and lead.stage.strip().lower() != "lead" else "Inbox",
        contact_channel="email",
        last_contacted_at=latest_contacted_at,
        next_follow_up_at=next_follow_up_at,
        next_step=next_step,
        notes=latest_snippet[:240],
        priority=priority,
        timeline=all_entries,
        recent_email_threads=thread_history,
    )


def _merge_calendar_event_into_follow_up(
    lead: LeadFollowUp,
    *,
    source: str,
    event_id: str,
    title: str,
    starts_at: datetime,
    notes: str,
    current_time: datetime,
) -> LeadFollowUp:
    entry_id = f"calendar-{event_id}"
    existing_timeline_ids = {entry.id for entry in lead.timeline}
    summary_parts = [f"Upcoming meeting: {title.strip().rstrip('.')}"]
    cleaned_notes = notes.strip().rstrip(".")
    if cleaned_notes:
        summary_parts.append(cleaned_notes)
    event_entry = LeadTimelineEntry(
        id=entry_id,
        occurred_at=starts_at,
        kind="meeting",
        channel=source,
        summary=". ".join(summary_parts) + ".",
    )
    all_entries = lead.timeline if entry_id in existing_timeline_ids else tuple(sorted((*lead.timeline, event_entry), key=lambda entry: entry.occurred_at, reverse=True))
    should_promote_meeting = starts_at >= current_time
    next_follow_up_at = starts_at if should_promote_meeting else lead.next_follow_up_at
    next_step = f"Prepare for {title.strip().rstrip('.')}." if should_promote_meeting else lead.next_step
    priority = "high" if should_promote_meeting and starts_at <= current_time + timedelta(days=2) else lead.priority
    last_contacted_at = max(lead.last_contacted_at or starts_at, starts_at) if starts_at <= current_time else lead.last_contacted_at
    return replace(
        lead,
        stage=lead.stage if lead.stage.strip() and lead.stage.strip().lower() != "lead" else "Meeting",
        contact_channel="calendar",
        last_contacted_at=last_contacted_at,
        next_follow_up_at=next_follow_up_at,
        next_step=next_step,
        notes=cleaned_notes[:240] if cleaned_notes else lead.notes,
        priority=priority,
        timeline=all_entries,
    )


def _build_email_timeline_summary(message: EmailThreadMessageInput) -> str:
    prefix = "Inbound email" if message.direction == "inbound" else "Outbound email"
    snippet = message.snippet or message.subject
    return f"{prefix}: {message.subject}. {snippet}".strip()


def _upsert_thread_summary(
    existing_threads: tuple[LeadEmailThreadSummary, ...],
    *,
    source: str,
    thread_id: str,
    counterpart_email: str,
    counterpart_name: str,
    messages: list[EmailThreadMessageInput],
    new_message_count: int,
) -> tuple[LeadEmailThreadSummary, ...]:
    latest_message = messages[-1]
    existing_by_id = {item.thread_id: item for item in existing_threads}
    existing = existing_by_id.get(thread_id)
    thread = LeadEmailThreadSummary(
        thread_id=thread_id,
        source=source,
        subject=latest_message.subject,
        counterpart_name=counterpart_name or _derive_name_from_email(counterpart_email),
        counterpart_email=counterpart_email,
        last_message_id=latest_message.message_id,
        last_external_message_id=latest_message.external_message_id,
        last_message_at=latest_message.sent_at,
        last_message_direction=latest_message.direction,
        message_count=(existing.message_count if existing else 0) + new_message_count if existing else len(messages),
        snippet=latest_message.snippet or latest_message.subject,
        needs_reply=latest_message.direction == "inbound",
        waiting_on_contact=latest_message.direction == "outbound",
    )
    existing_by_id[thread_id] = thread
    return tuple(sorted(existing_by_id.values(), key=lambda item: item.last_message_at, reverse=True)[:5])


def _resolve_follow_up_from_latest_email(
    *,
    lead: LeadFollowUp,
    counterpart_name: str,
    latest_message: EmailThreadMessageInput,
    current_time: datetime,
) -> tuple[datetime, str, str]:
    if latest_message.direction == "inbound":
        return (
            current_time,
            f"Reply to {counterpart_name}'s latest email.",
            "high",
        )
    existing_priority = lead.priority if lead.priority in {"high", "medium", "low"} else "medium"
    due_at = max(latest_message.sent_at + timedelta(days=3), current_time)
    return (
        due_at,
        f"Follow up if {counterpart_name} does not reply to the latest thread.",
        existing_priority,
    )


def _derive_name_from_email(email_address: str) -> str:
    local_part = email_address.split("@", 1)[0]
    cleaned = re.sub(r"[._-]+", " ", local_part).strip()
    if not cleaned:
        return email_address
    return " ".join(token.capitalize() for token in cleaned.split())


def _derive_company_from_email(email_address: str) -> str:
    if "@" not in email_address:
        return "Inbox contact"
    domain = email_address.split("@", 1)[1].split(".", 1)[0]
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", domain).strip()
    if not cleaned:
        return "Inbox contact"
    return " ".join(token.capitalize() for token in cleaned.split())


def _build_email_draft(
    lead: LeadFollowUp,
    *,
    user: User,
    settings: UserDashboardSettings,
    objective: str,
    tone: str,
    length: str,
) -> LeadFollowUpEmailDraft:
    sender_name = (
        settings.outbound_sender_name.strip()
        or settings.business_name.strip()
        or user.given_name
        or user.display_name
        or "Your team"
    )
    business_name = settings.business_name.strip() or sender_name
    website = settings.business_website.strip()
    intro = _build_email_intro(lead, business_name=business_name, objective=objective, tone=tone)
    context_line = _build_email_context_line(lead, objective=objective, tone=tone)
    ask_line = _build_email_ask_line(lead, objective=objective, tone=tone)
    close_line = _build_email_close_line(objective=objective, tone=tone)
    signoff = _build_email_signoff(sender_name=sender_name, website=website)
    body_lines = [
        f"Hi {lead.lead_name},",
        "",
        intro,
        context_line,
        ask_line,
    ]
    if length == "medium":
        proof_line = _build_email_proof_line(lead, business_name=business_name)
        if proof_line:
            body_lines.extend(["", proof_line])
    body_lines.extend(["", close_line, "", signoff])
    rationale = _build_email_rationale(lead, objective=objective, tone=tone, business_name=business_name)
    return LeadFollowUpEmailDraft(
        follow_up_id=lead.id,
        objective=objective,
        tone=tone,
        length=length,
        subject=_build_email_subject(lead, objective=objective),
        body="\n".join(line for line in body_lines if line is not None).strip(),
        rationale=rationale,
    )


def _build_email_subject(lead: LeadFollowUp, *, objective: str) -> str:
    if objective == "recap":
        return f"Recap and next steps for {lead.company_name}"
    if objective == "revive":
        return f"{lead.lead_name}, should we restart this?"
    if objective == "close_loop":
        return f"Should I close the loop on {lead.company_name}?"
    if lead.stage.lower() == "proposal":
        return f"Quick follow-up on the {lead.company_name} proposal"
    return f"Quick follow-up for {lead.company_name}"


def _build_email_intro(lead: LeadFollowUp, *, business_name: str, objective: str, tone: str) -> str:
    stage = lead.stage.lower()
    if objective == "recap":
        return f"Thanks again for the conversation around {lead.company_name}. I wanted to send a crisp recap from our side at {business_name} so the next step is easy."
    if objective == "revive":
        return f"I wanted to bring this back to the top of your inbox from {business_name} in case the timing is better now for {lead.company_name}."
    if objective == "close_loop":
        return f"I did not want this to linger without a clear next step, so I wanted to check in one last time."
    if tone == "direct":
        return f"I wanted to follow up from {business_name} on where things stand for {lead.company_name}."
    if tone == "confident":
        return f"I think there is still a strong fit here, especially given what you shared about {stage} and the current workflow."
    return f"I wanted to follow up from {business_name} while the context is still fresh and make the next step simple."


def _build_email_context_line(lead: LeadFollowUp, *, objective: str, tone: str) -> str:
    latest_timeline = lead.timeline[0].summary.strip() if lead.timeline else ""
    notes = lead.notes.strip()
    evidence = latest_timeline or notes
    if objective == "close_loop":
        return "If this is not a priority right now, that is completely fine. I would just rather close the loop cleanly than keep nudging you."
    if not evidence:
        if objective == "recap":
            return f"My current read is that the important next move is: {_ensure_sentence(lead.next_step)}"
        return f"The main thing still on my list is: {_ensure_sentence(lead.next_step)}"
    snippet = _truncate_sentence(evidence, 180)
    if tone == "confident":
        return f"You mentioned: {snippet} That still feels like the right place to keep the thread moving."
    return f"You mentioned: {snippet}"


def _build_email_ask_line(lead: LeadFollowUp, *, objective: str, tone: str) -> str:
    next_step = _ensure_sentence(lead.next_step)
    if objective == "recap":
        return f"From here, I suggest we {next_step}"
    if objective == "revive":
        return f"If this is still relevant, we can pick it back up by {next_step}"
    if objective == "close_loop":
        return "If you want to keep it moving, just reply and I will take it from there."
    if tone == "direct":
        return f"If you are still interested, the cleanest next move is to {next_step}"
    if tone == "confident":
        return f"The fastest way to keep momentum is to {next_step}"
    return f"If helpful, the next move from here is to {next_step}"


def _build_email_proof_line(lead: LeadFollowUp, *, business_name: str) -> str:
    if lead.stage.lower() == "proposal":
        return f"I can also keep the rollout light on your side if that helps {lead.company_name} move faster."
    if "spreadsheet" in lead.notes.lower():
        return f"We can keep this lightweight and work with the spreadsheet-first process your team already uses at {lead.company_name}."
    return f"My goal is to keep this straightforward and low-lift for {lead.company_name}, not create extra process."


def _build_email_close_line(*, objective: str, tone: str) -> str:
    if objective == "close_loop":
        return "Either way, a quick yes, no, or later would be perfect."
    if tone == "direct":
        return "A quick reply is enough and I can handle the rest."
    if tone == "confident":
        return "If the timing works, I can keep this moving without much back-and-forth."
    return "Happy to keep it easy from here."


def _build_email_signoff(*, sender_name: str, website: str) -> str:
    if website:
        return f"Best,\n{sender_name}\n{website}"
    return f"Best,\n{sender_name}"


def _build_email_rationale(lead: LeadFollowUp, *, objective: str, tone: str, business_name: str) -> tuple[str, ...]:
    reasons = [
        f"Anchored the draft to the current CRM stage: {lead.stage}.",
        f"Used the saved sender identity for branding: {business_name}.",
        f"Pulled the call to action from the queued next step: {lead.next_step}.",
    ]
    if objective == "close_loop":
        reasons.append("Softened the ask so the lead can say no without friction.")
    elif objective == "revive":
        reasons.append("Framed the note as a restart instead of pretending the thread stayed active.")
    if tone == "confident":
        reasons.append("Used firmer language to keep momentum without sounding pushy.")
    elif tone == "warm":
        reasons.append("Kept the wording human and low-pressure.")
    return tuple(reasons)


def _ensure_sentence(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "reply with the easiest next step"
    if stripped.endswith((".", "!", "?")):
        return stripped
    return f"{stripped}."


def _truncate_sentence(value: str, limit: int) -> str:
    stripped = " ".join(value.split())
    if len(stripped) <= limit:
        return _ensure_sentence(stripped)
    shortened = stripped[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:-")
    return f"{shortened}..."
