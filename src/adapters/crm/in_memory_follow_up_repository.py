from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from src.domain.auth import User
from src.domain.crm import LeadEmailThreadSummary, LeadFollowUp, LeadTimelineEntry


class InMemoryLeadFollowUpRepository:
    def __init__(self, now: callable | None = None) -> None:
        self.now = now or (lambda: datetime.now(tz=UTC))
        self._items = self._build_seed_data()

    def list_lead_follow_ups(self, user: User) -> list[LeadFollowUp]:
        return [replace(item) for item in self._items.values()]

    def complete_lead_follow_up(self, user: User, follow_up_id: str, completed_at: datetime) -> None:
        if follow_up_id not in self._items:
            raise KeyError(follow_up_id)
        del self._items[follow_up_id]

    def snooze_lead_follow_up(self, user: User, follow_up_id: str, next_follow_up_at: datetime) -> None:
        item = self._items.get(follow_up_id)
        if item is None:
            raise KeyError(follow_up_id)
        self._items[follow_up_id] = replace(item, next_follow_up_at=next_follow_up_at)

    def append_note_to_lead_follow_up(self, user: User, follow_up_id: str, note_body: str, noted_at: datetime) -> None:
        item = self._items.get(follow_up_id)
        if item is None:
            raise KeyError(follow_up_id)
        entry = LeadTimelineEntry(
            id=f"{follow_up_id}-note-{int(noted_at.timestamp())}",
            occurred_at=noted_at,
            kind="internal_note",
            channel="internal",
            summary=note_body,
        )
        self._items[follow_up_id] = replace(
            item,
            notes=note_body,
            timeline=(entry, *item.timeline),
        )

    def import_lead_follow_ups(self, user: User, follow_ups: list[LeadFollowUp]) -> int:
        for item in follow_ups:
            self._items[item.id] = replace(item)
        return len(follow_ups)

    def _build_seed_data(self) -> dict[str, LeadFollowUp]:
        current_time = self.now()
        items = [
            LeadFollowUp(
                id="lead-amber-studio",
                lead_name="Amber Flores",
                company_name="Northstar Studio",
                owner_name="Ada Lovelace",
                stage="Discovery",
                priority="high",
                contact_channel="email",
                last_contacted_at=current_time - timedelta(days=5),
                next_follow_up_at=current_time - timedelta(hours=4),
                next_step="Send a concise recap and propose two call slots.",
                notes="Interested, but waiting on a clearer summary of timeline and scope.",
                email_address="amber@northstarstudio.com",
                referral_source_name="Jules from Seabird Partners",
                birthday=date(1991, 5, 28),
                company_milestone_name="annual planning window",
                company_milestone_date=date(2016, 6, 2),
                timeline=(
                    LeadTimelineEntry(
                        id="amber-upload",
                        occurred_at=current_time - timedelta(hours=3),
                        kind="import",
                        channel="magic_link",
                        summary="Client uploaded three onboarding screenshots and a scope note through the shared link.",
                    ),
                    LeadTimelineEntry(
                        id="amber-call",
                        occurred_at=current_time - timedelta(days=5),
                        kind="call",
                        channel="phone",
                        summary="Discovery call completed. Timing and scope were positive, but the recap needs to be tighter.",
                    ),
                    LeadTimelineEntry(
                        id="amber-inbound",
                        occurred_at=current_time - timedelta(days=8),
                        kind="inbound",
                        channel="email",
                        summary="Inbound request mentioned spreadsheet-heavy client onboarding and missed follow-ups.",
                    ),
                ),
                recent_email_threads=(
                    LeadEmailThreadSummary(
                        thread_id="thread-amber-recap",
                        subject="Re: discovery recap",
                        counterpart_name="Amber Flores",
                        counterpart_email="amber@northstarstudio.com",
                        last_message_at=current_time - timedelta(hours=4),
                        last_message_direction="inbound",
                        message_count=4,
                        snippet="Could you tighten the recap and send two possible times for next week?",
                        needs_reply=True,
                        waiting_on_contact=False,
                    ),
                ),
            ),
            LeadFollowUp(
                id="lead-riverbridge",
                lead_name="Marcus Chen",
                company_name="Riverbridge Ops",
                owner_name="Ada Lovelace",
                email_address="marcus@riverbridgeops.com",
                stage="Proposal",
                priority="high",
                contact_channel="linkedin",
                last_contacted_at=current_time - timedelta(days=2),
                next_follow_up_at=current_time + timedelta(hours=2),
                next_step="Follow up on proposal review and confirm who signs off internally.",
                notes="Opened the proposal twice. Mentioned concern about rollout burden.",
                company_milestone_name="budget reset",
                company_milestone_date=date(2018, 6, 9),
                timeline=(
                    LeadTimelineEntry(
                        id="riverbridge-proposal",
                        occurred_at=current_time - timedelta(days=2),
                        kind="proposal",
                        channel="email",
                        summary="Proposal sent with a phased rollout option and lightweight pilot pricing.",
                    ),
                    LeadTimelineEntry(
                        id="riverbridge-linkedin",
                        occurred_at=current_time - timedelta(days=6),
                        kind="outreach",
                        channel="linkedin",
                        summary="Initial outreach hit on CRM follow-up gaps and reporting overhead inside their ops team.",
                    ),
                ),
                recent_email_threads=(
                    LeadEmailThreadSummary(
                        thread_id="thread-riverbridge-proposal",
                        subject="Proposal follow-up",
                        counterpart_name="Marcus Chen",
                        counterpart_email="marcus@riverbridgeops.com",
                        last_message_at=current_time - timedelta(days=2),
                        last_message_direction="outbound",
                        message_count=3,
                        snippet="Wanted to make sure the phased rollout option covered the concern around rollout burden.",
                        needs_reply=False,
                        waiting_on_contact=True,
                    ),
                ),
            ),
            LeadFollowUp(
                id="lead-lattice",
                lead_name="Priya Nair",
                company_name="Lattice Lane",
                owner_name="Samir Patel",
                email_address="priya@latticelane.com",
                stage="Qualification",
                priority="medium",
                contact_channel="email",
                last_contacted_at=current_time - timedelta(days=1),
                next_follow_up_at=current_time + timedelta(days=1),
                next_step="Share two examples of similar results and ask for current CRM workflow pain.",
                notes="Strong fit if lead capture and follow-up remain spreadsheet based.",
                referral_source_name="Nina at Harbor Circle",
                birthday=date(1990, 6, 1),
                timeline=(
                    LeadTimelineEntry(
                        id="lattice-qualification",
                        occurred_at=current_time - timedelta(days=1),
                        kind="qualification",
                        channel="email",
                        summary="Qualification reply confirmed their lead capture still lands in spreadsheets before CRM cleanup.",
                    ),
                    LeadTimelineEntry(
                        id="lattice-referral",
                        occurred_at=current_time - timedelta(days=4),
                        kind="referral",
                        channel="email",
                        summary="Referral intro said they keep losing context between discovery and follow-up.",
                    ),
                ),
                recent_email_threads=(
                    LeadEmailThreadSummary(
                        thread_id="thread-lattice-qualification",
                        subject="Spreadsheet workflow question",
                        counterpart_name="Priya Nair",
                        counterpart_email="priya@latticelane.com",
                        last_message_at=current_time - timedelta(days=1),
                        last_message_direction="inbound",
                        message_count=2,
                        snippet="We still move new leads through Sheets first, so examples there would help.",
                        needs_reply=True,
                        waiting_on_contact=False,
                    ),
                ),
            ),
            LeadFollowUp(
                id="lead-cedar",
                lead_name="Jordan Pike",
                company_name="Cedar Peak Agency",
                owner_name="Samir Patel",
                email_address="jordan@cedarpeakagency.com",
                stage="Negotiation",
                priority="medium",
                contact_channel="phone",
                last_contacted_at=current_time - timedelta(days=27),
                next_follow_up_at=current_time + timedelta(days=2),
                next_step="Confirm decision deadline and check whether they need a lighter pilot option.",
                notes="Likes the direction, but comparing against doing it manually one more quarter.",
                timeline=(
                    LeadTimelineEntry(
                        id="cedar-phone",
                        occurred_at=current_time - timedelta(days=27),
                        kind="call",
                        channel="phone",
                        summary="Negotiation call focused on whether the team can justify the workflow shift before busy season.",
                    ),
                    LeadTimelineEntry(
                        id="cedar-proposal",
                        occurred_at=current_time - timedelta(days=31),
                        kind="proposal",
                        channel="email",
                        summary="Proposal framed the CRM around relationship memory, handoffs, and fewer dropped follow-ups.",
                    ),
                ),
                recent_email_threads=(
                    LeadEmailThreadSummary(
                        thread_id="thread-cedar-pilot",
                        subject="Checking timing on the pilot",
                        counterpart_name="Jordan Pike",
                        counterpart_email="jordan@cedarpeakagency.com",
                        last_message_at=current_time - timedelta(days=9),
                        last_message_direction="outbound",
                        message_count=5,
                        snippet="Following up in case a lighter pilot option helps before busy season starts.",
                        needs_reply=False,
                        waiting_on_contact=True,
                    ),
                ),
            ),
        ]
        return {item.id: item for item in items}
