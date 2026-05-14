from __future__ import annotations

import os
from functools import lru_cache

from psycopg import OperationalError

from src.adapters.persistence.in_memory_personalization_repository import InMemoryPersonalizationRepository
from src.adapters.persistence.postgres_personalization_repository import PostgresPersonalizationRepository


@lru_cache(maxsize=1)
def build_personalization_repository():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return InMemoryPersonalizationRepository()

    repository = PostgresPersonalizationRepository(database_url=database_url)
    try:
        repository.ensure_schema()
    except OperationalError as exc:
        raise RuntimeError(
            "Personalization database is unavailable. Check DATABASE_URL. "
            "Railway internal hostnames such as 'postgres.railway.internal' only work inside Railway's private network."
        ) from exc
    return repository
