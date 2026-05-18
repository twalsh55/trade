from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest

from src.adapters.crm import mailbox_runtime
import src.adapters.crm.oauth_mailbox_provider as oauth_mailbox_provider_module
from src.adapters.crm.oauth_mailbox_provider import (
    MailboxProviderError,
    OAuthMailboxProviderAdapter,
    _gmail_headers_to_dict,
    _normalize_provider_error,
    _optional_int,
    _parse_email_header,
    _parse_gmail_internal_date,
    _parse_iso_datetime,
    _parse_message_datetime,
    _read_json_response,
    _require_string,
    _required_env,
)
from src.domain.auth import User
from src.domain.crm import MailboxConnection, MailboxThreadMessage, MailboxThreadSnapshot


def make_user() -> User:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    return User(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        auth_provider="clerk",
        auth_issuer="https://example.clerk.accounts.dev",
        auth_subject="user_123",
        stripe_customer_id=None,
        email="user@example.com",
        given_name="Ada",
        family_name="Lovelace",
        display_name="Ada Lovelace",
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


def make_connection(
    *,
    provider: str = "gmail",
    connection_mode: str = "oauth",
    status: str = "connected",
    watch_status: str = "inactive",
    background_sync_enabled: bool = True,
    email_address: str | None = None,
    token_expires_at: datetime | None = None,
    refresh_token: str = "refresh-token",
    watch_expires_at: datetime | None = None,
    last_sync_at: datetime | None = None,
    last_watch_event_at: datetime | None = None,
    external_account_id: str = "acct-123",
    health_note: str = "",
) -> MailboxConnection:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    email_address = "ada@example.com" if provider == "gmail" else "ada@outlook.example"
    return MailboxConnection(
        id=f"mailbox-{provider}-test",
        provider=provider,
        email_address=email_address or ("ada@example.com" if provider == "gmail" else "ada@outlook.example"),
        display_name="Ada Lovelace",
        status=status,
        connected_at=now - timedelta(days=2),
        connection_mode=connection_mode,
        background_sync_enabled=background_sync_enabled,
        access_token="access-token",
        refresh_token=refresh_token,
        token_expires_at=token_expires_at or (now - timedelta(minutes=5)),
        watch_status=watch_status,
        watch_expires_at=watch_expires_at,
        last_sync_at=last_sync_at,
        last_watch_event_at=last_watch_event_at,
        external_account_id=external_account_id,
        health_note=health_note,
    )


class FakeHttpClient:
    def __init__(self) -> None:
        self.responses: dict[tuple[str, str], list[httpx.Response]] = {}
        self.calls: list[tuple[str, str, object | None]] = []

    def queue(
        self,
        method: str,
        url: str,
        response: httpx.Response,
    ) -> None:
        self.responses.setdefault((method.upper(), url), []).append(response)

    def _pop(self, method: str, url: str, payload: object | None) -> httpx.Response:
        self.calls.append((method.upper(), url, payload))
        try:
            return self.responses[(method.upper(), url)].pop(0)
        except (KeyError, IndexError) as exc:
            raise AssertionError(f"Unexpected {method.upper()} {url}") from exc

    def get(self, url: str, *, params=None, headers=None):  # type: ignore[no-untyped-def]
        del headers
        return self._pop("GET", url, params)

    def post(self, url: str, *, data=None, json=None, headers=None):  # type: ignore[no-untyped-def]
        del headers
        return self._pop("POST", url, data if data is not None else json)

    def patch(self, url: str, *, json=None, headers=None):  # type: ignore[no-untyped-def]
        del headers
        return self._pop("PATCH", url, json)


def make_response(
    method: str,
    url: str,
    *,
    status_code: int = 200,
    json_payload: object | None = None,
    text: str | None = None,
) -> httpx.Response:
    request = httpx.Request(method.upper(), url)
    if json_payload is not None:
        return httpx.Response(status_code, json=json_payload, request=request)
    return httpx.Response(status_code, text=text or "", request=request)


def test_oauth_mailbox_provider_builds_authorization_urls(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client")
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", "ms-client")
    monkeypatch.setenv("MICROSOFT_OAUTH_TENANT_ID", "tenant-123")
    adapter = OAuthMailboxProviderAdapter(http_client=FakeHttpClient())

    gmail_url = adapter.build_authorization_url(
        "gmail",
        "https://app.example/callback",
        "state-123",
    )
    outlook_url = adapter.build_authorization_url(
        "outlook",
        "https://app.example/callback",
        "state-123",
    )

    assert "accounts.google.com" in gmail_url
    assert "google-client" in gmail_url
    assert "login.microsoftonline.com/tenant-123" in outlook_url
    assert "ms-client" in outlook_url

    with pytest.raises(MailboxProviderError, match="Unsupported mailbox provider."):
        adapter.build_authorization_url("imap", "https://app.example/callback", "state-123")


def test_oauth_mailbox_provider_exchanges_codes_for_gmail_and_outlook(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", "ms-client")
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_SECRET", "ms-secret")
    monkeypatch.setenv("MICROSOFT_OAUTH_TENANT_ID", "tenant-123")
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    client = FakeHttpClient()
    client.queue(
        "POST",
        "https://oauth2.googleapis.com/token",
        make_response(
            "POST",
            "https://oauth2.googleapis.com/token",
            json_payload={
                "access_token": "gmail-access",
                "refresh_token": "gmail-refresh",
                "expires_in": 1800,
                "scope": "gmail-scope",
            },
        ),
    )
    client.queue(
        "GET",
        "https://openidconnect.googleapis.com/v1/userinfo",
        make_response(
            "GET",
            "https://openidconnect.googleapis.com/v1/userinfo",
            json_payload={
                "email": "ada@example.com",
                "name": "Ada Lovelace",
                "sub": "google-subject",
            },
        ),
    )
    client.queue(
        "POST",
        "https://login.microsoftonline.com/tenant-123/oauth2/v2.0/token",
        make_response(
            "POST",
            "https://login.microsoftonline.com/tenant-123/oauth2/v2.0/token",
            json_payload={
                "access_token": "outlook-access",
                "refresh_token": "outlook-refresh",
                "expires_in": 3600,
            },
        ),
    )
    client.queue(
        "GET",
        "https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName",
        make_response(
            "GET",
            "https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName",
            json_payload={
                "id": "graph-id",
                "displayName": "Ada Outlook",
                "userPrincipalName": "ada@outlook.example",
            },
        ),
    )
    adapter = OAuthMailboxProviderAdapter(http_client=client, now=lambda: now)

    with pytest.raises(MailboxProviderError, match="authorization code is required"):
        adapter.exchange_authorization_code(
            "gmail",
            " ",
            "https://app.example/callback",
        )

    gmail_connection = adapter.exchange_authorization_code(
        "gmail",
        "code-123",
        "https://app.example/callback",
    )
    outlook_connection = adapter.exchange_authorization_code(
        "outlook",
        "code-456",
        "https://app.example/callback",
    )

    assert gmail_connection.provider == "gmail"
    assert gmail_connection.email_address == "ada@example.com"
    assert gmail_connection.external_account_id == "google-subject"
    assert outlook_connection.provider == "outlook"
    assert outlook_connection.email_address == "ada@outlook.example"
    assert outlook_connection.display_name == "Ada Outlook"

    client_missing_email = FakeHttpClient()
    client_missing_email.queue(
        "POST",
        "https://oauth2.googleapis.com/token",
        make_response(
            "POST",
            "https://oauth2.googleapis.com/token",
            json_payload={"access_token": "gmail-access", "refresh_token": "gmail-refresh"},
        ),
    )
    client_missing_email.queue(
        "GET",
        "https://openidconnect.googleapis.com/v1/userinfo",
        make_response(
            "GET",
            "https://openidconnect.googleapis.com/v1/userinfo",
            json_payload={"email": "not-an-email", "name": "Ada"},
        ),
    )
    missing_email_adapter = OAuthMailboxProviderAdapter(
        http_client=client_missing_email,
        now=lambda: now,
    )
    with pytest.raises(
        MailboxProviderError,
        match="did not return a mailbox email address",
    ):
        missing_email_adapter.exchange_authorization_code(
            "gmail",
            "code-123",
            "https://app.example/callback",
        )


def test_oauth_mailbox_provider_refresh_and_watch_subscription_paths(monkeypatch) -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_ID", "ms-client")
    monkeypatch.setenv("MICROSOFT_OAUTH_CLIENT_SECRET", "ms-secret")
    monkeypatch.setenv("MICROSOFT_OAUTH_TENANT_ID", "tenant-123")
    client = FakeHttpClient()
    client.queue(
        "POST",
        "https://oauth2.googleapis.com/token",
        make_response(
            "POST",
            "https://oauth2.googleapis.com/token",
            json_payload={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 7200,
                "scope": "gmail-scope",
            },
        ),
    )
    client.queue(
        "POST",
        "https://login.microsoftonline.com/tenant-123/oauth2/v2.0/token",
        make_response(
            "POST",
            "https://login.microsoftonline.com/tenant-123/oauth2/v2.0/token",
            json_payload={
                "access_token": "ms-access",
                "refresh_token": "ms-refresh",
                "expires_in": 3600,
                "scope": "outlook-scope",
            },
        ),
    )
    client.queue(
        "POST",
        "https://gmail.googleapis.com/gmail/v1/users/me/watch",
        make_response(
            "POST",
            "https://gmail.googleapis.com/gmail/v1/users/me/watch",
            json_payload={"expiration": str(int((now + timedelta(hours=4)).timestamp() * 1000)), "historyId": "history-123"},
        ),
    )
    adapter = OAuthMailboxProviderAdapter(http_client=client, now=lambda: now)

    manual_connection = make_connection(connection_mode="manual", provider="gmail")
    assert adapter.refresh_connection(manual_connection) == manual_connection

    valid_connection = make_connection(
        provider="gmail",
        token_expires_at=now + timedelta(hours=1),
    )
    assert adapter.refresh_connection(valid_connection) == valid_connection

    missing_refresh = make_connection(provider="gmail", refresh_token="")
    with pytest.raises(MailboxProviderError, match="Reconnect this inbox"):
        adapter.refresh_connection(missing_refresh)

    refreshed = adapter.refresh_connection(make_connection(provider="gmail"))
    assert refreshed.access_token == "new-access"
    assert refreshed.refresh_token == "new-refresh"
    refreshed_outlook = adapter.refresh_connection(
        make_connection(
            provider="outlook",
            email_address="ada@outlook.example",
        )
    )
    assert refreshed_outlook.access_token == "ms-access"

    non_oauth_watch = adapter.ensure_watch_subscription(
        make_connection(connection_mode="manual"),
    )
    assert non_oauth_watch.watch_status == "inactive"

    monkeypatch.delenv("GOOGLE_GMAIL_WATCH_TOPIC", raising=False)
    no_topic = adapter.ensure_watch_subscription(
        replace(refreshed, token_expires_at=now + timedelta(hours=1)),
    )
    assert no_topic.watch_status == "inactive"
    assert "GOOGLE_GMAIL_WATCH_TOPIC" in no_topic.health_note

    monkeypatch.setenv("GOOGLE_GMAIL_WATCH_TOPIC", "projects/test/topics/gmail")
    watched = adapter.ensure_watch_subscription(
        replace(refreshed, token_expires_at=now + timedelta(hours=1)),
    )
    assert watched.watch_status == "active"
    assert watched.sync_cursor == "history-123"

    outlook_adapter = OAuthMailboxProviderAdapter(http_client=FakeHttpClient(), now=lambda: now)
    outlook_watch = outlook_adapter.ensure_watch_subscription(
        make_connection(
            provider="outlook",
            token_expires_at=now + timedelta(hours=1),
        ),
    )
    assert outlook_watch.watch_status == "manual"


def test_oauth_mailbox_provider_pulls_threads_and_sends_messages(monkeypatch) -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    monkeypatch.setenv("GOOGLE_GMAIL_WATCH_TOPIC", "projects/test/topics/gmail")
    client = FakeHttpClient()
    client.queue(
        "GET",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        make_response(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            json_payload={"messages": [{"id": "msg-1", "threadId": "thread-1"}]},
        ),
    )
    client.queue(
        "GET",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/msg-1",
        make_response(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/msg-1",
            json_payload={
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Client <client@example.com>"},
                        {"name": "To", "value": "Ada <ada@example.com>"},
                        {"name": "Subject", "value": "Quick follow-up"},
                        {"name": "Date", "value": "Mon, 06 May 2024 12:00:00 +0000"},
                        {"name": "Message-ID", "value": "<gmail-1@example.com>"},
                    ]
                },
                "internalDate": str(int(now.timestamp() * 1000)),
                "snippet": "Checking in.",
            },
        ),
    )
    client.queue(
        "POST",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        make_response(
            "POST",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            json_payload={"id": "gmail-sent-1", "threadId": "thread-1"},
        ),
    )
    client.queue(
        "GET",
        "https://graph.microsoft.com/v1.0/me/messages",
        make_response(
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages",
            json_payload={
                "value": [
                    {
                        "id": "outlook-id-1",
                        "conversationId": "conversation-1",
                        "subject": "Hello",
                        "bodyPreview": "Preview",
                        "receivedDateTime": "2024-05-06T12:00:00Z",
                        "sentDateTime": "2024-05-06T12:00:00Z",
                        "from": {"emailAddress": {"address": "client@example.com", "name": "Client"}},
                        "toRecipients": [{"emailAddress": {"address": "ada@outlook.example", "name": "Ada"}}],
                        "internetMessageId": "<outlook-1@example.com>",
                    }
                ]
            },
        ),
    )
    client.queue(
        "GET",
        "https://graph.microsoft.com/v1.0/me/messages?$filter=internetMessageId eq '<gmail-1@example.com>'&$select=id,conversationId&$top=1",
        make_response(
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages?$filter=internetMessageId eq '<gmail-1@example.com>'&$select=id,conversationId&$top=1",
            json_payload={"value": [{"id": "provider-message-1", "conversationId": "conversation-1"}]},
        ),
    )
    client.queue(
        "POST",
        "https://graph.microsoft.com/v1.0/me/messages/provider-message-1/createReply",
        make_response(
            "POST",
            "https://graph.microsoft.com/v1.0/me/messages/provider-message-1/createReply",
            json_payload={"id": "draft-1", "conversationId": "conversation-1"},
        ),
    )
    client.queue(
        "PATCH",
        "https://graph.microsoft.com/v1.0/me/messages/draft-1",
        make_response(
            "PATCH",
            "https://graph.microsoft.com/v1.0/me/messages/draft-1",
            json_payload={},
        ),
    )
    client.queue(
        "POST",
        "https://graph.microsoft.com/v1.0/me/messages/draft-1/send",
        make_response(
            "POST",
            "https://graph.microsoft.com/v1.0/me/messages/draft-1/send",
            status_code=202,
            text="",
        ),
    )
    client.queue(
        "GET",
        "https://graph.microsoft.com/v1.0/me/messages?$filter=internetMessageId eq '<missing@example.com>'&$select=id,conversationId&$top=1",
        make_response(
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages?$filter=internetMessageId eq '<missing@example.com>'&$select=id,conversationId&$top=1",
            json_payload={"value": []},
        ),
    )
    client.queue(
        "POST",
        "https://graph.microsoft.com/v1.0/me/sendMail",
        make_response(
            "POST",
            "https://graph.microsoft.com/v1.0/me/sendMail",
            status_code=202,
            text="",
        ),
    )
    adapter = OAuthMailboxProviderAdapter(http_client=client, now=lambda: now)

    with pytest.raises(
        MailboxProviderError,
        match="provider-backed sync yet",
    ):
        adapter.pull_thread_updates(make_connection(connection_mode="manual"))

    gmail_threads = adapter.pull_thread_updates(
        make_connection(
            provider="gmail",
            token_expires_at=now + timedelta(hours=1),
            last_sync_at=now - timedelta(days=1),
        ),
    )
    assert len(gmail_threads) == 1
    assert gmail_threads[0].messages[0].subject == "Quick follow-up"
    assert adapter._find_outlook_message_for_reply("access-token", None) == (None, None)

    outlook_threads = adapter.pull_thread_updates(
        make_connection(
            provider="outlook",
            token_expires_at=now + timedelta(hours=1),
            email_address="ada@outlook.example",
        ),
    )
    assert len(outlook_threads) == 1
    assert outlook_threads[0].thread_id == "conversation-1"

    empty_client = FakeHttpClient()
    empty_client.queue(
        "GET",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        make_response(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            json_payload={"messages": []},
        ),
    )
    empty_client.queue(
        "GET",
        "https://graph.microsoft.com/v1.0/me/messages",
        make_response(
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages",
            json_payload={"value": [None, {"id": "old", "sentDateTime": "2024-05-05T12:00:00Z"}]},
        ),
    )
    empty_client.queue(
        "GET",
        "https://graph.microsoft.com/v1.0/me/messages?$filter=internetMessageId eq '<missing@example.com>'&$select=id,conversationId&$top=1",
        make_response(
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages?$filter=internetMessageId eq '<missing@example.com>'&$select=id,conversationId&$top=1",
            json_payload={"value": [None]},
        ),
    )
    sparse_adapter = OAuthMailboxProviderAdapter(http_client=empty_client, now=lambda: now)
    assert sparse_adapter._pull_gmail_threads(
        make_connection(provider="gmail", token_expires_at=now + timedelta(hours=1)),
        max_results=10,
    ) == []
    assert sparse_adapter._find_outlook_message_for_reply("access-token", "<missing@example.com>") == (None, None)
    assert sparse_adapter._pull_outlook_threads(
        make_connection(
            provider="outlook",
            email_address="ada@outlook.example",
            token_expires_at=now + timedelta(hours=1),
            last_sync_at=now,
        ),
        max_results=10,
    ) == []

    sparse_gmail_client = FakeHttpClient()
    sparse_gmail_client.queue(
        "GET",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        make_response(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            json_payload={"messages": [None, {"id": "", "threadId": ""}]},
        ),
    )
    sparse_gmail_adapter = OAuthMailboxProviderAdapter(http_client=sparse_gmail_client, now=lambda: now)
    assert sparse_gmail_adapter._pull_gmail_threads(
        make_connection(provider="gmail", token_expires_at=now + timedelta(hours=1)),
        max_results=10,
    ) == []

    no_items_client = FakeHttpClient()
    no_items_client.queue(
        "GET",
        "https://graph.microsoft.com/v1.0/me/messages",
        make_response(
            "GET",
            "https://graph.microsoft.com/v1.0/me/messages",
            json_payload={"value": []},
        ),
    )
    no_items_adapter = OAuthMailboxProviderAdapter(http_client=no_items_client, now=lambda: now)
    assert no_items_adapter._pull_outlook_threads(
        make_connection(
            provider="outlook",
            email_address="ada@outlook.example",
            token_expires_at=now + timedelta(hours=1),
        ),
        max_results=10,
    ) == []

    with pytest.raises(MailboxProviderError, match="valid recipient email address"):
        adapter.send_message(
            make_connection(provider="gmail", token_expires_at=now + timedelta(hours=1)),
            to_email="bad-address",
            to_name="Ada",
            subject="Hello",
            body="World",
        )

    with pytest.raises(MailboxProviderError, match="provider-backed sending yet"):
        adapter.send_message(
            make_connection(provider="gmail", connection_mode="manual", token_expires_at=now + timedelta(hours=1)),
            to_email="lead@example.com",
            to_name="Lead",
            subject="Hello",
            body="World",
        )

    gmail_receipt = adapter.send_message(
        make_connection(provider="gmail", token_expires_at=now + timedelta(hours=1)),
        to_email="lead@example.com",
        to_name="Lead",
        subject="Hello",
        body="World",
        thread_id="thread-1",
        reply_to_external_message_id="<gmail-1@example.com>",
    )
    assert gmail_receipt.thread_id == "thread-1"
    assert "same Gmail conversation" in gmail_receipt.continuity_note

    outlook_reply_receipt = adapter.send_message(
        make_connection(
            provider="outlook",
            email_address="ada@outlook.example",
            token_expires_at=now + timedelta(hours=1),
        ),
        to_email="lead@example.com",
        to_name="Lead",
        subject="Reply",
        body="Thanks",
        thread_id="conversation-1",
        reply_to_external_message_id="<gmail-1@example.com>",
    )
    assert outlook_reply_receipt.thread_id == "conversation-1"
    assert "same Outlook conversation" in outlook_reply_receipt.continuity_note

    outlook_fallback_receipt = adapter.send_message(
        make_connection(
            provider="outlook",
            email_address="ada@outlook.example",
            token_expires_at=now + timedelta(hours=1),
        ),
        to_email="lead@example.com",
        to_name="Lead",
        subject="Fresh note",
        body="Hello again",
        thread_id="conversation-2",
        reply_to_external_message_id="<missing@example.com>",
    )
    assert outlook_fallback_receipt.thread_id == "conversation-2"
    assert "fresh provider note" in outlook_fallback_receipt.continuity_note


def test_oauth_mailbox_provider_helper_functions_and_runtime_job(monkeypatch) -> None:
    request = httpx.Request("GET", "https://example.test")
    rate_limited = httpx.Response(
        429,
        json={"error": {"message": "slow down"}},
        request=request,
    )
    with pytest.raises(
        MailboxProviderError,
        match="rate-limited",
    ):
        _read_json_response(rate_limited)

    bad_json = httpx.Response(200, text="not-json", request=request)
    with pytest.raises(MailboxProviderError, match="invalid JSON"):
        _read_json_response(bad_json)

    invalid_error_json = httpx.Response(400, text="not-json", request=request)
    with pytest.raises(MailboxProviderError, match="Mailbox provider request failed with status 400."):
        _read_json_response(invalid_error_json)

    string_error_payload = httpx.Response(
        400,
        json={"error": "plain failure"},
        request=request,
    )
    with pytest.raises(MailboxProviderError, match="plain failure"):
        _read_json_response(string_error_payload)

    list_payload = httpx.Response(200, json=["oops"], request=request)
    with pytest.raises(MailboxProviderError, match="unexpected payload"):
        _read_json_response(list_payload)

    assert _normalize_provider_error("token expired", 401).startswith("Reconnect this inbox")
    assert _normalize_provider_error("", 500).startswith("The mailbox provider")
    assert _normalize_provider_error("", 429).startswith("This inbox is being rate-limited")
    assert _normalize_provider_error("", 400) == "Mailbox provider request failed with status 400."

    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    with pytest.raises(MailboxProviderError, match="GOOGLE_OAUTH_CLIENT_ID"):
        _required_env("GOOGLE_OAUTH_CLIENT_ID")
    with pytest.raises(MailboxProviderError, match="missing access_token"):
        _require_string({}, "access_token")

    assert _optional_int("42") == 42
    assert _optional_int("nope") is None
    assert _optional_int(12) == 12
    assert _gmail_headers_to_dict([{"name": "Subject", "value": "Hello"}]) == {"Subject": "Hello"}
    assert _gmail_headers_to_dict("bad") == {}
    assert _gmail_headers_to_dict([None, {"name": "Subject"}]) == {}
    assert _parse_email_header("Ada Lovelace <ada@example.com>") == ("Ada Lovelace", "ada@example.com")
    assert _parse_email_header("") == ("", "")
    monkeypatch.setattr(oauth_mailbox_provider_module, "getaddresses", lambda values: [])
    assert _parse_email_header(",") == ("", "")
    assert _parse_message_datetime("Mon, 06 May 2024 12:00:00 +0000") == datetime(2024, 5, 6, 12, 0, tzinfo=UTC)
    assert _parse_message_datetime(None) is None
    assert _parse_message_datetime("bad-date") is None
    assert _parse_message_datetime("Mon, 06 May 2024 12:00:00") == datetime(2024, 5, 6, 12, 0, tzinfo=UTC)
    assert _parse_gmail_internal_date(str(int(datetime(2024, 5, 6, 12, 0, tzinfo=UTC).timestamp() * 1000))) == datetime(2024, 5, 6, 12, 0, tzinfo=UTC)
    assert _parse_gmail_internal_date(int(datetime(2024, 5, 6, 12, 0, tzinfo=UTC).timestamp() * 1000)) == datetime(2024, 5, 6, 12, 0, tzinfo=UTC)
    assert _parse_gmail_internal_date(object()) is None
    assert _parse_iso_datetime("2024-05-06T12:00:00Z") == datetime(2024, 5, 6, 12, 0, tzinfo=UTC)
    assert _parse_iso_datetime("") is None
    assert _parse_iso_datetime("bad") is None
    assert _parse_iso_datetime("2024-05-06T12:00:00") == datetime(2024, 5, 6, 12, 0, tzinfo=UTC)
    assert make_connection(email_address="@example.com").display_name == "Ada Lovelace"

    class FakeRepository:
        def __init__(self) -> None:
            self.mode = "connected"

        def list_mailbox_connection_user_ids(self) -> list[UUID]:
            return [make_user().id, UUID(int=make_user().id.int + 1)]

        def list_mailbox_connections(self, user: User) -> list[MailboxConnection]:
            now = datetime.now(tz=UTC)
            if user.id != make_user().id:
                return []
            return [
                make_connection(
                    provider="gmail",
                    token_expires_at=now + timedelta(hours=1),
                    watch_status="inactive",
                    last_watch_event_at=now,
                ),
                make_connection(
                    provider="gmail",
                    connection_mode="manual",
                    token_expires_at=now + timedelta(hours=1),
                ),
            ]

    class FakeUserRepository:
        def get_user_by_id(self, user_id: UUID) -> User | None:
            return make_user() if user_id == make_user().id else None

    connection_after_sync = replace(
        make_connection(
            provider="gmail",
            watch_status="active",
            watch_expires_at=datetime.now(tz=UTC) + timedelta(hours=2),
            last_watch_event_at=datetime.now(tz=UTC),
        ),
        last_watch_event_at=datetime.now(tz=UTC),
    )

    class FakeSyncUseCase:
        def __init__(self, repository, now, mailbox_provider) -> None:  # type: ignore[no-untyped-def]
            del repository, now, mailbox_provider

        def execute(self, user: User, connection_id: str):  # type: ignore[no-untyped-def]
            del user, connection_id
            return type(
                "Result",
                (),
                {
                    "synced_threads": 3,
                    "connection": connection_after_sync,
                },
            )()

    monkeypatch.setattr(mailbox_runtime, "build_lead_follow_up_repository", lambda: FakeRepository())
    monkeypatch.setattr(mailbox_runtime, "build_user_repository", lambda: FakeUserRepository())
    monkeypatch.setattr(mailbox_runtime, "build_mailbox_provider_from_env", lambda: object())
    monkeypatch.setattr(mailbox_runtime, "SyncMailboxConnectionUseCase", FakeSyncUseCase)

    summary = mailbox_runtime.run_scheduled_mailbox_sync_job()

    assert summary[0] == 1
    assert summary[1] == 3
    assert summary[2] == 1
    assert summary[3] == 1
    assert summary[4] == 1

    monkeypatch.setattr(mailbox_runtime, "build_user_repository", lambda: None)
    assert mailbox_runtime.run_scheduled_mailbox_sync_job() == (0, 0, 0, 0, 0)
