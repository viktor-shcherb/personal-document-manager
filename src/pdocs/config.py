from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG = Path("~/.config/pdocs/config.toml").expanduser()


@dataclass(frozen=True)
class PathsConfig:
    vault: Path
    inbox: Path
    readable: Path
    state: Path


@dataclass(frozen=True)
class SecurityConfig:
    cipher: str
    keychain_service: str
    repository_key_account: str
    gpg_binary: str


@dataclass(frozen=True)
class GmailConfig:
    enabled: bool
    account: str
    oauth_client: Path
    token_service: str
    scan_queries: tuple[str, ...]


@dataclass(frozen=True)
class AppConfig:
    path: Path
    paths: PathsConfig
    security: SecurityConfig
    gmail: GmailConfig
    raw: dict


def _path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser().resolve()


def load_config(path: str | Path | None = None) -> AppConfig:
    configured = path or os.environ.get("PDOCS_CONFIG") or DEFAULT_CONFIG
    config_path = Path(configured).expanduser().resolve()
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    paths = data["paths"]
    security = data["security"]
    gmail = data.get("gmail", {})
    return AppConfig(
        path=config_path,
        paths=PathsConfig(
            vault=_path(paths["vault"]),
            inbox=_path(paths["inbox"]),
            readable=_path(paths["readable"]),
            state=_path(paths["state"]),
        ),
        security=SecurityConfig(
            cipher=security.get("cipher", "gpg-symmetric"),
            keychain_service=security.get("keychain_service", "pdocs"),
            repository_key_account=security.get(
                "repository_key_account", "repository-encryption"
            ),
            gpg_binary=security.get("gpg_binary", "gpg"),
        ),
        gmail=GmailConfig(
            enabled=gmail.get("enabled", False),
            account=gmail.get("account", ""),
            oauth_client=_path(
                gmail.get("oauth_client", "~/.config/pdocs/google-oauth-client.json")
            ),
            token_service=gmail.get("token_service", "pdocs-google-oauth"),
            scan_queries=tuple(gmail.get("scan_queries", ())),
        ),
        raw=data,
    )
