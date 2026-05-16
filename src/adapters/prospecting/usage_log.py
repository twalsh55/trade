from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from src.application.prospecting import ProspectingDigest


@dataclass(frozen=True)
class ProspectUsageLogEntry:
    generated_at: str
    profile: str
    scanned_post_count: int
    shortlisted_count: int
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class ProspectUsageLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, digest: ProspectingDigest) -> None:
        usage = digest.token_usage
        entry = ProspectUsageLogEntry(
            generated_at=digest.generated_at.isoformat(),
            profile=digest.profile,
            scanned_post_count=digest.scanned_post_count,
            shortlisted_count=digest.shortlisted_count,
            model=usage.model if usage else None,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), sort_keys=True))
            handle.write("\n")
