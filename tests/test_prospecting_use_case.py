from __future__ import annotations

from datetime import UTC, datetime

from src.application.prospecting import (
    DailyProspectingConfig,
    ProspectingDigest,
    RunDailyProspectingUseCase,
    _summarize_post_text,
    format_digest_email,
)
from src.domain.prospecting import ProspectMatch, SocialPost


class StubLeadSource:
    def __init__(self, responses: dict[str, list[SocialPost]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, int]] = []

    def search_recent_posts(self, search_term: str, limit: int) -> list[SocialPost]:
        self.calls.append((search_term, limit))
        return self.responses.get(search_term, [])


class StubDrafter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[ProspectMatch, ...], str | None]] = []

    def draft_promotional_replies(
        self,
        app_summary: str,
        matches: tuple[ProspectMatch, ...],
        app_url: str | None = None,
    ) -> list[str]:
        self.calls.append((app_summary, matches, app_url))
        return [f"draft for {match.post.external_id}" for match in matches]


class StubEmailDelivery:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send_email(self, recipient: str, subject: str, text_body: str) -> None:
        self.sent.append((recipient, subject, text_body))


def make_post(external_id: str, title: str, body: str, day: int) -> SocialPost:
    return SocialPost(
        source="reddit",
        external_id=external_id,
        title=title,
        body=body,
        author="poster",
        permalink=f"https://example.com/{external_id}",
        created_at=datetime(2026, 5, day, tzinfo=UTC),
    )


def test_daily_prospecting_use_case_shortlists_and_emails() -> None:
    matching_post = make_post(
        "1",
        "Looking for a market crash dashboard tool?",
        "Need help monitoring my portfolio risk during volatility.",
        14,
    )
    duplicate_post = make_post(
        "1",
        "Looking for a market crash dashboard tool?",
        "Need help monitoring my portfolio risk during volatility.",
        14,
    )
    weaker_post = make_post("2", "Daily recap", "Just posting a market summary.", 13)
    lead_source = StubLeadSource(
        {
            "looking for stock market crash app": [matching_post, weaker_post],
            "portfolio risk dashboard": [duplicate_post],
        }
    )
    drafter = StubDrafter()
    email_delivery = StubEmailDelivery()
    use_case = RunDailyProspectingUseCase(
        lead_source=lead_source,
        drafter=drafter,
        email_delivery=email_delivery,
        now=lambda: datetime(2026, 5, 14, 9, 30, tzinfo=UTC),
    )

    digest = use_case.execute(
        DailyProspectingConfig(
            recipient_email="tom.mg.walsh@gmail.com",
            app_url="https://www.brivoly.com",
            search_terms=("looking for stock market crash app", "portfolio risk dashboard"),
            per_term_limit=5,
            max_matches=2,
        )
    )

    assert lead_source.calls == [
        ("looking for stock market crash app", 5),
        ("portfolio risk dashboard", 5),
    ]
    assert digest.scanned_post_count == 3
    assert digest.shortlisted_count == 1
    assert digest.shortlisted_posts[0].suggested_reply == "draft for 1"
    assert [entry.decision for entry in digest.audit_entries] == [
        "candidate_shortlisted",
        "rejected",
        "duplicate_skipped",
    ]
    assert drafter.calls[0][2] == "https://www.brivoly.com"
    assert email_delivery.sent[0][0] == "tom.mg.walsh@gmail.com"
    assert "Looking for a market crash dashboard tool?" in email_delivery.sent[0][2]
    assert "Summary:" in email_delivery.sent[0][2]
    assert "Decision summary:" in email_delivery.sent[0][2]
    assert "Audit detail mode: concise" in email_delivery.sent[0][2]


def test_daily_prospecting_use_case_handles_empty_shortlist() -> None:
    lead_source = StubLeadSource({"market crash alert tool": []})
    drafter = StubDrafter()
    email_delivery = StubEmailDelivery()
    use_case = RunDailyProspectingUseCase(
        lead_source=lead_source,
        drafter=drafter,
        email_delivery=email_delivery,
        now=lambda: datetime(2026, 5, 14, 9, 30, tzinfo=UTC),
    )

    digest = use_case.execute(
        DailyProspectingConfig(
            recipient_email="tom.mg.walsh@gmail.com",
            search_terms=("market crash alert tool",),
        )
    )

    assert digest.shortlisted_count == 0
    assert drafter.calls[0][1] == ()
    assert "No strong social posts were found today." in email_delivery.sent[0][2]
    assert "Audit detail mode: concise" in email_delivery.sent[0][2]


def test_daily_prospecting_use_case_records_excluded_keyword_reason() -> None:
    excluded_post = make_post("3", "Hiring quant trader", "This job opening is for a trading startup.", 14)
    lead_source = StubLeadSource({"portfolio risk dashboard": [excluded_post]})
    drafter = StubDrafter()
    email_delivery = StubEmailDelivery()
    use_case = RunDailyProspectingUseCase(
        lead_source=lead_source,
        drafter=drafter,
        email_delivery=email_delivery,
        now=lambda: datetime(2026, 5, 14, 9, 30, tzinfo=UTC),
    )

    digest = use_case.execute(
        DailyProspectingConfig(
            recipient_email="tom.mg.walsh@gmail.com",
            search_terms=("portfolio risk dashboard",),
        )
    )

    assert digest.audit_entries[0].decision == "rejected"
    assert "filtered by excluded keyword hiring" in digest.audit_entries[0].reasons
    assert "filtered by excluded keyword job opening" in digest.audit_entries[0].reasons


def test_format_digest_email_truncates_long_body() -> None:
    post = make_post("1", "Title", "x" * 400, 14)
    digest = ProspectingDigest(
        generated_at=datetime(2026, 5, 14, 9, 30, tzinfo=UTC),
        scanned_post_count=5,
        shortlisted_count=1,
        shortlisted_posts=(
            type(
                "DraftedItem",
                (),
                {
                    "post": post,
                    "matched_query": "query",
                    "score": 12,
                    "reasons": ("mentions crash",),
                    "suggested_reply": "reply",
                },
            )(),
        ),
        audit_entries=(
            type(
                "AuditItem",
                (),
                {
                    "post": post,
                    "matched_query": "query",
                    "decision": "candidate_shortlisted",
                    "score": 12,
                    "reasons": ("mentions crash",),
                },
            )(),
        ),
    )
    config = DailyProspectingConfig(recipient_email="tom.mg.walsh@gmail.com")

    body = format_digest_email(config, digest)

    assert "..." in body
    assert "Suggested promo reply:" in body
    assert "Summary:" in body
    assert "Audit detail mode: concise" in body


def test_format_digest_email_uses_source_label_for_shortlisted_posts() -> None:
    post = SocialPost(
        source="hackernews",
        external_id="1",
        title="Title",
        body="body",
        author="poster",
        permalink="https://example.com/1",
        created_at=datetime(2026, 5, 14, tzinfo=UTC),
    )
    digest = ProspectingDigest(
        generated_at=datetime(2026, 5, 14, 9, 30, tzinfo=UTC),
        scanned_post_count=1,
        shortlisted_count=1,
        shortlisted_posts=(
            type(
                "DraftedItem",
                (),
                {
                    "post": post,
                    "matched_query": "query",
                    "score": 12,
                    "reasons": ("mentions crash",),
                    "suggested_reply": "reply",
                },
            )(),
        ),
        audit_entries=(),
    )

    body = format_digest_email(DailyProspectingConfig(recipient_email="tom.mg.walsh@gmail.com"), digest)

    assert "1. hackernews post" in body


def test_format_digest_email_includes_full_audit_when_verbose() -> None:
    post = make_post("1", "Title", "body", 14)
    digest = ProspectingDigest(
        generated_at=datetime(2026, 5, 14, 9, 30, tzinfo=UTC),
        scanned_post_count=1,
        shortlisted_count=0,
        shortlisted_posts=(),
        audit_entries=(
            type(
                "AuditItem",
                (),
                {
                    "post": post,
                    "matched_query": "query",
                    "decision": "rejected",
                    "score": 0,
                    "reasons": ("insufficient intent or fit score for shortlist",),
                },
            )(),
        ),
    )
    config = DailyProspectingConfig(
        recipient_email="tom.mg.walsh@gmail.com",
        verbose_audit=True,
    )

    body = format_digest_email(config, digest)

    assert "Full audit trail:" in body
    assert "Decision: rejected" in body


def test_daily_prospecting_use_case_applies_top_five_and_min_score() -> None:
    lead_source = StubLeadSource(
        {
            "portfolio risk dashboard": [
                make_post(str(index), f"Looking for a crash dashboard tool? #{index}", "I need a tool to monitor portfolio risk during volatility.", 14)
                for index in range(1, 8)
            ]
        }
    )
    drafter = StubDrafter()
    email_delivery = StubEmailDelivery()
    use_case = RunDailyProspectingUseCase(
        lead_source=lead_source,
        drafter=drafter,
        email_delivery=email_delivery,
        now=lambda: datetime(2026, 5, 14, 9, 30, tzinfo=UTC),
    )

    digest = use_case.execute(
        DailyProspectingConfig(
            recipient_email="tom.mg.walsh@gmail.com",
            search_terms=("portfolio risk dashboard",),
            max_matches=5,
            min_score=12,
        )
    )

    assert digest.shortlisted_count == 5


def test_summarize_post_text_handles_empty_and_title_only_body() -> None:
    assert _summarize_post_text("Title", "   ", 50) == ""
    assert _summarize_post_text("Same title", "Same title", 50) == "Same title"
