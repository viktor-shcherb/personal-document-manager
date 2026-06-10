from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from pdocs.backup import (
    BackupError,
    GITHUB_SECRETS,
    GoogleDriveBackupAuth,
    install_backup_workflow,
)


class StaticSecrets:
    def __init__(self, value: str):
        self.value = value

    def get(self, service: str, account: str) -> str:
        return self.value

    def set(self, service: str, account: str, value: str) -> None:
        self.value = value


def _upload_module():
    path = (
        Path(__file__).parents[1]
        / ".github"
        / "actions"
        / "google-drive-backup"
        / "upload.py"
    )
    spec = importlib.util.spec_from_file_location("pdocs_drive_upload", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_backup_workflow(tmp_path: Path):
    vault = tmp_path / "vault"
    subprocess.run(["git", "init", "-q", vault], check=True)

    workflow = install_backup_workflow(
        vault,
        action_ref="v1",
        folder_name="Encrypted Vault Backups",
    )

    text = workflow.read_text(encoding="utf-8")
    assert "on:\n  push:" in text
    assert "fetch-depth: 0" in text
    assert "google-drive-backup@v1" in text
    assert 'folder-name: "Encrypted Vault Backups"' in text
    assert "PDOCS_GOOGLE_DRIVE_REFRESH_TOKEN" in text

    with pytest.raises(BackupError):
        install_backup_workflow(vault)


def test_git_bundle_contains_all_local_branches_and_tags(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repository,
        check=True,
    )
    (repository / "record.pdoc").write_bytes(b"encrypted record")
    subprocess.run(["git", "add", "record.pdoc"], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "Add record"],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "branch", "archive"], cwd=repository, check=True)
    subprocess.run(["git", "tag", "issue-1"], cwd=repository, check=True)

    bundle = tmp_path / "repository.bundle"
    subprocess.run(
        [
            "git",
            "bundle",
            "create",
            bundle,
            "--branches",
            "--tags",
            "--remotes",
        ],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "bundle", "verify", bundle],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    heads = subprocess.run(
        ["git", "bundle", "list-heads", bundle],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "refs/heads/main" in heads
    assert "refs/heads/archive" in heads
    assert "refs/tags/issue-1" in heads


def test_configure_github_sets_named_secrets_without_arguments(
    monkeypatch: pytest.MonkeyPatch,
):
    token = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "refresh_token": "refresh-token",
    }
    config = SimpleNamespace(
        backup=SimpleNamespace(
            account="user@example.com",
            token_service="pdocs-drive",
        )
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("pdocs.backup.shutil.which", lambda command: "/usr/bin/gh")
    monkeypatch.setattr("pdocs.backup.subprocess.run", fake_run)

    GoogleDriveBackupAuth(
        config,
        StaticSecrets(json.dumps(token)),
    ).configure_github("owner/personal-documents")

    assert len(calls) == len(GITHUB_SECRETS)
    for command, kwargs in calls:
        assert command[:3] == ["gh", "secret", "set"]
        assert "--repo" in command
        assert kwargs["input"] in token.values()
        assert kwargs["input"] not in command


def test_upload_helpers_are_lossless_and_strict(tmp_path: Path):
    upload = _upload_module()
    payload = tmp_path / "repository.bundle"
    payload.write_bytes(b"complete git history\0" * 100)

    assert upload._md5(payload) == "76b500ea1aba6f0ae809ba850713c40e"
    assert upload._escape_query("owner/o'neil\\vault") == "owner/o\\'neil\\\\vault"
    assert upload._acknowledged_offset({"Range": "bytes=0-8388607"}) == 8388608
    assert upload._acknowledged_offset({}) == 0

    with pytest.raises(upload.DriveBackupError):
        upload._one_or_none([{"id": "one"}, {"id": "two"}], "backup")
