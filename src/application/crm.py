from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Callable

from src.application.account import UserDashboardSettings
from src.application.ports import LeadFollowUpRepositoryPort
from src.domain.auth import User
from src.domain.crm import (
    LeadFollowUp,
    LeadFollowUpActionResult,
    LeadFollowUpEmailDraft,
    LeadFollowUpOverview,
    LeadRelationshipReminder,
    LeadRelationshipSummary,
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
        )


def _clone_follow_up(item: LeadFollowUp) -> LeadFollowUp:
    return replace(item)


MEANINGFUL_TIMELINE_KINDS = frozenset({"call", "inbound", "outreach", "proposal", "qualification", "negotiation", "referral", "meeting", "email"})


def _enrich_follow_up(item: LeadFollowUp, current_time: datetime) -> LeadFollowUp:
    last_meaningful = _resolve_last_meaningful_interaction(item)
    health_score = _compute_relationship_health_score(item, last_meaningful, current_time)
    dormant = _is_dormant(item, last_meaningful, current_time)
    reminders = _build_relationship_reminders(item, last_meaningful, current_time)
    return replace(
        item,
        last_meaningful_interaction_at=last_meaningful,
        relationship_health_score=health_score,
        relationship_health_label=_health_label(health_score),
        dormant=dormant,
        relationship_reminders=tuple(reminders),
    )


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
    healthy_count = sum(1 for item in items if item.relationship_health_label == "healthy")
    watch_count = sum(1 for item in items if item.relationship_health_label == "watch")
    at_risk_count = sum(1 for item in items if item.relationship_health_label == "at_risk")
    dormant_count = sum(1 for item in items if item.dormant)
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
        healthy_count=healthy_count,
        watch_count=watch_count,
        at_risk_count=at_risk_count,
        dormant_count=dormant_count,
        referral_reminder_count=referral_reminder_count,
        milestone_reminder_count=milestone_reminder_count,
        warm_intro_connections=warm_intro_connections,
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
