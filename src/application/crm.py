from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Callable

from src.application.account import UserDashboardSettings
from src.application.ports import LeadFollowUpRepositoryPort
from src.domain.auth import User
from src.domain.crm import (
    LeadEmailThreadSummary,
    LeadFollowUp,
    LeadFollowUpActionResult,
    LeadFollowUpEmailDraft,
    LeadInboxSummary,
    LeadFollowUpOverview,
    LeadPipelineStageSummary,
    LeadPipelineSummary,
    LeadRelationshipReminder,
    LeadRelationshipSummary,
    LeadTimelineEntry,
    LeadWarmIntroConnection,
)


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
    return f"{_relative_days(latest_upload.occurred_at, current_time)} Brivoly attached new client context from {source}: {summary}"


def _build_upload_follow_through_hint(item: LeadFollowUp, current_time: datetime) -> str:
    latest_upload = _get_latest_upload_entry(item)
    if latest_upload is None:
        return ""

    latest_thread = sorted(item.recent_email_threads, key=lambda thread: thread.last_message_at, reverse=True)[:1]
    if latest_thread:
        thread = latest_thread[0]
        if thread.needs_reply:
            return "Reply while the new client context is still fresh and connect it back to the last thread."
        if thread.waiting_on_contact:
            return "If the thread stays quiet, fold the new client context into your next check-in."

    if item.next_step.strip():
        return f"Best next touch from the new context: {_ensure_sentence(item.next_step)}"

    if latest_upload.occurred_at >= current_time - timedelta(days=2):
        return "A short recap of the new client context would keep momentum up."
    return "Keep the new client context in view the next time you reach back out."


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
            parts.append(upload_follow_through_hint)
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


def _build_reconnect_why_now(item: LeadFollowUp, current_time: datetime) -> str:
    if item.relationship_state == "stale":
        if item.last_meaningful_interaction_at:
            return f"It has been {_relative_days(item.last_meaningful_interaction_at, current_time).lower()} since the last meaningful touch."
        return "This relationship has been quiet long enough that a gentle restart would help."
    if item.relationship_state == "at_risk":
        return item.relationship_timing_nudge or "Momentum is slipping and this relationship could go cold without a light touch."
    if item.relationship_state == "drifting":
        return "The relationship is still warm enough to reopen naturally, but momentum is starting to fade."
    if item.relationship_reminders:
        return _sentence_case(item.relationship_reminders[0].message.rstrip(".")) + "."
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

    if item.next_step.strip():
        return _sentence_case(_ensure_sentence(item.next_step))
    if item.last_meaningful_interaction_at:
        return f"Reference the last meaningful touch from {_relative_days(item.last_meaningful_interaction_at, current_time).lower()} and suggest one small next step."
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

    if item.relationship_context_summary.strip() and item.relationship_context_summary != "Brivoly has not captured enough relationship context yet.":
        return f'Quick angle: "Wanted to circle back while the context around {_truncate_sentence(item.relationship_context_summary, 90)} is still fresh."'
    if item.last_meaningful_interaction_at:
        return f'Quick angle: "Wanted to reconnect after {_relative_days(item.last_meaningful_interaction_at, current_time).lower()} and make the next step easy from here."'
    return 'Quick angle: "Wanted to check back in and see if this is worth picking up again."'


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


def _require_follow_up(items: list[LeadFollowUp], follow_up_id: str) -> LeadFollowUp:
    for item in items:
        if item.id == follow_up_id:
            return item
    raise KeyError(follow_up_id)


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


def _build_email_timeline_summary(message: EmailThreadMessageInput) -> str:
    prefix = "Inbound email" if message.direction == "inbound" else "Outbound email"
    snippet = message.snippet or message.subject
    return f"{prefix}: {message.subject}. {snippet}".strip()


def _upsert_thread_summary(
    existing_threads: tuple[LeadEmailThreadSummary, ...],
    *,
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
        subject=latest_message.subject,
        counterpart_name=counterpart_name or _derive_name_from_email(counterpart_email),
        counterpart_email=counterpart_email,
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
