from __future__ import annotations

from src.application.ports import AuthProviderPort, UserRepositoryPort
from src.domain.auth import User


class AuthenticateUserUseCase:
    def __init__(self, auth_provider: AuthProviderPort, users: UserRepositoryPort) -> None:
        self.auth_provider = auth_provider
        self.users = users

    def execute(self, session_token: str | None) -> User | None:
        if not session_token:
            return None

        identity = self.auth_provider.authenticate_session_token(session_token)
        return self.users.upsert_authenticated_user(identity)
