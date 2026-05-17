from __future__ import annotations

import base64
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from src.application.ports import MailboxProviderPort
from src.domain.crm import MailboxConnection, MailboxSendReceipt, MailboxThreadMessage, MailboxThreadSnapshot


class MailboxProviderError(RuntimeError):
    pass


class OAuthMailboxProviderAdapter(MailboxProviderPort):
    def __init__(self, *, http_client: httpx.Client | None = None, now: callable | None = None) -> None:
        self.http_client = http_client or httpx.Client(timeout=20.0)
        self.now = now or (lambda: datetime.now(tz=UTC))

    def build_authorization_url(self, provider: str, redirect_uri: str, state: str) -> str:
        normalized_provider = _normalize_provider(provider)
        if normalized_provider == "gmail":
            client_id = _required_env("GOOGLE_OAUTH_CLIENT_ID")
            query = urlencode(
                {
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": " ".join(_gmail_scopes()),
                    "state": state,
                    "access_type": "offline",
                    "include_granted_scopes": "true",
                    "prompt": "consent",
                }
            )
            return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

        client_id = _required_env("MICROSOFT_OAUTH_CLIENT_ID")
        tenant = os.getenv("MICROSOFT_OAUTH_TENANT_ID", "").strip() or "common"
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "response_mode": "query",
                "scope": " ".join(_microsoft_scopes()),
                "state": state,
            }
        )
        return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{query}"

    def exchange_authorization_code(
        self,
        provider: str,
        code: str,
        redirect_uri: str,
        existing_connection: MailboxConnection | None = None,
    ) -> MailboxConnection:
        normalized_provider = _normalize_provider(provider)
        normalized_code = code.strip()
        if not normalized_code:
            raise MailboxProviderError("Provider authorization code is required.")

        if normalized_provider == "gmail":
            token_payload = self._post_form(
                "https://oauth2.googleapis.com/token",
                {
                    "client_id": _required_env("GOOGLE_OAUTH_CLIENT_ID"),
                    "client_secret": _required_env("GOOGLE_OAUTH_CLIENT_SECRET"),
                    "code": normalized_code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            user_payload = self._get_json(
                "https://openidconnect.googleapis.com/v1/userinfo",
                access_token=_require_string(token_payload, "access_token"),
            )
            email_address = (_require_string(user_payload, "email") or "").strip().lower()
            display_name = _optional_string(user_payload.get("name")) or _derive_name_from_email(email_address)
            external_account_id = _optional_string(user_payload.get("sub")) or email_address
            scope = _optional_string(token_payload.get("scope")) or " ".join(_gmail_scopes())
        else:
            token_payload = self._post_form(
                f"https://login.microsoftonline.com/{os.getenv('MICROSOFT_OAUTH_TENANT_ID', '').strip() or 'common'}/oauth2/v2.0/token",
                {
                    "client_id": _required_env("MICROSOFT_OAUTH_CLIENT_ID"),
                    "client_secret": _required_env("MICROSOFT_OAUTH_CLIENT_SECRET"),
                    "code": normalized_code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "scope": " ".join(_microsoft_scopes()),
                },
            )
            user_payload = self._get_json(
                "https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName",
                access_token=_require_string(token_payload, "access_token"),
            )
            email_address = (
                _optional_string(user_payload.get("mail"))
                or _optional_string(user_payload.get("userPrincipalName"))
                or ""
            ).strip().lower()
            display_name = _optional_string(user_payload.get("displayName")) or _derive_name_from_email(email_address)
            external_account_id = _optional_string(user_payload.get("id")) or email_address
            scope = _optional_string(token_payload.get("scope")) or " ".join(_microsoft_scopes())

        if "@" not in email_address:
            raise MailboxProviderError("The provider did not return a mailbox email address.")

        issued_at = self.now()
        expires_in = _optional_int(token_payload.get("expires_in")) or 3600
        connection_id = existing_connection.id if existing_connection else f"mailbox-{normalized_provider}-{external_account_id[:18]}"
        return MailboxConnection(
            id=connection_id,
            provider=normalized_provider,
            email_address=email_address,
            display_name=display_name,
            status="connected",
            connected_at=existing_connection.connected_at if existing_connection else issued_at,
            connection_mode="oauth",
            external_account_id=external_account_id,
            access_token=_require_string(token_payload, "access_token"),
            refresh_token=_optional_string(token_payload.get("refresh_token")) or (existing_connection.refresh_token if existing_connection else ""),
            token_expires_at=issued_at + timedelta(seconds=max(60, expires_in - 30)),
            scope=scope,
            sync_cursor=existing_connection.sync_cursor if existing_connection else "",
            last_sync_at=existing_connection.last_sync_at if existing_connection else None,
            last_sync_status=existing_connection.last_sync_status if existing_connection else "",
            last_sync_error=existing_connection.last_sync_error if existing_connection else "",
            last_synced_thread_count=existing_connection.last_synced_thread_count if existing_connection else 0,
            sent_message_count=existing_connection.sent_message_count if existing_connection else 0,
        )

    def refresh_connection(self, connection: MailboxConnection) -> MailboxConnection:
        if connection.connection_mode != "oauth":
            return connection
        expiry_threshold = self.now() + timedelta(minutes=2)
        if connection.token_expires_at and connection.token_expires_at > expiry_threshold:
            return connection
        if not connection.refresh_token.strip():
            raise MailboxProviderError("Reconnect this inbox so Brivoly can keep holding relationship memory quietly.")

        normalized_provider = _normalize_provider(connection.provider)
        if normalized_provider == "gmail":
            payload = self._post_form(
                "https://oauth2.googleapis.com/token",
                {
                    "client_id": _required_env("GOOGLE_OAUTH_CLIENT_ID"),
                    "client_secret": _required_env("GOOGLE_OAUTH_CLIENT_SECRET"),
                    "refresh_token": connection.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        else:
            payload = self._post_form(
                f"https://login.microsoftonline.com/{os.getenv('MICROSOFT_OAUTH_TENANT_ID', '').strip() or 'common'}/oauth2/v2.0/token",
                {
                    "client_id": _required_env("MICROSOFT_OAUTH_CLIENT_ID"),
                    "client_secret": _required_env("MICROSOFT_OAUTH_CLIENT_SECRET"),
                    "refresh_token": connection.refresh_token,
                    "grant_type": "refresh_token",
                    "scope": " ".join(_microsoft_scopes()),
                },
            )

        expires_in = _optional_int(payload.get("expires_in")) or 3600
        return replace(
            connection,
            status="connected",
            access_token=_require_string(payload, "access_token"),
            refresh_token=_optional_string(payload.get("refresh_token")) or connection.refresh_token,
            token_expires_at=self.now() + timedelta(seconds=max(60, expires_in - 30)),
            scope=_optional_string(payload.get("scope")) or connection.scope,
            reauth_required=False,
            health_note="",
        )

    def ensure_watch_subscription(self, connection: MailboxConnection) -> MailboxConnection:
        hydrated = self.refresh_connection(connection)
        if hydrated.connection_mode != "oauth":
            return replace(
                hydrated,
                watch_status="inactive",
                health_note="Provider watch coverage only applies to OAuth-linked mailboxes.",
            )
        if hydrated.provider == "gmail":
            topic_name = os.getenv("GOOGLE_GMAIL_WATCH_TOPIC", "").strip()
            if not topic_name:
                return replace(
                    hydrated,
                    watch_status="inactive",
                    health_note="Add GOOGLE_GMAIL_WATCH_TOPIC to keep this Gmail inbox synced through provider watch events.",
                )
            payload = self._post_json(
                "https://gmail.googleapis.com/gmail/v1/users/me/watch",
                {
                    "topicName": topic_name,
                    "labelFilterBehavior": "INCLUDE",
                    "labelIds": ["INBOX", "SENT"],
                },
                access_token=hydrated.access_token,
            )
            expiration_ms = _optional_int(payload.get("expiration")) or 0
            expires_at = (
                datetime.fromtimestamp(expiration_ms / 1000, tz=UTC)
                if expiration_ms > 0
                else self.now() + timedelta(hours=12)
            )
            history_id = _optional_string(payload.get("historyId")) or hydrated.sync_cursor
            return replace(
                hydrated,
                status="connected",
                watch_status="active",
                watch_expires_at=expires_at,
                sync_cursor=history_id,
                reauth_required=False,
                health_note="",
            )
        return replace(
            hydrated,
            watch_status="manual",
            health_note="Outlook watch renewal is not configured yet, so Brivoly still relies on sync jobs for this mailbox.",
        )

    def pull_thread_updates(self, connection: MailboxConnection, max_results: int = 10) -> list[MailboxThreadSnapshot]:
        hydrated = self.refresh_connection(connection)
        if hydrated.connection_mode != "oauth":
            raise MailboxProviderError("This mailbox is not configured for provider-backed sync yet.")
        if hydrated.provider == "gmail":
            return self._pull_gmail_threads(hydrated, max_results=max_results)
        return self._pull_outlook_threads(hydrated, max_results=max_results)

    def send_message(
        self,
        connection: MailboxConnection,
        *,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
        reply_to_external_message_id: str | None = None,
    ) -> MailboxSendReceipt:
        hydrated = self.refresh_connection(connection)
        normalized_to = to_email.strip().lower()
        if "@" not in normalized_to:
            raise MailboxProviderError("A valid recipient email address is required.")
        if hydrated.connection_mode != "oauth":
            raise MailboxProviderError("This mailbox is not configured for provider-backed sending yet.")

        now = self.now()
        if hydrated.provider == "gmail":
            message = EmailMessage()
            message["From"] = f"{hydrated.display_name} <{hydrated.email_address}>"
            message["To"] = f"{to_name.strip() or normalized_to} <{normalized_to}>"
            message["Subject"] = subject
            generated_message_id = f"<gmail-{uuid4().hex[:18]}@brivoly.mail>"
            message["Message-ID"] = generated_message_id
            if reply_to_external_message_id:
                message["In-Reply-To"] = reply_to_external_message_id
                message["References"] = reply_to_external_message_id
            message.set_content(body)
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            request_payload: dict[str, object] = {"raw": raw_message}
            if thread_id:
                request_payload["threadId"] = thread_id
            response_payload = self._post_json(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                request_payload,
                access_token=hydrated.access_token,
            )
            resolved_thread_id = _optional_string(response_payload.get("threadId")) or thread_id or f"gmail-{uuid4().hex[:12]}"
            message_id = _optional_string(response_payload.get("id")) or f"gmail-sent-{uuid4().hex[:12]}"
            external_message_id = generated_message_id
        else:
            external_message_id = f"<outlook-{uuid4().hex[:18]}@brivoly.mail>"
            provider_message_id, conversation_id = (
                self._find_outlook_message_for_reply(hydrated.access_token, reply_to_external_message_id)
                if reply_to_external_message_id
                else (None, None)
            )
            if provider_message_id:
                draft_payload = self._post_json(
                    f"https://graph.microsoft.com/v1.0/me/messages/{provider_message_id}/createReply",
                    {},
                    access_token=hydrated.access_token,
                )
                draft_id = _require_string(draft_payload, "id")
                resolved_thread_id = _optional_string(draft_payload.get("conversationId")) or thread_id or conversation_id or f"outlook-{uuid4().hex[:12]}"
                self._patch_json(
                    f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}",
                    {
                        "subject": subject,
                        "body": {"contentType": "Text", "content": body},
                        "internetMessageHeaders": [
                            {"name": "Message-ID", "value": external_message_id},
                            {"name": "In-Reply-To", "value": reply_to_external_message_id},
                            {"name": "References", "value": reply_to_external_message_id},
                        ],
                    },
                    access_token=hydrated.access_token,
                )
                self._post_json(
                    f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}/send",
                    {},
                    access_token=hydrated.access_token,
                    expect_json=False,
                )
                message_id = draft_id
            else:
                resolved_thread_id, message_id = self._send_outlook_message(
                    hydrated,
                    normalized_to=normalized_to,
                    to_name=to_name,
                    subject=subject,
                    body=body,
                    thread_id=thread_id,
                    external_message_id=external_message_id,
                    reply_to_external_message_id=reply_to_external_message_id,
                )

        sent_message = MailboxThreadMessage(
            message_id=message_id,
            external_message_id=external_message_id,
            sent_at=now,
            direction="outbound",
            from_email=hydrated.email_address,
            from_name=hydrated.display_name,
            to_emails=(normalized_to,),
            subject=subject,
            body_text=body,
            snippet=body[:280],
        )
        return MailboxSendReceipt(
            connection=replace(
                hydrated,
                status="connected",
                last_sync_status="sent",
                last_sync_error="",
                last_sent_at=now,
                reauth_required=False,
                health_note="",
            ),
            thread_id=resolved_thread_id,
            message=sent_message,
        )

    def _send_outlook_message(
        self,
        connection: MailboxConnection,
        *,
        normalized_to: str,
        to_name: str,
        subject: str,
        body: str,
        thread_id: str | None,
        external_message_id: str,
        reply_to_external_message_id: str | None,
    ) -> tuple[str, str]:
        self._post_json(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body},
                    "toRecipients": [
                        {"emailAddress": {"address": normalized_to, "name": to_name.strip() or normalized_to}}
                    ],
                    "internetMessageHeaders": [
                        {"name": "Message-ID", "value": external_message_id},
                        *(
                            [
                                {"name": "In-Reply-To", "value": reply_to_external_message_id},
                                {"name": "References", "value": reply_to_external_message_id},
                            ]
                            if reply_to_external_message_id
                            else []
                        ),
                    ],
                },
                "saveToSentItems": True,
            },
            access_token=connection.access_token,
            expect_json=False,
        )
        return thread_id or f"outlook-{uuid4().hex[:12]}", f"outlook-sent-{uuid4().hex[:12]}"

    def _find_outlook_message_for_reply(self, access_token: str, external_message_id: str | None) -> tuple[str | None, str | None]:
        if not external_message_id:
            return (None, None)
        escaped = external_message_id.replace("'", "''")
        payload = self._get_json(
            f"https://graph.microsoft.com/v1.0/me/messages?$filter=internetMessageId eq '{escaped}'&$select=id,conversationId&$top=1",
            access_token=access_token,
        )
        values = payload.get("value")
        if not isinstance(values, list) or not values:
            return (None, None)
        first = values[0]
        if not isinstance(first, dict):
            return (None, None)
        return (_optional_string(first.get("id")), _optional_string(first.get("conversationId")))

    def _pull_gmail_threads(self, connection: MailboxConnection, *, max_results: int) -> list[MailboxThreadSnapshot]:
        params: dict[str, object] = {"maxResults": max(1, min(max_results, 25))}
        if connection.last_sync_at:
            params["q"] = f"after:{int(connection.last_sync_at.timestamp())}"
        payload = self._get_json(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            access_token=connection.access_token,
            params=params,
        )
        messages = payload.get("messages", [])
        if not isinstance(messages, list) or not messages:
            return []

        threads: dict[str, list[MailboxThreadMessage]] = {}
        for item in messages:
            if not isinstance(item, dict):
                continue
            message_id = _optional_string(item.get("id"))
            thread_id = _optional_string(item.get("threadId")) or message_id
            if not message_id or not thread_id:
                continue
            details = self._get_json(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
                access_token=connection.access_token,
                params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date", "Message-ID"]},
            )
            payload_headers = ((details.get("payload") or {}).get("headers") if isinstance(details.get("payload"), dict) else []) or []
            headers = _gmail_headers_to_dict(payload_headers)
            from_name, from_email = _parse_email_header(headers.get("From", ""))
            to_emails = tuple(email for _, email in getaddresses([headers.get("To", "")]) if email)
            sent_at = _parse_message_datetime(headers.get("Date")) or _parse_gmail_internal_date(details.get("internalDate")) or self.now()
            subject = headers.get("Subject", "").strip() or "No subject"
            snippet = _optional_string(details.get("snippet")) or ""
            body_text = snippet
            direction = "outbound" if from_email.strip().lower() == connection.email_address.strip().lower() else "inbound"
            threads.setdefault(thread_id, []).append(
                MailboxThreadMessage(
                    message_id=message_id,
                    external_message_id=headers.get("Message-ID", "").strip(),
                    sent_at=sent_at,
                    direction=direction,
                    from_email=from_email,
                    from_name=from_name,
                    to_emails=to_emails,
                    subject=subject,
                    body_text=body_text,
                    snippet=snippet,
                )
            )
        return [
            MailboxThreadSnapshot(
                source="gmail",
                thread_id=thread_id,
                messages=tuple(sorted(items, key=lambda message: message.sent_at)),
            )
            for thread_id, items in threads.items()
            if items
        ]

    def _pull_outlook_threads(self, connection: MailboxConnection, *, max_results: int) -> list[MailboxThreadSnapshot]:
        payload = self._get_json(
            "https://graph.microsoft.com/v1.0/me/messages",
            access_token=connection.access_token,
            params={
                "$top": str(max(1, min(max_results, 25))),
                "$orderby": "receivedDateTime DESC",
                "$select": "id,conversationId,subject,bodyPreview,receivedDateTime,sentDateTime,from,toRecipients,internetMessageId",
            },
        )
        items = payload.get("value", [])
        if not isinstance(items, list) or not items:
            return []

        threads: dict[str, list[MailboxThreadMessage]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            sent_at = _parse_iso_datetime(item.get("sentDateTime")) or _parse_iso_datetime(item.get("receivedDateTime"))
            if connection.last_sync_at and sent_at and sent_at <= connection.last_sync_at:
                continue
            from_payload = ((item.get("from") or {}).get("emailAddress") if isinstance(item.get("from"), dict) else {}) or {}
            from_email = _optional_string(from_payload.get("address")) or ""
            from_name = _optional_string(from_payload.get("name")) or _derive_name_from_email(from_email)
            to_emails = tuple(
                _optional_string(recipient.get("emailAddress", {}).get("address")) or ""
                for recipient in item.get("toRecipients", [])
                if isinstance(recipient, dict)
            )
            to_emails = tuple(email for email in to_emails if email)
            thread_id = _optional_string(item.get("conversationId")) or _optional_string(item.get("id")) or f"outlook-{uuid4().hex[:12]}"
            message_id = _optional_string(item.get("internetMessageId")) or _optional_string(item.get("id")) or f"msg-{uuid4().hex[:12]}"
            snippet = _optional_string(item.get("bodyPreview")) or ""
            direction = "outbound" if from_email.strip().lower() == connection.email_address.strip().lower() else "inbound"
            threads.setdefault(thread_id, []).append(
                MailboxThreadMessage(
                    message_id=message_id,
                    external_message_id=_optional_string(item.get("internetMessageId")) or "",
                    sent_at=sent_at or self.now(),
                    direction=direction,
                    from_email=from_email,
                    from_name=from_name,
                    to_emails=to_emails,
                    subject=_optional_string(item.get("subject")) or "No subject",
                    body_text=snippet,
                    snippet=snippet,
                )
            )
        return [
            MailboxThreadSnapshot(
                source="outlook",
                thread_id=thread_id,
                messages=tuple(sorted(messages, key=lambda message: message.sent_at)),
            )
            for thread_id, messages in threads.items()
            if messages
        ]

    def _get_json(
        self,
        url: str,
        *,
        access_token: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        response = self.http_client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        return _read_json_response(response)

    def _post_form(self, url: str, payload: dict[str, str]) -> dict[str, Any]:
        response = self.http_client.post(
            url,
            data=payload,
            headers={"Accept": "application/json"},
        )
        return _read_json_response(response)

    def _post_json(
        self,
        url: str,
        payload: dict[str, object],
        *,
        access_token: str,
        expect_json: bool = True,
    ) -> dict[str, Any]:
        response = self.http_client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if not expect_json and response.status_code in {200, 201, 202, 204}:
            return {}
        return _read_json_response(response)

    def _patch_json(
        self,
        url: str,
        payload: dict[str, object],
        *,
        access_token: str,
    ) -> dict[str, Any]:
        response = self.http_client.patch(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        return _read_json_response(response)


def _read_json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                detail = _optional_string(error_payload.get("message")) or _optional_string(error_payload.get("error_description")) or ""
            elif isinstance(error_payload, str):
                detail = error_payload
            detail = detail or _optional_string(payload.get("error_description")) or _optional_string(payload.get("message")) or ""
        raise MailboxProviderError(_normalize_provider_error(detail, response.status_code)) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise MailboxProviderError("Mailbox provider returned an invalid JSON response.") from exc
    if not isinstance(payload, dict):
        raise MailboxProviderError("Mailbox provider returned an unexpected payload.")
    return payload


def _normalize_provider(provider: str) -> str:
    normalized_provider = provider.strip().lower()
    if normalized_provider not in {"gmail", "outlook"}:
        raise MailboxProviderError("Unsupported mailbox provider.")
    return normalized_provider


def _normalize_provider_error(detail: str, status_code: int) -> str:
    normalized_detail = detail.strip()
    lower_detail = normalized_detail.lower()
    if status_code == 429:
        return "This inbox is being rate-limited right now. Brivoly can try again in a moment."
    if status_code >= 500:
        return "The mailbox provider is having a rough moment. Brivoly can try again shortly."
    if any(token in lower_detail for token in ("invalid_grant", "expired", "expired token", "invalid token", "refresh token", "oauth", "unauthorized", "forbidden", "consent_required")):
        return "Reconnect this inbox so Brivoly can keep holding relationship memory quietly."
    return normalized_detail or f"Mailbox provider request failed with status {status_code}."


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MailboxProviderError(f"{name} is required for mailbox provider auth.")
    return value


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = _optional_string(payload.get(key))
    if not value:
        raise MailboxProviderError(f"Mailbox provider response missing {key}.")
    return value


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _gmail_scopes() -> tuple[str, ...]:
    return (
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
    )


def _microsoft_scopes() -> tuple[str, ...]:
    return (
        "openid",
        "email",
        "profile",
        "offline_access",
        "https://graph.microsoft.com/Mail.ReadWrite",
        "https://graph.microsoft.com/Mail.Send",
        "https://graph.microsoft.com/User.Read",
    )


def _derive_name_from_email(email_address: str) -> str:
    local_part = email_address.split("@", 1)[0].replace(".", " ").replace("_", " ").replace("-", " ")
    return " ".join(segment.capitalize() for segment in local_part.split() if segment) or email_address


def _gmail_headers_to_dict(headers: object) -> dict[str, str]:
    if not isinstance(headers, list):
        return {}
    values: dict[str, str] = {}
    for item in headers:
        if not isinstance(item, dict):
            continue
        name = _optional_string(item.get("name"))
        value = _optional_string(item.get("value"))
        if name and value:
            values[name] = value
    return values


def _parse_email_header(raw_value: str) -> tuple[str, str]:
    parsed = getaddresses([raw_value])
    if not parsed:
        return "", ""
    name, email = parsed[0]
    return name or _derive_name_from_email(email), email.strip().lower()


def _parse_message_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        parsed = parsedate_to_datetime(raw_value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_gmail_internal_date(raw_value: object) -> datetime | None:
    if isinstance(raw_value, str) and raw_value.strip().isdigit():
        return datetime.fromtimestamp(int(raw_value.strip()) / 1000, tz=UTC)
    if isinstance(raw_value, int):
        return datetime.fromtimestamp(raw_value / 1000, tz=UTC)
    return None


def _parse_iso_datetime(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    normalized = raw_value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
