from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path

from .config import AppConfig, gmail_token_locator
from .interfaces import SecretStore, SourceCandidate


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailError(RuntimeError):
    pass


def _google_imports():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as error:
        raise GmailError(
            "Google dependencies are not installed; install the project with "
            "the 'google' extra"
        ) from error
    return Request, Credentials, InstalledAppFlow, build


class GmailSource:
    def __init__(self, config: AppConfig, secrets: SecretStore):
        self.config = config
        self.secrets = secrets

    def _token_account(self) -> str:
        if not self.config.gmail.account:
            raise GmailError("Gmail account is missing from configuration")
        return self.config.gmail.account

    def _save_token(self, credentials, *, previous: str | None = None) -> None:
        self._token_account()
        locator = gmail_token_locator(self.config)
        value = credentials.to_json()
        if previous is None:
            self.secrets.create(locator.service, locator.account, value)
        else:
            self.secrets.replace(
                locator.service,
                locator.account,
                value,
                expected=previous,
            )

    def authorize(self, *, replace_existing: bool = False) -> None:
        _, _, InstalledAppFlow, _ = _google_imports()
        self._token_account()
        if not self.config.gmail.oauth_client.is_file():
            raise GmailError(
                f"OAuth client file not found: {self.config.gmail.oauth_client}"
            )
        locator = gmail_token_locator(self.config)
        previous = self.secrets.get_optional(locator.service, locator.account)
        if previous is not None and not replace_existing:
            raise GmailError(
                "Gmail token already exists in Keychain; use "
                "'pdocs gmail auth --replace-existing' only when deliberately "
                "reauthorizing this configured account"
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.config.gmail.oauth_client),
            SCOPES,
        )
        credentials = flow.run_local_server(port=0)
        self._save_token(credentials, previous=previous)

    def _credentials(self):
        Request, Credentials, _, _ = _google_imports()
        self._token_account()
        locator = gmail_token_locator(self.config)
        try:
            token = self.secrets.get(locator.service, locator.account)
        except Exception as error:
            raise GmailError(
                "Gmail is not authorized; run 'pdocs gmail auth'"
            ) from error
        credentials = Credentials.from_authorized_user_info(
            json.loads(token),
            SCOPES,
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._save_token(credentials, previous=token)
        if not credentials.valid:
            raise GmailError("Gmail credentials are invalid; authorize again")
        return credentials

    def _service(self):
        _, _, _, build = _google_imports()
        return build("gmail", "v1", credentials=self._credentials())

    @staticmethod
    def _headers(message: dict) -> dict[str, str]:
        headers = message.get("payload", {}).get("headers", [])
        return {item["name"].lower(): item["value"] for item in headers}

    def search(self, query: str, limit: int = 50) -> list[SourceCandidate]:
        service = self._service()
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=limit)
            .execute()
        )
        candidates = []
        for summary in response.get("messages", []):
            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=summary["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = self._headers(message)
            raw = self._raw(message["id"])
            parsed = BytesParser(policy=policy.default).parsebytes(raw)
            candidates.append(
                SourceCandidate(
                    reference=message["id"],
                    thread_reference=message.get("threadId"),
                    received_at=headers.get("date", ""),
                    source_time=datetime.fromtimestamp(
                        int(message["internalDate"]) / 1000,
                        tz=UTC,
                    )
                    .replace(microsecond=0)
                    .isoformat(),
                    sender=headers.get("from", ""),
                    subject=headers.get("subject", ""),
                    has_attachments=any(parsed.iter_attachments()),
                )
            )
        return candidates

    def _raw(self, message_id: str) -> bytes:
        message = (
            self._service()
            .users()
            .messages()
            .get(userId="me", id=message_id, format="raw")
            .execute()
        )
        return base64.urlsafe_b64decode(message["raw"])

    def inspect(self, message_id: str) -> dict:
        raw = self._raw(message_id)
        message = BytesParser(policy=policy.default).parsebytes(raw)
        body = message.get_body(preferencelist=("plain", "html"))
        content = body.get_content() if body else ""
        return {
            "message_id": message_id,
            "thread_id": (
                self._service()
                .users()
                .messages()
                .get(userId="me", id=message_id, format="minimal")
                .execute()
                .get("threadId")
            ),
            "from": message.get("From", ""),
            "to": message.get("To", ""),
            "date": message.get("Date", ""),
            "subject": message.get("Subject", ""),
            "body": content,
            "attachments": [
                {
                    "filename": attachment.get_filename(),
                    "media_type": attachment.get_content_type(),
                }
                for attachment in message.iter_attachments()
            ],
        }

    def inspect_thread(self, thread_id: str) -> list[dict]:
        thread = (
            self._service()
            .users()
            .threads()
            .get(userId="me", id=thread_id, format="minimal")
            .execute()
        )
        return [self.inspect(message["id"]) for message in thread.get("messages", [])]

    def export(self, message_id: str) -> Path:
        raw = self._raw(message_id)
        message = BytesParser(policy=policy.default).parsebytes(raw)
        destination = self.config.paths.inbox / "email" / message_id
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "message.eml").write_bytes(raw)

        attachments_dir = destination / "attachments"
        exported_attachments = []
        for index, attachment in enumerate(message.iter_attachments(), start=1):
            filename = attachment.get_filename() or f"attachment-{index}"
            filename = re.sub(r"[/\\\x00]", "_", filename)
            attachments_dir.mkdir(exist_ok=True)
            path = attachments_dir / filename
            if path.exists():
                path = attachments_dir / f"{index}-{filename}"
            payload = attachment.get_payload(decode=True)
            if payload is None:
                payload = attachment.as_bytes(policy=policy.default)
            path.write_bytes(payload)
            exported_attachments.append(str(path.relative_to(destination)))

        details = self.inspect(message_id)
        source = {
            "source": "gmail",
            "message_id": message_id,
            "thread_id": details["thread_id"],
            "from": details["from"],
            "to": details["to"],
            "date": details["date"],
            "subject": details["subject"],
            "attachments": exported_attachments,
        }
        (destination / "source.json").write_text(
            json.dumps(source, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return destination
