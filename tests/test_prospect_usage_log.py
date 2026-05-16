from __future__ import annotations

import json
from datetime import UTC, datetime

from src.adapters.prospecting.usage_log import ProspectUsageLog
from src.application.prospecting import ProspectingDigest
from src.domain.prospecting import ProspectTokenUsage


def test_prospect_usage_log_appends_jsonl_entry(tmp_path) -> None:
    log_path = tmp_path / "prospect_usage.jsonl"
    digest = ProspectingDigest(
        generated_at=datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
        profile="crm_direction",
        scanned_post_count=14,
        shortlisted_count=3,
        shortlisted_posts=(),
        audit_entries=(),
        token_usage=ProspectTokenUsage(
            model="gpt-5-nano",
            input_tokens=111,
            output_tokens=22,
            total_tokens=133,
        ),
    )

    ProspectUsageLog(log_path).append(digest)

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["profile"] == "crm_direction"
    assert payload["scanned_post_count"] == 14
    assert payload["total_tokens"] == 133
