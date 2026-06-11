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
state = "{path.parent / "state"}"

[views]
refresh_interval_seconds = 300

[views.local]
path = "{path.parent / "readable"}"

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


def test_config_loads_named_source_profiles(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    _write_config(config_path, DEPLOYMENT_ID)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + f"""
[sources.gmail.documents]
query = "has:attachment"
initial_window = "60d"
overlap_window = "48h"

[sources.folder.iphone]
root = "{tmp_path / "exchange"}"
inbox = "Incoming"
extensions = ["PDF", ".HEIC"]

[views.icloud]
path = "{tmp_path / "exchange/Readable"}"
prune = true
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.sources.gmail["documents"].initial_window == "60d"
    folder = config.sources.folder["iphone"]
    assert folder.inbox_path() == (tmp_path / "exchange/Incoming")
    assert folder.extensions == (".pdf", ".heic")
    assert config.views.targets["icloud"].path == (tmp_path / "exchange/Readable")
    assert config.views.targets["icloud"].prune is True


def test_config_rejects_folder_path_outside_source_root(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    _write_config(config_path, DEPLOYMENT_ID)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + f"""
[sources.folder.invalid]
root = "{tmp_path / "exchange"}"
inbox = "../outside"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes its source root"):
        load_config(config_path)


def test_config_rejects_unsafe_source_profile_name(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    _write_config(config_path, DEPLOYMENT_ID)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + f"""
[sources.folder."../../outside"]
root = "{tmp_path / "exchange"}"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Source profile names"):
        load_config(config_path)
