from __future__ import annotations

from pathlib import Path

import pytest

from pdocs.config import (
    SecretLocator,
    drive_token_locator,
    gmail_token_locator,
    load_config,
    repository_secret_locator,
)


DEPLOYMENT_ID = "00000000-0000-4000-8000-000000000001"


def _write_config(path: Path, deployment_id: str) -> None:
    path.write_text(
        f"""
[deployment]
id = "{deployment_id}"

[paths]
vault = "{path.parent / "vault"}"
inbox = "{path.parent / "inbox"}"
readable = "{path.parent / "readable"}"
state = "{path.parent / "state"}"

[security]
gpg_binary = "gpg"

[gmail]
enabled = true
account = "user@example.com"
oauth_client = "{path.parent / "gmail.json"}"

[backup]
enabled = true
account = "user@example.com"
oauth_client = "{path.parent / "drive.json"}"
""",
        encoding="utf-8",
    )


def test_secret_locators_are_namespaced_by_deployment_uuid(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    _write_config(config_path, DEPLOYMENT_ID)

    config = load_config(config_path)

    assert repository_secret_locator(config) == SecretLocator(
        service="pdocs.repository-encryption",
        account=DEPLOYMENT_ID,
    )
    assert gmail_token_locator(config).account == (f"{DEPLOYMENT_ID}:user@example.com")
    assert drive_token_locator(config).account == (f"{DEPLOYMENT_ID}:user@example.com")
    assert (
        len(
            {
                repository_secret_locator(config).service,
                gmail_token_locator(config).service,
                drive_token_locator(config).service,
            }
        )
        == 3
    )


def test_config_rejects_non_uuid_deployment_id(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    _write_config(config_path, "copied-instance")

    with pytest.raises(ValueError, match="must be a UUID"):
        load_config(config_path)
