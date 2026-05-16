from __future__ import annotations

from src.adapters.social.public_search_lead_source import PublicSearchLeadSource


class IndieHackersLeadSource(PublicSearchLeadSource):
    def __init__(
        self,
        user_agent: str = "trade-prospecting-bot/0.1",
        timeout_seconds: float = 20.0,
    ) -> None:
        super().__init__(
            source_name="indie_hackers",
            site_domains=("indiehackers.com",),
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
            author_label="indiehackers",
            failure_label="Indie Hackers search results",
        )
