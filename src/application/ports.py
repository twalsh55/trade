from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

from src.domain.auth import ExternalIdentity, User


class MarketDataPort(Protocol):
    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Return close prices indexed by date with ticker columns."""


class AuthProviderPort(Protocol):
    def authenticate_session_token(self, session_token: str) -> ExternalIdentity:
        """Validate a provider session token and return a normalized identity."""


class UserRepositoryPort(Protocol):
    def upsert_authenticated_user(self, identity: ExternalIdentity) -> User:
        """Create or update the internal user record for an authenticated identity."""
