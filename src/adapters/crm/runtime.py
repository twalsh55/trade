from __future__ import annotations

from src.adapters.crm.in_memory_follow_up_repository import InMemoryLeadFollowUpRepository
from src.adapters.llm.openai_crm_image_intake import OpenAICRMImageIntakeAgent
from src.env_utils import get_first_configured_env


_repository: InMemoryLeadFollowUpRepository | None = None


def build_lead_follow_up_repository() -> InMemoryLeadFollowUpRepository:
    global _repository
    if _repository is None:
        _repository = InMemoryLeadFollowUpRepository()
    return _repository


def build_crm_image_intake_agent_from_env() -> OpenAICRMImageIntakeAgent:
    api_key = get_first_configured_env("APP_OPENAI_API_KEY", "OPENAI_API_KEY")
    if not api_key:
        raise ValueError("AI note image intake is unavailable because no app OpenAI key is configured.")
    return OpenAICRMImageIntakeAgent(
        api_key=api_key,
        model="gpt-4.1-mini",
    )
