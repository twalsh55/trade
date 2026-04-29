from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt

from src.domain.auth import ExternalIdentity


class AuthenticationError(ValueError):
    """Raised when an inbound auth session cannot be trusted."""


@dataclass(frozen=True)
class ClerkAuthConfig:
    publishable_key: str
    secret_key: str | None = None
    frontend_api_url: str | None = None
    jwks_url: str | None = None
    issuer: str | None = None
    authorized_parties: tuple[str, ...] = ()

    @property
    def resolved_frontend_api_url(self) -> str:
        if self.frontend_api_url:
            return self.frontend_api_url.rstrip("/")

        try:
            encoded_domain = self.publishable_key.split("_", 2)[2]
            padded = encoded_domain + "=" * (-len(encoded_domain) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        except (IndexError, ValueError, UnicodeDecodeError) as exc:
            raise AuthenticationError("Unable to derive Clerk frontend API URL from CLERK_PUBLISHABLE_KEY.") from exc

        return f"https://{decoded[:-1]}"

    @property
    def resolved_jwks_url(self) -> str:
        if self.jwks_url:
            return self.jwks_url
        return f"{self.resolved_frontend_api_url}/.well-known/jwks.json"

    @property
    def resolved_issuer(self) -> str | None:
        return self.issuer


class ClerkAuthProvider:
    provider_name = "clerk"

    def __init__(self, config: ClerkAuthConfig) -> None:
        self.config = config
        self.jwks_client = jwt.PyJWKClient(config.resolved_jwks_url)

    def authenticate_session_token(self, session_token: str) -> ExternalIdentity:
        claims = self._verify_session_token(session_token)
        profile = self._load_user_profile(claims["sub"])

        email = _first_non_empty(
            profile.get("primary_email_address"),
            _get_primary_email_from_profile(profile),
        )
        given_name = _first_non_empty(profile.get("first_name"), claims.get("given_name"))
        family_name = _first_non_empty(profile.get("last_name"), claims.get("family_name"))
        display_name = _first_non_empty(profile.get("full_name"), email, claims.get("sub"))

        return ExternalIdentity(
            provider=self.provider_name,
            issuer=str(claims["iss"]),
            subject=str(claims["sub"]),
            session_id=_coerce_optional_string(claims.get("sid")),
            email=email,
            given_name=given_name,
            family_name=family_name,
            display_name=display_name,
        )

    def _verify_session_token(self, session_token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(session_token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid session token header.") from exc

        if header.get("alg") != "RS256":
            raise AuthenticationError("Unexpected session token signing algorithm.")

        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(session_token)
            decode_kwargs: dict[str, Any] = {
                "algorithms": ["RS256"],
                "options": {"require": ["exp", "iat", "nbf", "iss", "sub"]},
            }
            if self.config.resolved_issuer:
                decode_kwargs["issuer"] = self.config.resolved_issuer

            claims = jwt.decode(
                session_token,
                signing_key.key,
                **decode_kwargs,
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Session token verification failed.") from exc

        if self.config.authorized_parties:
            azp = claims.get("azp")
            if azp not in self.config.authorized_parties:
                raise AuthenticationError("Session token authorized party is not allowed.")

        return claims

    def _load_user_profile(self, user_id: str) -> dict[str, Any]:
        if not self.config.secret_key:
            return {}

        request = urllib.request.Request(
            url=f"https://api.clerk.com/v1/users/{user_id}",
            headers={
                "Authorization": f"Bearer {self.config.secret_key}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.URLError:
            return {}

        try:
            raw_profile = json.loads(payload)
        except json.JSONDecodeError:
            return {}

        if not isinstance(raw_profile, dict):
            return {}

        return raw_profile


def _coerce_optional_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _first_non_empty(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _get_primary_email_from_profile(profile: dict[str, Any]) -> str | None:
    primary_email_id = profile.get("primary_email_address_id")
    email_addresses = profile.get("email_addresses")
    if not isinstance(email_addresses, list):
        return None

    for item in email_addresses:
        if not isinstance(item, dict):
            continue
        if item.get("id") == primary_email_id:
            email = item.get("email_address")
            if isinstance(email, str) and email.strip():
                return email.strip()
    return None
