from __future__ import annotations

from datetime import UTC, datetime

from src.domain.prospecting import SocialPost, score_social_post


def build_post(title: str, body: str) -> SocialPost:
    return SocialPost(
        source="reddit",
        external_id="abc123",
        title=title,
        body=body,
        author="alice",
        permalink="https://example.com/post",
        created_at=datetime(2026, 5, 14, tzinfo=UTC),
    )


def test_score_social_post_returns_ranked_match() -> None:
    post = build_post(
        "Looking for a market crash dashboard app?",
        "I need a tool to monitor portfolio risk and set alerts during volatility.",
    )

    match = score_social_post(post, "market crash dashboard")

    assert match is not None
    assert match.score >= 8
    assert "asks a question" in match.reasons
    assert "mentions crash" in match.reasons


def test_score_social_post_filters_low_intent_posts() -> None:
    post = build_post("Daily market recap", "Stocks moved around today.")
    assert score_social_post(post, "market crash dashboard") is None


def test_score_social_post_filters_excluded_topics() -> None:
    post = build_post("Hiring for fintech role", "This is a job opening for a trading startup.")
    assert score_social_post(post, "portfolio risk dashboard") is None
