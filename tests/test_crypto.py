from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pdocs.config import SecurityConfig
from pdocs.crypto import GpgSymmetricCipher


class StaticSecrets:
    def get(self, service: str, account: str) -> str:
        return "test-only-passphrase"

    def set(self, service: str, account: str, value: str) -> None:
        raise NotImplementedError


@pytest.mark.skipif(shutil.which("gpg") is None, reason="GnuPG is not installed")
def test_gpg_round_trip_with_lossless_compression(tmp_path: Path):
    source = tmp_path / "message.eml"
    encrypted = tmp_path / "message.pdoc"
    restored = tmp_path / "restored.eml"
    source.write_bytes(b"Subject: Example\n\n" + b"compressible text\n" * 10000)

    cipher = GpgSymmetricCipher(
        SecurityConfig(
            cipher="gpg-symmetric",
            keychain_service="test",
            repository_key_account="test",
            gpg_binary="gpg",
        ),
        StaticSecrets(),
    )
    cipher.seal(source, encrypted)
    cipher.unseal(encrypted, restored)

    assert restored.read_bytes() == source.read_bytes()
    assert encrypted.stat().st_size < source.stat().st_size
