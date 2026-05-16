from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.domain.prospecting import ProspectTokenUsage

if TYPE_CHECKING:
    from src.application.ports import EmailDeliveryPort, ProductUpdateLogPort, ProspectRunHistoryPort


DEFAULT_OPERATOR_BRIEFING_GOAL = (
    "Zero in on a narrow, recurring CRM workflow with measurable ROI, low support burden, "
    "and fast time-to-revenue for a solo founder."
)

THEME_DEFINITIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "lead follow-up discipline",
        ("follow up", "follow-up", "reminder", "next touch", "touchpoint"),
        "Missed follow-ups keep showing up as a recurring pain, which supports building reminders, next actions, and accountability into the CRM.",
    ),
    (
        "pipeline hygiene",
        ("pipeline", "stage", "deal", "handoff"),
        "Teams appear to lose momentum when pipeline state is stale or handoffs are loose, which points toward stage hygiene and ownership workflows.",
    ),
    (
        "relationship memory",
        ("notes", "relationship", "context", "handoff", "history"),
        "Operators need a durable memory of what happened with each lead or client, suggesting a timeline and structured notes are valuable.",
    ),
    (
        "spreadsheet replacement",
        ("spreadsheet", "excel", "csv", "manual", "copy/paste"),
        "Manual spreadsheet-heavy work still shows up often, which is a strong sign of repetitive admin pain and measurable ROI.",
    ),
    (
        "agency or client coordination",
        ("agency", "client", "account manager", "handoff"),
        "Agency-style client workflows look promising because they are recurring, operational, and easier to price against saved time.",
    ),
)


@dataclass(frozen=True, slots=True)
class ShortlistedIdeaRecord:
    source: str
    matched_query: str
    score: int
    reasons: tuple[str, ...]
    description: str
    observed_signal: str


@dataclass(frozen=True, slots=True)
class ProspectRunRecord:
    generated_at: datetime
    profile: str
    scanned_post_count: int
    shortlisted_count: int
    shortlisted_ideas: tuple[ShortlistedIdeaRecord, ...]
    token_usage: ProspectTokenUsage | None


@dataclass(frozen=True, slots=True)
class ProductUpdateRecord:
    recorded_at: datetime
    category: str
    title: str
    summary: str
    agent_guidance: str
    profitability_note: str


@dataclass(frozen=True, slots=True)
class DailyOperatorBriefingConfig:
    recipient_email: str
    lookback_hours: int = 24
    goal: str = DEFAULT_OPERATOR_BRIEFING_GOAL
    trigger_label: str = "scheduled update"


@dataclass(frozen=True, slots=True)
class OperatorGuidancePoint:
    theme: str
    count: int
    explanation: str


@dataclass(frozen=True, slots=True)
class OperatorBriefing:
    generated_at: datetime
    lookback_started_at: datetime
    prospect_run_count: int
    total_scanned_posts: int
    total_shortlisted_ideas: int
    top_ideas: tuple[ShortlistedIdeaRecord, ...]
    guidance_points: tuple[OperatorGuidancePoint, ...]
    product_updates: tuple[ProductUpdateRecord, ...]
    profitability_assessment: str
    recommended_next_step: str
    token_usage: ProspectTokenUsage | None


class RunDailyOperatorBriefingUseCase:
    def __init__(
        self,
        prospect_history: ProspectRunHistoryPort,
        product_updates: ProductUpdateLogPort,
        email_delivery: EmailDeliveryPort,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self.prospect_history = prospect_history
        self.product_updates = product_updates
        self.email_delivery = email_delivery
        self.now = now

    def execute(self, config: DailyOperatorBriefingConfig) -> OperatorBriefing:
        generated_at = self.now()
        lookback_started_at = generated_at - timedelta(hours=config.lookback_hours)
        prospect_runs = self.prospect_history.list_prospect_runs(lookback_started_at)
        updates = self.product_updates.list_product_updates(lookback_started_at)
        ideas = _collect_top_ideas(prospect_runs)
        guidance_points = _derive_guidance_points(ideas)
        profitability_assessment = _build_profitability_assessment(guidance_points, updates, config.goal)
        recommended_next_step = _build_recommended_next_step(guidance_points)
        token_usage = _merge_token_usage(prospect_runs)

        briefing = OperatorBriefing(
            generated_at=generated_at,
            lookback_started_at=lookback_started_at,
            prospect_run_count=len(prospect_runs),
            total_scanned_posts=sum(item.scanned_post_count for item in prospect_runs),
            total_shortlisted_ideas=sum(item.shortlisted_count for item in prospect_runs),
            top_ideas=ideas,
            guidance_points=guidance_points,
            product_updates=tuple(sorted(updates, key=lambda item: item.recorded_at, reverse=True)),
            profitability_assessment=profitability_assessment,
            recommended_next_step=recommended_next_step,
            token_usage=token_usage,
        )
        self.email_delivery.send_email(
            recipient=config.recipient_email,
            subject=f"Operator briefing ({config.trigger_label}) for {generated_at.date().isoformat()}",
            text_body=format_operator_briefing_email(config, briefing),
        )
        return briefing


def format_operator_briefing_email(config: DailyOperatorBriefingConfig, briefing: OperatorBriefing) -> str:
    model_path, intelligence_setting = _describe_model_usage(briefing.token_usage)
    summary_line = (
        f"Runs {briefing.prospect_run_count} | scanned {briefing.total_scanned_posts} | "
        f"ideas {briefing.total_shortlisted_ideas} | model {model_path} | {intelligence_setting}"
    )
    if briefing.token_usage is not None:
        usage_line = (
            f"Token usage: {briefing.token_usage.total_tokens} total "
            f"({briefing.token_usage.input_tokens} in / {briefing.token_usage.output_tokens} out)"
        )
    else:
        usage_line = "Token usage: template mode or no OpenAI drafting recorded"

    lines = [
        f"Operator briefing generated at {briefing.generated_at.isoformat()}",
        f"Trigger: {config.trigger_label}",
        summary_line,
        usage_line,
        "",
        f"Goal: {config.goal}",
    ]

    lines.extend(["", "Agent guidance:"])
    if briefing.guidance_points:
        for item in briefing.guidance_points[:2]:
            lines.append(f"- {item.theme}: {item.explanation}")
    else:
        lines.append("- No repeated guidance patterns were strong enough to matter.")

    lines.extend(["", "Top signals:"])
    if briefing.top_ideas:
        for index, item in enumerate(briefing.top_ideas[:2], start=1):
            lines.append(f"{index}. {item.description}")
            lines.append(f"   {item.source} via '{item.matched_query}' | {item.observed_signal}")
    else:
        lines.append("- No strong ideas were shortlisted.")

    lines.extend(["", "Shipped work:"])
    if briefing.product_updates:
        for item in briefing.product_updates[:3]:
            lines.append(f"- [{item.category}] {item.title}: {item.summary}")
    else:
        lines.append("- No product updates were logged.")

    lines.extend(
        [
            "",
            "Profitability read:",
            briefing.profitability_assessment,
            "",
            "Next move:",
            briefing.recommended_next_step,
        ]
    )

    return "\n".join(lines).rstrip()


def _describe_model_usage(token_usage: ProspectTokenUsage | None) -> tuple[str, str]:
    if token_usage is None:
        return ("template fallback", "deterministic fallback, no live OpenAI reasoning")
    return (token_usage.model, "live OpenAI reasoning")


def _collect_top_ideas(prospect_runs: list[ProspectRunRecord]) -> tuple[ShortlistedIdeaRecord, ...]:
    ideas = [idea for run in prospect_runs for idea in run.shortlisted_ideas]
    ranked = sorted(ideas, key=lambda item: item.score, reverse=True)
    return tuple(ranked[:5])


def _derive_guidance_points(ideas: tuple[ShortlistedIdeaRecord, ...]) -> tuple[OperatorGuidancePoint, ...]:
    theme_counts: Counter[str] = Counter()
    theme_explanations: dict[str, str] = {}
    for idea in ideas:
        haystack = " ".join(
            (
                idea.description,
                idea.observed_signal,
                idea.matched_query,
                " ".join(idea.reasons),
            )
        ).lower()
        for theme, keywords, explanation in THEME_DEFINITIONS:
            if any(keyword in haystack for keyword in keywords):
                theme_counts[theme] += 1
                theme_explanations[theme] = explanation

    ranked = sorted(theme_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    return tuple(
        OperatorGuidancePoint(theme=theme, count=count, explanation=theme_explanations[theme])
        for theme, count in ranked
    )


def _build_profitability_assessment(
    guidance_points: tuple[OperatorGuidancePoint, ...],
    updates: list[ProductUpdateRecord],
    goal: str,
) -> str:
    if not guidance_points:
        return (
            "The signal is still weak today, so the safest move is to keep learning before expanding scope. "
            f"The current goal remains: {goal}"
        )

    top_themes = ", ".join(item.theme for item in guidance_points)
    updates_text = " ".join(f"{item.title} {item.summary} {item.agent_guidance}" for item in updates).lower()
    aligned_updates = sum(1 for item in guidance_points if item.theme.split()[0] in updates_text)

    if aligned_updates > 0:
        return (
            "The product work is lining up with the strongest research themes. "
            f"Current evidence points toward {top_themes}, which supports a narrower CRM focused on recurring operator pain and clear ROI."
        )

    return (
        "The agent is surfacing a clearer direction than the product log currently reflects. "
        f"Research is clustering around {top_themes}, so the roadmap should keep tightening toward that operational workflow."
    )


def _build_recommended_next_step(guidance_points: tuple[OperatorGuidancePoint, ...]) -> str:
    if not guidance_points:
        return "Keep the CRM surface small and gather more agent evidence before adding another major feature."

    top_theme = guidance_points[0].theme
    if top_theme == "lead follow-up discipline":
        return "Add complete, snooze, and reminder workflows to the lead follow-up queue before broadening the CRM."
    if top_theme == "pipeline hygiene":
        return "Add stage ownership and stale-deal nudges so the CRM actively improves pipeline hygiene."
    if top_theme == "relationship memory":
        return "Add a lightweight contact timeline and structured notes so follow-up decisions have context."
    if top_theme == "spreadsheet replacement":
        return "Add import and cleanup flows for spreadsheet-based leads to convert obvious admin pain into a product wedge."
    return "Keep pushing the CRM toward narrow, recurring workflows with clear operational ROI."


def _merge_token_usage(prospect_runs: list[ProspectRunRecord]) -> ProspectTokenUsage | None:
    usages = [item.token_usage for item in prospect_runs if item.token_usage is not None]
    if not usages:
        return None
    model_counts = Counter(item.model for item in usages)
    model = sorted(model_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return ProspectTokenUsage(
        model=model,
        input_tokens=sum(item.input_tokens for item in usages),
        output_tokens=sum(item.output_tokens for item in usages),
        total_tokens=sum(item.total_tokens for item in usages),
    )
