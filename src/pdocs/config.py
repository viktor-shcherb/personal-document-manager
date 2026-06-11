from __future__ import annotations

import os
import re
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG = Path("~/.config/pdocs/config.toml").expanduser()
SOURCE_PROFILE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class DeploymentConfig:
    id: str


@dataclass(frozen=True)
class PathsConfig:
    vault: Path
    inbox: Path
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
class GmailSourceProfile:
    name: str
    query: str
    initial_window: str
    overlap_window: str


@dataclass(frozen=True)
class FolderSourceProfile:
    name: str
    root: Path
    inbox: str
    extensions: tuple[str, ...]

    def inbox_path(self) -> Path:
        return _child_path(self.root, self.inbox)


@dataclass(frozen=True)
class ViewTargetConfig:
    name: str
    path: Path
    prune: bool


@dataclass(frozen=True)
class ViewsConfig:
    refresh_interval_seconds: int
    targets: dict[str, ViewTargetConfig]


@dataclass(frozen=True)
class SourcesConfig:
    gmail: dict[str, GmailSourceProfile]
    folder: dict[str, FolderSourceProfile]


@dataclass(frozen=True)
class AppConfig:
    path: Path
    deployment: DeploymentConfig
    paths: PathsConfig
    security: SecurityConfig
    gmail: GmailConfig
    backup: BackupConfig
    sources: SourcesConfig
    views: ViewsConfig
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


def _child_path(root: Path, value: str) -> Path:
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Configured path escapes its source root: {value!r}")
    return candidate


def validate_source_profile_name(name: str) -> str:
    if not SOURCE_PROFILE.fullmatch(name):
        raise ValueError(
            "Source profile names must use lowercase ASCII letters, digits, "
            "dots, underscores, and hyphens"
        )
    return name


def _source_profiles(data: dict) -> SourcesConfig:
    sources = data.get("sources", {})
    gmail_profiles = {}
    for name, profile in sources.get("gmail", {}).items():
        validate_source_profile_name(name)
        gmail_profiles[name] = GmailSourceProfile(
            name=name,
            query=profile["query"].strip(),
            initial_window=profile.get("initial_window", "30d"),
            overlap_window=profile.get("overlap_window", "24h"),
        )

    folder_profiles = {}
    for name, profile in sources.get("folder", {}).items():
        validate_source_profile_name(name)
        extensions = tuple(
            extension.lower() if extension.startswith(".") else f".{extension.lower()}"
            for extension in profile.get(
                "extensions",
                (".pdf", ".jpg", ".jpeg", ".png", ".heic"),
            )
        )
        folder_profiles[name] = FolderSourceProfile(
            name=name,
            root=_path(profile["root"]),
            inbox=profile.get("inbox", "Inbox"),
            extensions=extensions,
        )
        folder_profiles[name].inbox_path()
    return SourcesConfig(gmail=gmail_profiles, folder=folder_profiles)


def _views_config(data: dict) -> ViewsConfig:
    configured = data.get("views", {})
    interval = configured.get("refresh_interval_seconds", 300)
    if not isinstance(interval, int) or interval < 30:
        raise ValueError(
            "[views].refresh_interval_seconds must be an integer of at least 30"
        )

    targets = {}
    for name, target in configured.items():
        if name == "refresh_interval_seconds":
            continue
        validate_source_profile_name(name)
        if not isinstance(target, dict):
            raise ValueError(f"[views.{name}] must be a table")
        targets[name] = ViewTargetConfig(
            name=name,
            path=_path(target["path"]),
            prune=target.get("prune", True),
        )
    if not targets:
        raise ValueError("Configure at least one [views.NAME] destination")
    return ViewsConfig(
        refresh_interval_seconds=interval,
        targets=targets,
    )


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
        sources=_source_profiles(data),
        views=_views_config(data),
        raw=data,
    )
