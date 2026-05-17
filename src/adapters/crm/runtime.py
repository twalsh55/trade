from __future__ import annotations

import os
from functools import lru_cache

from psycopg import OperationalError

from src.adapters.crm.in_memory_follow_up_repository import InMemoryLeadFollowUpRepository
from src.adapters.crm.postgres_follow_up_repository import PostgresLeadFollowUpRepository
from src.adapters.llm.openai_crm_image_intake import OpenAICRMImageIntakeAgent
from src.adapters.llm.openai_crm_spreadsheet_assist import OpenAICRMSpreadsheetAssistAgent
from src.env_utils import get_first_configured_env


@lru_cache(maxsize=1)
def build_lead_follow_up_repository() -> InMemoryLeadFollowUpRepository | PostgresLeadFollowUpRepository:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return InMemoryLeadFollowUpRepository()

    repository = PostgresLeadFollowUpRepository(database_url=database_url)
    try:
        repository.ensure_schema()
    except OperationalError as exc:
        raise RuntimeError(
            "CRM database is unavailable. Check DATABASE_URL. "
            "Railway internal hostnames such as 'postgres.railway.internal' only work inside Railway's private network."
        ) from exc
    return repository


def build_crm_image_intake_agent_from_env() -> OpenAICRMImageIntakeAgent:
    api_key = get_first_configured_env("APP_OPENAI_API_KEY", "OPENAI_API_KEY")
    if not api_key:
        raise ValueError("AI note image intake is unavailable because no app OpenAI key is configured.")
    return OpenAICRMImageIntakeAgent(
        api_key=api_key,
        model="gpt-4.1-mini",
    )


def build_crm_spreadsheet_assist_agent_from_env() -> OpenAICRMSpreadsheetAssistAgent:
    api_key = get_first_configured_env("APP_OPENAI_API_KEY", "OPENAI_API_KEY")
    if not api_key:
        raise ValueError("AI spreadsheet header assistance is unavailable because no app OpenAI key is configured.")
    return OpenAICRMSpreadsheetAssistAgent(
        api_key=api_key,
        model="gpt-4.1-mini",
    )
