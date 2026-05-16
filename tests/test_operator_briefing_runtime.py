from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.adapters.operator_briefing.runtime import (
    _build_observed_signal,
    append_product_update_note,
    append_prospect_digest_to_history,
    build_email_notifier_from_env,
    build_operator_briefing_config_from_env,
    build_operator_insights_repository_from_env,
    collect_operator_briefing_config_errors,
    parse_positive_int,
    required_env,
    run_daily_operator_briefing_job,
    run_operator_briefing_job,
)
from src.application.operator_briefing import ProductUpdateRecord
from src.application.prospecting import DraftedProspectEmail, ProspectAuditEntry, ProspectingDigest
from src.domain.prospecting import ProspectTokenUsage, SocialPost


def build_digest() -> ProspectingDigest:
    post = SocialPost(
        source="reddit",
        external_id="abc",
        title="Follow-up pain",
        body="We still lose leads because reminders live in spreadsheets and email threads." * 3,
        author="ada",
        permalink="https://example.com/post",
        created_at=datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
    )
    return ProspectingDigest(
        generated_at=datetime(2026, 5, 16, 11, 0, tzinfo=UTC),
        profile="crm_direction",
        scanned_post_count=10,
        shortlisted_count=1,
        shortlisted_posts=(
            DraftedProspectEmail(
                post=post,
                matched_query="lead follow up manually",
                score=19,
                reasons=("mentions follow up", "mentions spreadsheet"),
                suggested_reply="Build a reminder-first lead queue for agencies.",
                assessment="strong_signal",
                confidence="high",
                noise_flags=(),
            ),
        ),
        audit_entries=(
            ProspectAuditEntry(
                post=post,
                matched_query="lead follow up manually",
                decision="candidate_shortlisted",
                score=19,
                reasons=("mentions follow up",),
            ),
        ),
        token_usage=ProspectTokenUsage(model="gpt-5-nano", input_tokens=10, output_tokens=5, total_tokens=15),
    )


def test_operator_briefing_runtime_appends_history_and_updates(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_RUN_LOG_FILE", str(tmp_path / "prospect_runs.jsonl"))
    monkeypatch.setenv("PRODUCT_UPDATE_LOG_FILE", str(tmp_path / "product_updates.jsonl"))

    append_prospect_digest_to_history(build_digest())
    append_product_update_note(
        ProductUpdateRecord(
            recorded_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
            category="feature",
            title="Lead queue",
            summary="Added a lead queue.",
            agent_guidance="The agent saw repeated follow-up pain.",
            profitability_note="This is a recurring workflow with clear ROI.",
        )
    )

    repository = build_operator_insights_repository_from_env()
    runs = repository.list_prospect_runs(datetime(2026, 5, 16, 0, 0, tzinfo=UTC))
    updates = repository.list_product_updates(datetime(2026, 5, 16, 0, 0, tzinfo=UTC))

    assert runs[0].shortlisted_ideas[0].observed_signal.endswith("...")
    assert updates[0].title == "Lead queue"


def test_operator_briefing_runtime_builds_config_and_validates_env(monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_EMAIL_RECIPIENT", "prospect@example.com")
    monkeypatch.setenv("OPERATOR_BRIEFING_RECIPIENT", "")
    monkeypatch.setenv("OPERATOR_BRIEFING_GOAL", "")
    monkeypatch.setenv("OPERATOR_BRIEFING_LOOKBACK_HOURS", "12")

    config = build_operator_briefing_config_from_env()
    assert config.recipient_email == "prospect@example.com"
    assert config.lookback_hours == 12
    assert "time-to-revenue" in config.goal

    monkeypatch.setenv("OPERATOR_BRIEFING_LOOKBACK_HOURS", "0")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_FROM_EMAIL", raising=False)
    errors = collect_operator_briefing_config_errors()
    assert "OPERATOR_BRIEFING_LOOKBACK_HOURS must be greater than zero" in errors
    assert "Missing SMTP_HOST" in errors

    monkeypatch.setenv("OPERATOR_BRIEFING_LOOKBACK_HOURS", "abc")
    errors = collect_operator_briefing_config_errors()
    assert "OPERATOR_BRIEFING_LOOKBACK_HOURS must be an integer" in errors

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "from@example.com")
    monkeypatch.delenv("OPERATOR_BRIEFING_LOOKBACK_HOURS", raising=False)
    assert collect_operator_briefing_config_errors() == []
    monkeypatch.setenv("OPERATOR_BRIEFING_LOOKBACK_HOURS", "abc")
    assert "OPERATOR_BRIEFING_LOOKBACK_HOURS must be an integer" in collect_operator_briefing_config_errors()
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USE_TLS", "false")
    notifier = build_email_notifier_from_env()
    assert notifier.port == 2525
    assert notifier.use_tls is False

    with pytest.raises(ValueError, match="Missing TEST_REQUIRED"):
        required_env("TEST_REQUIRED")
    assert parse_positive_int("UNSET_NUMBER", default=7) == 7
    monkeypatch.setenv("BAD_INT", "abc")
    with pytest.raises(ValueError, match="BAD_INT must be an integer."):
        parse_positive_int("BAD_INT", default=1)
    monkeypatch.setenv("BAD_INT", "-1")
    with pytest.raises(ValueError, match="BAD_INT must be greater than zero."):
        parse_positive_int("BAD_INT", default=1)
    assert _build_observed_signal("Short title", "") == "Short title"


def test_run_daily_operator_briefing_job_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_RUN_LOG_FILE", str(tmp_path / "prospect_runs.jsonl"))
    monkeypatch.setenv("PRODUCT_UPDATE_LOG_FILE", str(tmp_path / "product_updates.jsonl"))
    monkeypatch.setenv("PROSPECT_EMAIL_RECIPIENT", "tom@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "from@example.com")

    append_prospect_digest_to_history(build_digest())
    sent = []

    def fake_send_email(self, recipient: str, subject: str, text_body: str) -> None:
        sent.append((recipient, subject, text_body))

    monkeypatch.setattr("src.adapters.notifications.smtp_email_notifier.SMTPEmailNotifier.send_email", fake_send_email)

    briefing = run_daily_operator_briefing_job()

    assert briefing.prospect_run_count == 1
    assert sent[0][0] == "tom@example.com"
    assert "Operator briefing (daily schedule)" in sent[0][1]


def test_run_operator_briefing_job_uses_custom_trigger_label(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_RUN_LOG_FILE", str(tmp_path / "prospect_runs.jsonl"))
    monkeypatch.setenv("PRODUCT_UPDATE_LOG_FILE", str(tmp_path / "product_updates.jsonl"))
    monkeypatch.setenv("PROSPECT_EMAIL_RECIPIENT", "tom@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pass")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "from@example.com")

    append_prospect_digest_to_history(build_digest())
    sent = []

    def fake_send_email(self, recipient: str, subject: str, text_body: str) -> None:
        sent.append((recipient, subject, text_body))

    monkeypatch.setattr("src.adapters.notifications.smtp_email_notifier.SMTPEmailNotifier.send_email", fake_send_email)

    briefing = run_operator_briefing_job(trigger_label="prospect run")

    assert briefing.prospect_run_count == 1
    assert sent[0][0] == "tom@example.com"
    assert "Operator briefing (prospect run)" in sent[0][1]
    assert "Trigger: prospect run" in sent[0][2]
