from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SIGNAL_KEYWORDS = {
    "investing": 3,
    "portfolio": 3,
    "market": 2,
    "stocks": 2,
    "trading": 2,
    "crash": 4,
    "recession": 3,
    "bear market": 3,
    "hedge": 3,
    "volatility": 3,
    "risk": 2,
    "alert": 2,
}

INTENT_KEYWORDS = {
    "looking for": 5,
    "recommend": 5,
    "any app": 6,
    "tool": 4,
    "dashboard": 4,
    "track": 3,
    "monitor": 3,
    "help": 2,
    "need": 2,
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
