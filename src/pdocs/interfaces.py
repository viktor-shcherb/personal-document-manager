from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SecretStore(Protocol):
    def get(self, service: str, account: str) -> str: ...

    def get_optional(self, service: str, account: str) -> str | None: ...

    def create(self, service: str, account: str, value: str) -> None: ...

    def replace(
        self,
        service: str,
        account: str,
        value: str,
        *,
        expected: str,
    ) -> None: ...


class Cipher(Protocol):
    def seal(self, source: Path, destination: Path) -> None: ...

    def unseal(self, source: Path, destination: Path) -> None: ...


@dataclass(frozen=True)
class BackupArtifact:
    path: Path
    repository: str
    commit: str
    size: int
    checksum: str


class BackupSink(Protocol):
    def replace(self, artifact: BackupArtifact) -> str: ...


@dataclass(frozen=True)
class SourceCandidate:
    reference: str
    thread_reference: str | None
    received_at: str
    source_time: str
    sender: str
    subject: str
    has_attachments: bool
