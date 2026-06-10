from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from pdocs.crypto import GpgSymmetricCipher


class StaticSecrets:
    def get(self, service: str, account: str) -> str:
        return "test-only-passphrase"

    def get_optional(self, service: str, account: str) -> str | None:
        return self.get(service, account)

    def create(self, service: str, account: str, value: str) -> None:
        raise NotImplementedError

    def replace(
        self,
        service: str,
        account: str,
        value: str,
        *,
        expected: str,
    ) -> None:
        raise NotImplementedError


@pytest.mark.skipif(shutil.which("gpg") is None, reason="GnuPG is not installed")
def test_gpg_round_trip_with_lossless_compression(tmp_path: Path):
    source = tmp_path / "message.eml"
    encrypted = tmp_path / "message.pdoc"
    restored = tmp_path / "restored.eml"
    source.write_bytes(b"Subject: Example\n\n" + b"compressible text\n" * 10000)

    cipher = GpgSymmetricCipher(
        SimpleNamespace(
            deployment=SimpleNamespace(
                id="00000000-0000-4000-8000-000000000001",
            ),
            security=SimpleNamespace(
                cipher="gpg-symmetric",
                gpg_binary="gpg",
            ),
        ),
        StaticSecrets(),
    )
    cipher.seal(source, encrypted)
    cipher.unseal(encrypted, restored)

    assert restored.read_bytes() == source.read_bytes()
    assert encrypted.stat().st_size < source.stat().st_size
