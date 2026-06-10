from __future__ import annotations

from types import SimpleNamespace

import pytest

from pdocs.gmail import GmailError, GmailSource


DEPLOYMENT_ID = "00000000-0000-4000-8000-000000000001"


class ExistingSecrets:
    def get_optional(self, service: str, account: str) -> str | None:
        return "existing token"


def test_authorize_refuses_existing_token_before_opening_browser(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    oauth_client = tmp_path / "oauth.json"
    oauth_client.write_text("{}", encoding="utf-8")
    config = SimpleNamespace(
        deployment=SimpleNamespace(id=DEPLOYMENT_ID),
        gmail=SimpleNamespace(
            account="user@example.com",
            oauth_client=oauth_client,
        ),
    )

    class UnexpectedFlow:
        @classmethod
        def from_client_secrets_file(cls, *args, **kwargs):
            raise AssertionError("OAuth browser flow must not start")

    monkeypatch.setattr(
        "pdocs.gmail._google_imports",
        lambda: (None, None, UnexpectedFlow, None),
    )

    with pytest.raises(GmailError, match="already exists"):
        GmailSource(config, ExistingSecrets()).authorize()


class Request:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class Messages:
    def __init__(self):
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        if kwargs.get("pageToken") is None:
            return Request(
                {
                    "messages": [{"id": "message-1"}],
                    "nextPageToken": "next",
                }
            )
        return Request({"messages": [{"id": "message-2"}]})

    def get(self, **kwargs):
        message_id = kwargs["id"]
        return Request(
            {
                "id": message_id,
                "threadId": f"thread-{message_id}",
                "internalDate": "1781100000000",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": "Document"},
                        {"name": "Date", "value": "Wed, 10 Jun 2026"},
                    ],
                    "parts": (
                        [{"filename": "document.pdf"}]
                        if message_id == "message-2"
                        else []
                    ),
                },
            }
        )


class Service:
    def __init__(self):
        self.messages_api = Messages()

    def users(self):
        return self

    def messages(self):
        return self.messages_api


def test_search_paginates_all_messages_without_raw_downloads():
    gmail = GmailSource(
        SimpleNamespace(gmail=SimpleNamespace(account="user@example.com")),
        ExistingSecrets(),
    )
    service = Service()
    gmail._service = lambda: service

    candidates = gmail.search("after:2022/06/10", limit=0)

    assert [candidate.reference for candidate in candidates] == [
        "message-1",
        "message-2",
    ]
    assert candidates[0].has_attachments is False
    assert candidates[1].has_attachments is True
    assert len(service.messages_api.list_calls) == 2


def test_search_rejects_negative_limit():
    gmail = GmailSource(
        SimpleNamespace(gmail=SimpleNamespace(account="user@example.com")),
        ExistingSecrets(),
    )

    with pytest.raises(GmailError, match="zero or greater"):
        gmail.search("after:2022/06/10", limit=-1)


def test_execute_retries_rate_limits(monkeypatch: pytest.MonkeyPatch):
    class RateLimitError(RuntimeError):
        resp = SimpleNamespace(status=429)

    class FlakyRequest:
        def __init__(self):
            self.calls = 0

        def execute(self):
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError
            return {"ok": True}

    request = FlakyRequest()
    sleeps = []
    monkeypatch.setattr("pdocs.gmail.time.sleep", sleeps.append)

    assert GmailSource._execute(request) == {"ok": True}
    assert request.calls == 2
    assert sleeps == [1.5]
