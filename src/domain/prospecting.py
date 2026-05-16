from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SIGNAL_KEYWORDS = {
    "spreadsheet": 4,
    "excel": 4,
    "csv": 3,
    "manual": 4,
    "reconciliation": 4,
    "reporting": 3,
    "workflow": 3,
    "process": 2,
    "integration": 3,
    "automation": 4,
    "admin": 3,
    "dashboard": 3,
    "ops": 2,
    "operations": 3,
    "compliance": 3,
    "email": 2,
    "pdf": 2,
    "copy paste": 4,
    "copy/paste": 4,
    "crm": 5,
    "lead": 4,
    "leads": 4,
    "follow up": 5,
    "follow-up": 5,
    "pipeline": 5,
    "prospect": 4,
    "client": 4,
    "customer": 3,
    "handoff": 4,
    "reminder": 3,
    "notes": 3,
}

INTENT_KEYWORDS = {
    "looking for": 5,
    "recommend": 5,
    "any tool": 6,
    "any software": 6,
    "tool": 4,
    "software": 4,
    "alternative": 5,
    "how are you solving": 6,
    "i wish there was": 7,
    "anyone else": 3,
    "frustrated": 4,
    "pain point": 5,
    "automation": 4,
    "help": 2,
    "need": 2,
    "tracking": 4,
    "still using": 5,
    "who owns": 4,
    "forgot to follow up": 6,
}

EXCLUDE_KEYWORDS = {
    "hiring",
    "job",
    "job opening",
    "for hire",
    "meme coin",
    "sports betting",
}


@dataclass(frozen=True, slots=True)
class SocialPost:
    source: str
    external_id: str
    title: str
    body: str
    author: str
    permalink: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProspectMatch:
    post: SocialPost
    matched_query: str
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProspectTokenUsage:
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


def score_social_post(post: SocialPost, matched_query: str) -> ProspectMatch | None:
    haystack = f"{post.title}\n{post.body}".lower()

    if any(keyword in haystack for keyword in EXCLUDE_KEYWORDS):
        return None

    score = 0
    reasons: list[str] = []

    for keyword, weight in SIGNAL_KEYWORDS.items():
        if keyword in haystack:
            score += weight
            reasons.append(f"mentions {keyword}")

    for keyword, weight in INTENT_KEYWORDS.items():
        if keyword in haystack:
            score += weight
            reasons.append(f"shows intent via {keyword}")

    if "?" in post.title or "?" in post.body:
        score += 2
        reasons.append("asks a question")

    if matched_query.lower() in haystack:
        score += 2
        reasons.append(f"matched query {matched_query}")

    deduped_reasons = tuple(dict.fromkeys(reasons))
    if score < 8:
        return None

    return ProspectMatch(
        post=post,
        matched_query=matched_query,
        score=score,
        reasons=deduped_reasons,
    )
