from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .config import SecurityConfig
from .interfaces import SecretStore


class CryptoError(RuntimeError):
    pass


class GpgSymmetricCipher:
    def __init__(self, config: SecurityConfig, secrets: SecretStore):
        self.config = config
        self.secrets = secrets

    def _passphrase(self) -> str:
        return self.secrets.get(
            self.config.keychain_service,
            self.config.repository_key_account,
        )

    def seal(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            dir=destination.parent,
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            result = subprocess.run(
                [
                    self.config.gpg_binary,
                    "--batch",
                    "--yes",
                    "--quiet",
                    "--symmetric",
                    "--cipher-algo",
                    "AES256",
                    "--compress-algo",
                    "zlib",
                    "--compress-level",
                    "6",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase-fd",
                    "0",
                    "--output",
                    str(temporary),
                    str(source),
                ],
                input=f"{self._passphrase()}\n",
                text=True,
                capture_output=True,
            )
            if result.returncode:
                detail = result.stderr.strip() or "no diagnostic output"
                raise CryptoError(f"GnuPG failed to encrypt {destination}: {detail}")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def unseal(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                self.config.gpg_binary,
                "--batch",
                "--yes",
                "--quiet",
                "--decrypt",
                "--pinentry-mode",
                "loopback",
                "--passphrase-fd",
                "0",
                "--output",
                str(destination),
                str(source),
            ],
            input=f"{self._passphrase()}\n",
            text=True,
            capture_output=True,
        )
        if result.returncode:
            destination.unlink(missing_ok=True)
            detail = result.stderr.strip() or "no diagnostic output"
            raise CryptoError(f"GnuPG failed to decrypt {source}: {detail}")
