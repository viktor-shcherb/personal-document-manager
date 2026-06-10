from __future__ import annotations

import os
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG = Path("~/.config/pdocs/config.toml").expanduser()


@dataclass(frozen=True)
class DeploymentConfig:
    id: str


@dataclass(frozen=True)
class PathsConfig:
    vault: Path
    inbox: Path
    readable: Path
    state: Path


@dataclass(frozen=True)
class SecurityConfig:
    cipher: str
    gpg_binary: str


@dataclass(frozen=True)
class GmailConfig:
    enabled: bool
    account: str
    oauth_client: Path
    scan_queries: tuple[str, ...]


@dataclass(frozen=True)
class BackupConfig:
    enabled: bool
    provider: str
    account: str
    oauth_client: Path
    folder_name: str


@dataclass(frozen=True)
class AppConfig:
    path: Path
    deployment: DeploymentConfig
    paths: PathsConfig
    security: SecurityConfig
    gmail: GmailConfig
    backup: BackupConfig
    raw: dict


@dataclass(frozen=True)
class SecretLocator:
    service: str
    account: str


def repository_secret_locator(config: AppConfig) -> SecretLocator:
    return SecretLocator(
        service="pdocs.repository-encryption",
        account=config.deployment.id,
    )


def gmail_token_locator(config: AppConfig) -> SecretLocator:
    return SecretLocator(
        service="pdocs.gmail-oauth",
        account=f"{config.deployment.id}:{config.gmail.account}",
    )


def drive_token_locator(config: AppConfig) -> SecretLocator:
    return SecretLocator(
        service="pdocs.google-drive-oauth",
        account=f"{config.deployment.id}:{config.backup.account}",
    )


def _path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser().resolve()


def _deployment_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(
            "[deployment].id must be a UUID generated uniquely for this deployment"
        ) from error


def load_config(path: str | Path | None = None) -> AppConfig:
    configured = path or os.environ.get("PDOCS_CONFIG") or DEFAULT_CONFIG
    config_path = Path(configured).expanduser().resolve()
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    deployment = data["deployment"]
    paths = data["paths"]
    security = data["security"]
    gmail = data.get("gmail", {})
    backup = data.get("backup", {})
    default_oauth_client = gmail.get(
        "oauth_client", "~/.config/pdocs/google-oauth-client.json"
    )
    return AppConfig(
        path=config_path,
        deployment=DeploymentConfig(id=_deployment_id(deployment["id"])),
        paths=PathsConfig(
            vault=_path(paths["vault"]),
            inbox=_path(paths["inbox"]),
            readable=_path(paths["readable"]),
            state=_path(paths["state"]),
        ),
        security=SecurityConfig(
            cipher=security.get("cipher", "gpg-symmetric"),
            gpg_binary=security.get("gpg_binary", "gpg"),
        ),
        gmail=GmailConfig(
            enabled=gmail.get("enabled", False),
            account=gmail.get("account", ""),
            oauth_client=_path(default_oauth_client),
            scan_queries=tuple(gmail.get("scan_queries", ())),
        ),
        backup=BackupConfig(
            enabled=backup.get("enabled", False),
            provider=backup.get("provider", "google-drive"),
            account=backup.get("account", gmail.get("account", "")),
            oauth_client=_path(backup.get("oauth_client", default_oauth_client)),
            folder_name=backup.get("folder_name", "Personal Document Backups"),
        ),
        raw=data,
    )
