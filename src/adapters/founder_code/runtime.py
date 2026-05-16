from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import httpx
from psycopg import OperationalError

from src.adapters.persistence.postgres_founder_code_request_repository import PostgresFounderCodeRequestRepository


def build_founder_code_request_repository():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for founder code request storage.")
    repository = PostgresFounderCodeRequestRepository(database_url=database_url)
    try:
        repository.ensure_schema()
    except OperationalError as exc:
        raise RuntimeError(
            "Founder code request database is unavailable. Check DATABASE_URL. "
            "Railway internal hostnames such as 'postgres.railway.internal' only work inside Railway's private network."
        ) from exc
    return repository


def sync_founder_code_requests_from_api() -> int:
    base_url = (
        os.getenv("AUTONOMOUS_SYNC_API_BASE_URL", "").strip()
        or "https://api.brivoly.com"
    )
    internal_secret = (
        os.getenv("INTERNAL_CRON_SECRET", "").strip()
        or os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    )
    if not internal_secret:
        raise ValueError("Missing INTERNAL_CRON_SECRET or TELEGRAM_WEBHOOK_SECRET for founder code sync.")

    cursor_path = Path(
        os.getenv("AUTONOMOUS_CODE_CURSOR_FILE", "var/founder_code_cursor.txt").strip()
        or "var/founder_code_cursor.txt"
    )
    inbox_path = Path(
        os.getenv("AUTONOMOUS_CODE_INBOX_FILE", "var/founder_code_inbox.jsonl").strip()
        or "var/founder_code_inbox.jsonl"
    )
    limit = parse_positive_int("AUTONOMOUS_CODE_SYNC_LIMIT", default=25)
    since = _read_cursor(cursor_path)

    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/internal/founder-code-requests",
            headers={"X-Internal-Cron-Secret": internal_secret},
            params={"limit": limit, **({"since": since} if since else {})},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Unable to sync founder code requests from the API.") from exc
    requests = payload.get("requests", [])
    if not isinstance(requests, list):
        raise RuntimeError("Founder code sync returned an invalid payload.")

    if not requests:
        return 0

    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    latest_created_at = since
    with inbox_path.open("a", encoding="utf-8") as handle:
        for item in requests:
            if not isinstance(item, dict):
                continue
            handle.write(json.dumps(item, sort_keys=True))
            handle.write("\n")
            created_at = item.get("created_at")
            if isinstance(created_at, str):
                latest_created_at = created_at
    if latest_created_at:
        cursor_path.parent.mkdir(parents=True, exist_ok=True)
        cursor_path.write_text(latest_created_at, encoding="utf-8")
    return len(requests)


def parse_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _read_cursor(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        return None
    datetime.fromisoformat(value)
    return value
