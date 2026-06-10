from __future__ import annotations

import base64
import json
import re
import time
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path

from .config import AppConfig, gmail_token_locator
from .interfaces import SecretStore, SourceCandidate


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
RETRYABLE_STATUS_CODES = {429, 500, 503}


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
    def _execute(request, *, attempts: int = 7):
        for attempt in range(attempts):
            try:
                return request.execute()
            except Exception as error:
                status = getattr(getattr(error, "resp", None), "status", None)
                if status not in RETRYABLE_STATUS_CODES or attempt == attempts - 1:
                    raise
                time.sleep(1.5 * (attempt + 1))
        raise AssertionError("unreachable")

    @staticmethod
    def _headers(message: dict) -> dict[str, str]:
        headers = message.get("payload", {}).get("headers", [])
        return {item["name"].lower(): item["value"] for item in headers}

    @classmethod
    def _has_attachments(cls, payload: dict) -> bool:
        if payload.get("filename"):
            return True
        return any(cls._has_attachments(part) for part in payload.get("parts", ()))

    def search(self, query: str, limit: int = 50) -> list[SourceCandidate]:
        if limit < 0:
            raise GmailError("Gmail search limit must be zero or greater")
        service = self._service()
        summaries = []
        page_token = None
        while limit == 0 or len(summaries) < limit:
            remaining = limit - len(summaries) if limit else 500
            request = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=min(500, remaining),
                    pageToken=page_token,
                )
            )
            response = self._execute(request)
            summaries.extend(response.get("messages", ()))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        candidates = []
        for summary in summaries:
            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=summary["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
            )
            message = self._execute(message)
            headers = self._headers(message)
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
                    has_attachments=self._has_attachments(message.get("payload", {})),
                )
            )
        return candidates

    def _raw_response(self, message_id: str) -> tuple[dict, bytes]:
        request = (
            self._service()
            .users()
            .messages()
            .get(userId="me", id=message_id, format="raw")
        )
        response = self._execute(request)
        return response, base64.urlsafe_b64decode(response["raw"])

    def _raw(self, message_id: str) -> bytes:
        _, raw = self._raw_response(message_id)
        return raw

    def inspect(self, message_id: str) -> dict:
        raw = self._raw(message_id)
        message = BytesParser(policy=policy.default).parsebytes(raw)
        body = message.get_body(preferencelist=("plain", "html"))
        content = body.get_content() if body else ""
        return {
            "message_id": message_id,
            "thread_id": self._execute(
                self._service()
                .users()
                .messages()
                .get(userId="me", id=message_id, format="minimal")
            ).get("threadId"),
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
        request = (
            self._service()
            .users()
            .threads()
            .get(userId="me", id=thread_id, format="minimal")
        )
        thread = self._execute(request)
        return [self.inspect(message["id"]) for message in thread.get("messages", [])]

    def export(self, message_id: str) -> Path:
        response, raw = self._raw_response(message_id)
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

        source = {
            "source": "gmail",
            "message_id": message_id,
            "thread_id": response.get("threadId"),
            "from": message.get("From", ""),
            "to": message.get("To", ""),
            "date": message.get("Date", ""),
            "subject": message.get("Subject", ""),
            "attachments": exported_attachments,
        }
        (destination / "source.json").write_text(
            json.dumps(source, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return destination
