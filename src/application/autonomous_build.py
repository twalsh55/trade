from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.prospecting import DraftedProspectEmail, ProspectingDigest
from src.domain.prospecting import ProspectTokenUsage


@dataclass(frozen=True, slots=True)
class AutonomousBuildBrief:
    created_at: datetime
    profile: str
    should_build: bool
    feature_name: str | None
    summary: str
    rationale: str
    implementation_outline: tuple[str, ...]
    evidence_titles: tuple[str, ...]
    source_mix: tuple[str, ...]
    confidence: str
    token_usage: ProspectTokenUsage | None


def decide_autonomous_build_brief(
    digest: ProspectingDigest,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> AutonomousBuildBrief:
    candidates = tuple(
        item
        for item in digest.shortlisted_posts
        if item.assessment == "strong_signal" and item.confidence in {"high", "medium"}
    )
    if not candidates:
        return AutonomousBuildBrief(
            created_at=now(),
            profile=digest.profile,
            should_build=False,
            feature_name=None,
            summary="No feature should be auto-queued from this run.",
            rationale=(
                "The prospect pass did not produce a strong enough repeated signal. "
                "Keep gathering evidence instead of broadening the roadmap."
            ),
            implementation_outline=(),
            evidence_titles=tuple(item.post.title for item in digest.shortlisted_posts[:2]),
            source_mix=tuple(item.post.source for item in digest.shortlisted_posts[:2]),
            confidence="low",
            token_usage=digest.token_usage,
        )

    primary = _pick_primary_candidate(candidates)
    feature_name, summary, outline = _map_candidate_to_feature(primary)
    confidence = "high" if primary.confidence == "high" and len(candidates) >= 1 else "medium"
    evidence_titles = tuple(item.post.title for item in candidates[:3])
    source_mix = tuple(dict.fromkeys(item.post.source for item in candidates[:3]))
    rationale = (
        f"Primary evidence came from {primary.post.source} and matched recurring CRM workflow pain around "
        f"{_build_theme_label(primary)}. The signal is strong enough to deepen the current wedge rather than wait "
        f"for a broader trend."
    )
    return AutonomousBuildBrief(
        created_at=now(),
        profile=digest.profile,
        should_build=True,
        feature_name=feature_name,
        summary=summary,
        rationale=rationale,
        implementation_outline=outline,
        evidence_titles=evidence_titles,
        source_mix=source_mix,
        confidence=confidence,
        token_usage=digest.token_usage,
    )


def format_autonomous_build_brief(brief: AutonomousBuildBrief) -> str:
    lines = [
        "Code cooperation result",
        f"Decision: {'build now' if brief.should_build else 'hold'}",
        f"Profile: {brief.profile}",
        f"Confidence: {brief.confidence}",
    ]
    if brief.feature_name:
        lines.append(f"Feature: {brief.feature_name}")
    lines.extend(
        [
            f"Summary: {brief.summary}",
            f"Why: {brief.rationale}",
        ]
    )
    if brief.evidence_titles:
        lines.append("Evidence:")
        lines.extend(f"- {title}" for title in brief.evidence_titles[:3])
    if brief.implementation_outline:
        lines.append("Implementation next:")
        lines.extend(f"- {step}" for step in brief.implementation_outline[:3])
    if brief.token_usage is not None:
        lines.append(
            "Model usage: "
            f"{brief.token_usage.model} {brief.token_usage.total_tokens} tokens"
        )
    return "\n".join(lines)


def _pick_primary_candidate(candidates: tuple[DraftedProspectEmail, ...]) -> DraftedProspectEmail:
    def rank(item: DraftedProspectEmail) -> tuple[int, int, int]:
        combined = _combined_candidate_text(item)
        spreadsheet_bias = 1 if any(term in combined for term in ("spreadsheet", "csv", "google sheets", "sheet")) else 0
        inbox_bias = 1 if any(term in combined for term in ("dm", "message", "inbox", "twitter", "x ")) else 0
        confidence_bias = 2 if item.confidence == "high" else 1
        return (spreadsheet_bias, inbox_bias, item.score + confidence_bias)

    return sorted(candidates, key=rank, reverse=True)[0]


def _map_candidate_to_feature(item: DraftedProspectEmail) -> tuple[str, str, tuple[str, ...]]:
    combined = _combined_candidate_text(item)
    if any(term in combined for term in ("spreadsheet", "csv", "google sheets", "sheet")):
        return (
            "CSV and Google Sheets import",
            "Build spreadsheet import and cleanup so teams can adopt the CRM without abandoning their current lead sheet.",
            (
                "Add CSV upload parsing for contacts, company, owner, status, next follow-up, and notes.",
                "Normalize messy headers, detect duplicate contacts, and preview validation issues before import.",
                "Map imported rows into the follow-up queue, timeline history, and note memory panel.",
            ),
        )
    if any(term in combined for term in ("dm", "message", "inbox", "twitter", "x ")) or "inbox" in item.post.title.lower():
        return (
            "Inbox and DM capture",
            "Capture revenue-critical messages into the CRM timeline so founder-led sales follow-up does not disappear across inboxes.",
            (
                "Add a lightweight inbound message model tied to contacts and follow-up records.",
                "Ingest copied or forwarded messages into the contact timeline with owner and channel metadata.",
                "Create reminder rules for unanswered threads and stale prospect conversations.",
            ),
        )
    return (
        "Follow-up workflow refinement",
        "Deepen the current follow-up-first CRM wedge with tighter workflow hygiene and relationship memory.",
        (
            "Add clearer stale-deal detection and next-step enforcement in the follow-up queue.",
            "Surface missing owner, missing next action, and aging lead warnings in the CRM workspace.",
            "Strengthen timeline and note capture around every follow-up event.",
        ),
    )


def _build_theme_label(item: DraftedProspectEmail) -> str:
    combined = _combined_candidate_text(item)
    if any(term in combined for term in ("spreadsheet", "csv", "google sheets", "sheet")):
        return "spreadsheet-held CRM workflows"
    if any(term in combined for term in ("dm", "message", "inbox", "twitter", "x ")):
        return "message-driven follow-up"
    return "follow-up discipline"


def _combined_candidate_text(item: DraftedProspectEmail) -> str:
    return " ".join(
        [
            item.post.title.lower(),
            item.post.body.lower(),
            item.suggested_reply.lower(),
            " ".join(item.reasons).lower(),
        ]
    )
