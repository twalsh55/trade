from __future__ import annotations

from datetime import UTC, datetime

from src.application.operator_briefing import (
    DailyOperatorBriefingConfig,
    OperatorGuidancePoint,
    ProductUpdateRecord,
    ProspectRunRecord,
    RunDailyOperatorBriefingUseCase,
    ShortlistedIdeaRecord,
    _build_profitability_assessment,
    _build_recommended_next_step,
    format_operator_briefing_email,
)
from src.domain.prospecting import ProspectTokenUsage


class FakeProspectHistory:
    def __init__(self, runs: list[ProspectRunRecord]) -> None:
        self.runs = runs
        self.since = None

    def list_prospect_runs(self, since: datetime) -> list[ProspectRunRecord]:
        self.since = since
        return self.runs


class FakeProductUpdates:
    def __init__(self, updates: list[ProductUpdateRecord]) -> None:
        self.updates = updates
        self.since = None

    def list_product_updates(self, since: datetime) -> list[ProductUpdateRecord]:
        self.since = since
        return self.updates


class FakeEmailDelivery:
    def __init__(self) -> None:
        self.sent = []

    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        self.sent.append((recipient, subject, text_body))


def test_run_daily_operator_briefing_summarizes_runs_and_updates() -> None:
    history = FakeProspectHistory(
        [
            ProspectRunRecord(
                generated_at=datetime(2026, 5, 16, 9, 0, tzinfo=UTC),
                profile="crm_direction",
                scanned_post_count=12,
                shortlisted_count=2,
                shortlisted_ideas=(
                    ShortlistedIdeaRecord(
                        source="reddit",
                        matched_query="lead follow up manually",
                        score=21,
                        reasons=("mentions follow up", "mentions spreadsheet"),
                        description="Build a follow-up queue for agency leads with reminders and ownership.",
                        observed_signal="We keep forgetting to follow up and still track this in spreadsheets.",
                    ),
                    ShortlistedIdeaRecord(
                        source="hacker_news",
                        matched_query="sales pipeline spreadsheet",
                        score=18,
                        reasons=("mentions pipeline", "mentions manual"),
                        description="Create stale-pipeline nudges and stage hygiene checks for operators.",
                        observed_signal="Pipeline state goes stale because nobody owns the next touch.",
                    ),
                ),
                token_usage=ProspectTokenUsage(
                    model="gpt-5-nano",
                    input_tokens=120,
                    output_tokens=30,
                    total_tokens=150,
                ),
            )
        ]
    )
    updates = FakeProductUpdates(
        [
            ProductUpdateRecord(
                recorded_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
                category="feature",
                title="Lead follow-up queue",
                summary="Added a CRM queue with due today, overdue, and priority views.",
                agent_guidance="The agent kept surfacing missed follow-up pain and spreadsheet tracking.",
                profitability_note="This targets a recurring workflow that agencies can justify paying for.",
            )
        ]
    )
    email = FakeEmailDelivery()
    use_case = RunDailyOperatorBriefingUseCase(
        prospect_history=history,
        product_updates=updates,
        email_delivery=email,
        now=lambda: datetime(2026, 5, 16, 18, 0, tzinfo=UTC),
    )

    briefing = use_case.execute(DailyOperatorBriefingConfig(recipient_email="tom@example.com"))

    assert briefing.prospect_run_count == 1
    assert briefing.total_shortlisted_ideas == 2
    assert briefing.guidance_points[0].theme == "lead follow-up discipline"
    assert briefing.token_usage is not None
    assert briefing.token_usage.total_tokens == 150
    assert "lining up with the strongest research themes" in briefing.profitability_assessment
    assert briefing.recommended_next_step.startswith("Add complete, snooze, and reminder workflows")
    assert email.sent[0][0] == "tom@example.com"
    assert "Operator briefing (scheduled update)" in email.sent[0][1]
    assert "Agent guidance:" in email.sent[0][2]
    assert "Trigger: scheduled update" in email.sent[0][2]
    assert "model gpt-5-nano | live OpenAI reasoning" in email.sent[0][2]
    assert "Top signals:" in email.sent[0][2]
    assert "Shipped work:" in email.sent[0][2]


def test_format_operator_briefing_email_handles_empty_signal() -> None:
    briefing = RunDailyOperatorBriefingUseCase(
        prospect_history=FakeProspectHistory([]),
        product_updates=FakeProductUpdates([]),
        email_delivery=FakeEmailDelivery(),
        now=lambda: datetime(2026, 5, 16, 18, 0, tzinfo=UTC),
    ).execute(DailyOperatorBriefingConfig(recipient_email="tom@example.com"))

    content = format_operator_briefing_email(DailyOperatorBriefingConfig(recipient_email="tom@example.com"), briefing)

    assert "No repeated guidance patterns were strong enough to matter." in content
    assert "No strong ideas were shortlisted." in content
    assert "No product updates were logged." in content
    assert "model template fallback | deterministic fallback, no live OpenAI reasoning" in content


def test_operator_briefing_private_helpers_cover_remaining_branches() -> None:
    guidance = (
        OperatorGuidancePoint(theme="pipeline hygiene", count=2, explanation="x"),
    )
    no_alignment = _build_profitability_assessment(guidance, [], "goal")
    assert "clearer direction than the product log currently reflects" in no_alignment
    assert _build_recommended_next_step(guidance).startswith("Add stage ownership")

    relationship = (OperatorGuidancePoint(theme="relationship memory", count=1, explanation="x"),)
    assert _build_recommended_next_step(relationship).startswith("Add a lightweight contact timeline")

    spreadsheet = (OperatorGuidancePoint(theme="spreadsheet replacement", count=1, explanation="x"),)
    assert _build_recommended_next_step(spreadsheet).startswith("Add import and cleanup flows")

    other = (OperatorGuidancePoint(theme="agency or client coordination", count=1, explanation="x"),)
    assert _build_recommended_next_step(other).startswith("Keep pushing the CRM")
