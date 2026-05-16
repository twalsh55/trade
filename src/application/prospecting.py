from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.ports import EmailDeliveryPort, ProspectDraftingPort, SocialLeadSourcePort
from src.domain.prospecting import ProspectMatch, ProspectTokenUsage, SocialPost, score_social_post

DEFAULT_PROSPECT_SEARCH_TERMS = (
    "i wish there was a tool for",
    "how are you solving this manually",
    "spreadsheet workflow problem",
)

DEFAULT_CRM_DIRECTION_SEARCH_TERMS = (
    "lead follow up manually",
    "sales pipeline spreadsheet",
    "client handoff spreadsheet",
    "crm for agencies spreadsheet",
    "relationship notes follow up",
)

DEFAULT_APP_SUMMARY = (
    "You are researching boring, profitable SaaS opportunities for a solo indie hacker. "
    "Focus on painful, recurring, monetizable workflows with low operational complexity. "
    "Do not suggest posting, replying, or promoting anything publicly."
)

DEFAULT_CRM_DIRECTION_SUMMARY = (
    "You are researching how a solo founder should shape a CRM product. "
    "Focus on recurring lead follow-up, pipeline hygiene, relationship memory, handoff coordination, "
    "and admin-heavy client workflows with measurable operational ROI. "
    "Do not suggest posting, replying, or promoting anything publicly."
)


@dataclass(frozen=True, slots=True)
class DraftedProspectEmail:
    post: SocialPost
    matched_query: str
    score: int
    reasons: tuple[str, ...]
    suggested_reply: str


@dataclass(frozen=True, slots=True)
class ProspectAuditEntry:
    post: SocialPost
    matched_query: str
    decision: str
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProspectingDigest:
    generated_at: datetime
    profile: str
    scanned_post_count: int
    shortlisted_count: int
    shortlisted_posts: tuple[DraftedProspectEmail, ...]
    audit_entries: tuple[ProspectAuditEntry, ...]
    token_usage: ProspectTokenUsage | None


@dataclass(frozen=True, slots=True)
class DailyProspectingConfig:
    recipient_email: str
    profile: str = "general"
    app_summary: str = DEFAULT_APP_SUMMARY
    app_url: str | None = None
    search_terms: tuple[str, ...] = DEFAULT_PROSPECT_SEARCH_TERMS
    per_term_limit: int = 8
    max_matches: int = 5
    min_score: int = 12
    verbose_audit: bool = False


class RunDailyProspectingUseCase:
    def __init__(
        self,
        lead_source: SocialLeadSourcePort,
        drafter: ProspectDraftingPort,
        email_delivery: EmailDeliveryPort,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self.lead_source = lead_source
        self.drafter = drafter
        self.email_delivery = email_delivery
        self.now = now

    def execute(self, config: DailyProspectingConfig) -> ProspectingDigest:
        seen_ids: set[str] = set()
        matches: list[ProspectMatch] = []
        scanned_count = 0
        audit_entries: list[ProspectAuditEntry] = []

        for search_term in config.search_terms:
            posts = self.lead_source.search_recent_posts(search_term, config.per_term_limit)
            scanned_count += len(posts)
            for post in posts:
                unique_key = f"{post.source}:{post.external_id}"
                if unique_key in seen_ids:
                    audit_entries.append(
                        ProspectAuditEntry(
                            post=post,
                            matched_query=search_term,
                            decision="duplicate_skipped",
                            score=0,
                            reasons=("already reviewed under an earlier query",),
                        )
                    )
                    continue
                seen_ids.add(unique_key)
                match = score_social_post(post, search_term)
                if match is not None:
                    matches.append(match)
                    audit_entries.append(
                        ProspectAuditEntry(
                            post=post,
                            matched_query=search_term,
                            decision="candidate_shortlisted",
                            score=match.score,
                            reasons=match.reasons,
                        )
                    )
                else:
                    audit_entries.append(
                        ProspectAuditEntry(
                            post=post,
                            matched_query=search_term,
                            decision="rejected",
                            score=0,
                            reasons=_build_rejection_reasons(post, search_term),
                        )
                    )

        ranked = tuple(
            sorted(
                (match for match in matches if match.score >= config.min_score),
                key=lambda item: (item.score, item.post.created_at),
                reverse=True,
            )[: config.max_matches]
        )
        drafted_replies = self.drafter.draft_promotional_replies(config.app_summary, ranked, config.app_url)
        drafted_matches = tuple(
            DraftedProspectEmail(
                post=match.post,
                matched_query=match.matched_query,
                score=match.score,
                reasons=match.reasons,
                suggested_reply=drafted_replies[index],
            )
            for index, match in enumerate(ranked)
        )
        digest = ProspectingDigest(
            generated_at=self.now(),
            profile=config.profile,
            scanned_post_count=scanned_count,
            shortlisted_count=len(drafted_matches),
            shortlisted_posts=drafted_matches,
            audit_entries=tuple(audit_entries),
            token_usage=self.drafter.get_last_usage(),
        )
        self.email_delivery.send_email(
            recipient=config.recipient_email,
            subject=f"Daily prospecting digest for {digest.generated_at.date().isoformat()}",
            text_body=format_digest_email(config, digest),
        )
        return digest


def format_digest_email(config: DailyProspectingConfig, digest: ProspectingDigest) -> str:
    decision_counts = _build_decision_counts(digest.audit_entries)
    lines = [
        f"Daily prospecting digest generated at {digest.generated_at.isoformat()}",
        f"Profile: {digest.profile}",
        f"Recipient: {config.recipient_email}",
        f"Scanned posts: {digest.scanned_post_count}",
        f"Shortlisted posts: {digest.shortlisted_count}",
        f"Audited decisions: {len(digest.audit_entries)}",
        (
            "Decision summary: "
            f"shortlisted={decision_counts['candidate_shortlisted']}, "
            f"rejected={decision_counts['rejected']}, "
            f"duplicates={decision_counts['duplicate_skipped']}"
        ),
        "",
    ]

    if digest.token_usage is not None:
        lines.extend(
            [
                "OpenAI token usage:",
                (
                    f"- model={digest.token_usage.model} "
                    f"input={digest.token_usage.input_tokens} "
                    f"output={digest.token_usage.output_tokens} "
                    f"total={digest.token_usage.total_tokens}"
                ),
                "",
            ]
        )

    if config.app_url:
        lines.extend([f"Reference URL: {config.app_url}", ""])

    if digest.shortlisted_posts:
        lines.extend(["Potential app concepts:", ""])

    for index, item in enumerate(digest.shortlisted_posts, start=1):
        excerpt = _summarize_post_text(item.post.title, item.post.body, max_length=180)
        lines.extend(
            [
                f"{index}. App concept",
                f"Description: {item.suggested_reply}",
                f"Why it looks promising: {', '.join(item.reasons)}",
                f"Observed workflow signal: {excerpt or item.post.title}",
                f"Source mix: {item.post.source} via query '{item.matched_query}'",
                f"Opportunity score: {item.score}",
                "",
            ]
        )

    if not digest.shortlisted_posts:
        lines.extend(["No strong SaaS opportunity signals were found today.", ""])

    if config.verbose_audit:
        lines.extend(["Full audit trail:", ""])
        for index, entry in enumerate(digest.audit_entries, start=1):
            excerpt = _summarize_post_text(entry.post.title, entry.post.body, max_length=140)
            lines.extend(
                [
                    f"{index}. Audited post",
                    f"Source: {entry.post.source}",
                    f"Title: {entry.post.title}",
                    f"Author: {entry.post.author}",
                    f"Posted at: {entry.post.created_at.isoformat()}",
                    f"URL: {entry.post.permalink}",
                    f"Matched query: {entry.matched_query}",
                    f"Decision: {entry.decision}",
                    f"Score: {entry.score}",
                    f"Reasons: {', '.join(entry.reasons)}",
                    f"Summary: {excerpt or '(no body text)'}",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "Audit detail mode: concise",
                "Only synthesized app concepts are shown in full.",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def _build_rejection_reasons(post: SocialPost, matched_query: str) -> tuple[str, ...]:
    haystack = f"{post.title}\n{post.body}".lower()
    reasons: list[str] = []

    excluded_keywords = ("hiring", "job", "job opening", "for hire", "meme coin", "sports betting")
    matched_exclusions = [keyword for keyword in excluded_keywords if keyword in haystack]
    if matched_exclusions:
        reasons.extend(f"filtered by excluded keyword {keyword}" for keyword in matched_exclusions)
        return tuple(reasons)

    if matched_query.lower() not in haystack:
        reasons.append("did not include the matched query phrase directly")
    if "?" not in post.title and "?" not in post.body:
        reasons.append("did not ask a direct question")
    reasons.append("insufficient intent or fit score for shortlist")
    return tuple(reasons)


def _build_decision_counts(audit_entries: tuple[ProspectAuditEntry, ...]) -> dict[str, int]:
    counts = {
        "candidate_shortlisted": 0,
        "rejected": 0,
        "duplicate_skipped": 0,
    }
    for entry in audit_entries:
        counts[entry.decision] = counts.get(entry.decision, 0) + 1
    return counts


def _summarize_post_text(title: str, body: str, max_length: int) -> str:
    normalized_body = " ".join(body.strip().split())
    if not normalized_body:
        return ""

    first_sentence = normalized_body.split(". ", 1)[0].strip()
    candidate = first_sentence if first_sentence else normalized_body
    if candidate.lower() == title.strip().lower():
        candidate = normalized_body

    if len(candidate) <= max_length:
        return candidate
    return f"{candidate[: max_length - 3].rstrip()}..."
