from __future__ import annotations

import json
import os
from pathlib import Path

from src.application.autonomous_build import AutonomousBuildBrief


def append_autonomous_build_brief(brief: AutonomousBuildBrief) -> Path:
    path = build_autonomous_build_queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": brief.created_at.isoformat(),
        "profile": brief.profile,
        "founder_guidance": brief.founder_guidance,
        "should_build": brief.should_build,
        "feature_name": brief.feature_name,
        "summary": brief.summary,
        "rationale": brief.rationale,
        "implementation_outline": list(brief.implementation_outline),
        "evidence_titles": list(brief.evidence_titles),
        "source_mix": list(brief.source_mix),
        "confidence": brief.confidence,
        "token_usage": (
            {
                "model": brief.token_usage.model,
                "input_tokens": brief.token_usage.input_tokens,
                "output_tokens": brief.token_usage.output_tokens,
                "total_tokens": brief.token_usage.total_tokens,
            }
            if brief.token_usage is not None
            else None
        ),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")
    return path


def build_autonomous_build_queue_path() -> Path:
    return Path(
        os.getenv("AUTONOMOUS_BUILD_QUEUE_FILE", "var/autonomous_build_queue.jsonl").strip()
        or "var/autonomous_build_queue.jsonl"
    )
