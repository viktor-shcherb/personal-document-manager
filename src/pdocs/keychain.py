from __future__ import annotations

import subprocess


class KeychainError(RuntimeError):
    pass


class MacOSKeychain:
    def get(self, service: str, account: str) -> str:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-s",
                service,
                "-a",
                account,
                "-w",
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode:
            raise KeychainError(
                f"Keychain item not found for service={service!r}, account={account!r}"
            )
        return result.stdout.rstrip("\n")

    def set(self, service: str, account: str, value: str) -> None:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "add-generic-password",
                "-U",
                "-s",
                service,
                "-a",
                account,
                "-w",
            ],
            input=f"{value}\n",
            text=True,
            capture_output=True,
        )
        if result.returncode:
            raise KeychainError("Unable to update macOS Keychain")
