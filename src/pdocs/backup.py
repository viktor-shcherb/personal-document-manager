from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import AppConfig
from .interfaces import SecretStore


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GITHUB_SECRETS = {
    "PDOCS_GOOGLE_DRIVE_CLIENT_ID": "client_id",
    "PDOCS_GOOGLE_DRIVE_CLIENT_SECRET": "client_secret",
    "PDOCS_GOOGLE_DRIVE_REFRESH_TOKEN": "refresh_token",
}
DEFAULT_ACTION = (
    "viktor-shcherb/personal-document-manager/.github/actions/google-drive-backup"
)


class BackupError(RuntimeError):
    pass


def _google_imports():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as error:
        raise BackupError(
            "Google OAuth dependencies are not installed; install the project "
            "with the 'google' extra"
        ) from error
    return InstalledAppFlow


class GoogleDriveBackupAuth:
    def __init__(self, config: AppConfig, secrets: SecretStore):
        self.config = config
        self.secrets = secrets

    def _account(self) -> str:
        if not self.config.backup.account:
            raise BackupError("Backup account is missing from configuration")
        return self.config.backup.account

    def authorize(self) -> None:
        InstalledAppFlow = _google_imports()
        client_path = self.config.backup.oauth_client
        if not client_path.is_file():
            raise BackupError(f"OAuth client file not found: {client_path}")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_path),
            [DRIVE_SCOPE],
        )
        credentials = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
        )
        if not credentials.refresh_token:
            raise BackupError(
                "Google did not issue a refresh token; revoke the existing app "
                "grant and authorize again"
            )
        self.secrets.set(
            self.config.backup.token_service,
            self._account(),
            credentials.to_json(),
        )

    def token_data(self) -> dict[str, str]:
        try:
            raw_token = self.secrets.get(
                self.config.backup.token_service,
                self._account(),
            )
        except Exception as error:
            raise BackupError(
                "Google Drive backup is not authorized; run 'pdocs backup auth'"
            ) from error
        try:
            token = json.loads(raw_token)
        except json.JSONDecodeError as error:
            raise BackupError("Stored Google Drive token is invalid") from error
        missing = [
            field
            for field in ("client_id", "client_secret", "refresh_token")
            if not token.get(field)
        ]
        if missing:
            raise BackupError(f"Stored Google Drive token lacks: {', '.join(missing)}")
        return token

    def configure_github(self, repository: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise BackupError("GitHub repository must use OWNER/REPOSITORY format")
        if not shutil.which("gh"):
            raise BackupError("GitHub CLI is not installed")
        token = self.token_data()
        for secret_name, token_field in GITHUB_SECRETS.items():
            result = subprocess.run(
                ["gh", "secret", "set", secret_name, "--repo", repository],
                input=token[token_field],
                text=True,
                capture_output=True,
            )
            if result.returncode:
                detail = result.stderr.strip() or "unknown GitHub CLI error"
                raise BackupError(f"Unable to set {secret_name}: {detail}")


def install_backup_workflow(
    vault: Path,
    *,
    action_ref: str = "v1",
    folder_name: str = "Personal Document Backups",
    force: bool = False,
) -> Path:
    if not (vault / ".git").exists():
        raise BackupError(f"Vault is not a Git repository: {vault}")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", action_ref):
        raise BackupError("Action reference contains unsupported characters")

    destination = vault / ".github" / "workflows" / "backup-google-drive.yml"
    if destination.exists() and not force:
        raise BackupError(
            f"Backup workflow already exists: {destination}; use --force to replace it"
        )
    workflow = f"""name: Backup Git history to Google Drive

on:
  push:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: pdocs-google-drive-backup-${{{{ github.repository }}}}
  cancel-in-progress: false

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: {DEFAULT_ACTION}@{action_ref}
        with:
          oauth-client-id: ${{{{ secrets.PDOCS_GOOGLE_DRIVE_CLIENT_ID }}}}
          oauth-client-secret: ${{{{ secrets.PDOCS_GOOGLE_DRIVE_CLIENT_SECRET }}}}
          oauth-refresh-token: ${{{{ secrets.PDOCS_GOOGLE_DRIVE_REFRESH_TOKEN }}}}
          folder-name: {json.dumps(folder_name)}
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(workflow, encoding="utf-8")
    return destination
