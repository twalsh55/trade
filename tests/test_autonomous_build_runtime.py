from __future__ import annotations

import json
from datetime import UTC, datetime

from src.adapters.autonomous_build.runtime import append_autonomous_build_brief, build_autonomous_build_queue_path
from src.application.autonomous_build import AutonomousBuildBrief
from src.domain.prospecting import ProspectTokenUsage


def test_build_autonomous_build_queue_path_uses_env_override(tmp_path, monkeypatch) -> None:
    queue_path = tmp_path / "queue.jsonl"
    monkeypatch.setenv("AUTONOMOUS_BUILD_QUEUE_FILE", str(queue_path))

    assert build_autonomous_build_queue_path() == queue_path


def test_append_autonomous_build_brief_writes_jsonl(tmp_path, monkeypatch) -> None:
    queue_path = tmp_path / "queue.jsonl"
    monkeypatch.setenv("AUTONOMOUS_BUILD_QUEUE_FILE", str(queue_path))

    brief = AutonomousBuildBrief(
        created_at=datetime(2026, 5, 16, 19, 0, tzinfo=UTC),
        profile="crm_direction",
        founder_guidance="fix a bug with login",
        should_build=True,
        feature_name="CSV and Google Sheets import",
        summary="Build import.",
        rationale="Strong repeated spreadsheet signal.",
        implementation_outline=("Parse CSV", "Dedupe rows"),
        evidence_titles=("Show HN: Sheety",),
        source_mix=("hackernews",),
        confidence="high",
        token_usage=ProspectTokenUsage(model="gpt-5.4", input_tokens=1000, output_tokens=200, total_tokens=1200),
    )

    path = append_autonomous_build_brief(brief)

    assert path == queue_path
    payload = json.loads(queue_path.read_text(encoding="utf-8").strip())
    assert payload["founder_guidance"] == "fix a bug with login"
    assert payload["feature_name"] == "CSV and Google Sheets import"
    assert payload["implementation_outline"] == ["Parse CSV", "Dedupe rows"]
    assert payload["token_usage"]["total_tokens"] == 1200
