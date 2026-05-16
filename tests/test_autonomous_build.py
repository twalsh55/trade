from __future__ import annotations

from datetime import UTC, datetime

from src.application.autonomous_build import decide_autonomous_build_brief, format_autonomous_build_brief
from src.application.prospecting import DraftedProspectEmail, ProspectingDigest
from src.domain.prospecting import ProspectTokenUsage, SocialPost


def test_decide_autonomous_build_brief_prefers_spreadsheet_import_feature() -> None:
    digest = ProspectingDigest(
        generated_at=datetime(2026, 5, 16, 18, 0, tzinfo=UTC),
        profile="crm_direction",
        scanned_post_count=12,
        shortlisted_count=2,
        shortlisted_posts=(
            DraftedProspectEmail(
                post=SocialPost(
                    source="hackernews",
                    external_id="1",
                    title="Show HN: Sheety - CRM with Google Sheets as DB",
                    body="Small teams still manage leads in spreadsheets and need CRM follow up discipline.",
                    author="maker",
                    permalink="https://example.com/sheety",
                    created_at=datetime(2026, 5, 16, 16, 0, tzinfo=UTC),
                ),
                matched_query="sales pipeline spreadsheet",
                score=31,
                reasons=("mentions spreadsheet", "mentions crm"),
                suggested_reply="Spreadsheet-native CRM layer with follow-up queue and notes.",
                assessment="strong_signal",
                confidence="high",
                noise_flags=("show_hn_launch",),
            ),
            DraftedProspectEmail(
                post=SocialPost(
                    source="hackernews",
                    external_id="2",
                    title="Show HN: Inbox for DMs",
                    body="DM threads get lost between inboxes.",
                    author="maker",
                    permalink="https://example.com/inbox",
                    created_at=datetime(2026, 5, 16, 15, 0, tzinfo=UTC),
                ),
                matched_query="relationship notes follow up",
                score=27,
                reasons=("mentions follow up",),
                suggested_reply="Unified DM CRM for founder-led sales.",
                assessment="strong_signal",
                confidence="high",
                noise_flags=(),
            ),
        ),
        audit_entries=(),
        token_usage=ProspectTokenUsage(model="gpt-5.4", input_tokens=1000, output_tokens=200, total_tokens=1200),
    )

    brief = decide_autonomous_build_brief(digest, now=lambda: datetime(2026, 5, 16, 19, 0, tzinfo=UTC))

    assert brief.should_build is True
    assert brief.feature_name == "CSV and Google Sheets import"
    assert "adopt the CRM without abandoning their current lead sheet" in brief.summary
    assert brief.evidence_titles[0].startswith("Show HN: Sheety")
    assert "spreadsheet-held CRM workflows" in brief.rationale


def test_decide_autonomous_build_brief_holds_when_no_strong_signal_exists() -> None:
    digest = ProspectingDigest(
        generated_at=datetime(2026, 5, 16, 18, 0, tzinfo=UTC),
        profile="crm_direction",
        scanned_post_count=8,
        shortlisted_count=1,
        shortlisted_posts=(
            DraftedProspectEmail(
                post=SocialPost(
                    source="hackernews",
                    external_id="3",
                    title="Show HN: Broad workflow AI layer",
                    body="Enterprise workflow orchestration.",
                    author="maker",
                    permalink="https://example.com/noise",
                    created_at=datetime(2026, 5, 16, 15, 0, tzinfo=UTC),
                ),
                matched_query="sales pipeline spreadsheet",
                score=12,
                reasons=("mentions workflow",),
                suggested_reply="Workflow layer.",
                assessment="weak_signal",
                confidence="medium",
                noise_flags=("enterprise_hype",),
            ),
        ),
        audit_entries=(),
        token_usage=None,
    )

    brief = decide_autonomous_build_brief(digest)

    assert brief.should_build is False
    assert brief.feature_name is None
    assert brief.confidence == "low"


def test_format_autonomous_build_brief_includes_outline_and_usage() -> None:
    digest = ProspectingDigest(
        generated_at=datetime(2026, 5, 16, 18, 0, tzinfo=UTC),
        profile="crm_direction",
        scanned_post_count=12,
        shortlisted_count=1,
        shortlisted_posts=(
            DraftedProspectEmail(
                post=SocialPost(
                    source="hackernews",
                    external_id="1",
                    title="Show HN: Sheety - CRM with Google Sheets as DB",
                    body="Spreadsheet CRM pain.",
                    author="maker",
                    permalink="https://example.com/sheety",
                    created_at=datetime(2026, 5, 16, 16, 0, tzinfo=UTC),
                ),
                matched_query="sales pipeline spreadsheet",
                score=31,
                reasons=("mentions spreadsheet",),
                suggested_reply="Spreadsheet-native CRM layer with follow-up queue and notes.",
                assessment="strong_signal",
                confidence="high",
                noise_flags=(),
            ),
        ),
        audit_entries=(),
        token_usage=ProspectTokenUsage(model="gpt-5.4-mini", input_tokens=900, output_tokens=120, total_tokens=1020),
    )

    message = format_autonomous_build_brief(decide_autonomous_build_brief(digest))

    assert "Decision: build now" in message
    assert "Implementation next:" in message
    assert "Model usage: gpt-5.4-mini 1020 tokens" in message


def test_decide_autonomous_build_brief_uses_message_capture_branch() -> None:
    digest = ProspectingDigest(
        generated_at=datetime(2026, 5, 16, 18, 0, tzinfo=UTC),
        profile="crm_direction",
        scanned_post_count=12,
        shortlisted_count=1,
        shortlisted_posts=(
            DraftedProspectEmail(
                post=SocialPost(
                    source="hackernews",
                    external_id="2",
                    title="Show HN: Inbox for DMs",
                    body="Prospect messages are getting lost between inboxes.",
                    author="maker",
                    permalink="https://example.com/inbox",
                    created_at=datetime(2026, 5, 16, 16, 0, tzinfo=UTC),
                ),
                matched_query="relationship notes follow up",
                score=28,
                reasons=("mentions follow up", "mentions message"),
                suggested_reply="Unified DM CRM for founder-led sales.",
                assessment="strong_signal",
                confidence="high",
                noise_flags=(),
            ),
        ),
        audit_entries=(),
        token_usage=None,
    )

    brief = decide_autonomous_build_brief(digest)

    assert brief.feature_name == "Inbox and DM capture"
    assert "message-driven follow-up" in brief.rationale


def test_decide_autonomous_build_brief_uses_follow_up_fallback_branch() -> None:
    digest = ProspectingDigest(
        generated_at=datetime(2026, 5, 16, 18, 0, tzinfo=UTC),
        profile="crm_direction",
        scanned_post_count=12,
        shortlisted_count=1,
        shortlisted_posts=(
            DraftedProspectEmail(
                post=SocialPost(
                    source="reddit",
                    external_id="4",
                    title="Manual follow-up reminder pain",
                    body="We keep missing next steps after calls.",
                    author="operator",
                    permalink="https://example.com/followup",
                    created_at=datetime(2026, 5, 16, 16, 0, tzinfo=UTC),
                ),
                matched_query="lead follow up manually",
                score=25,
                reasons=("mentions follow up", "shows explicit workflow pain"),
                suggested_reply="Follow-up discipline workflow for small teams.",
                assessment="strong_signal",
                confidence="high",
                noise_flags=(),
            ),
        ),
        audit_entries=(),
        token_usage=None,
    )

    brief = decide_autonomous_build_brief(digest)

    assert brief.feature_name == "Follow-up workflow refinement"
    assert "follow-up discipline" in brief.rationale
