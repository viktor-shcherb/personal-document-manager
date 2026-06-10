from __future__ import annotations

import pytest

from pdocs.keychain import KeychainConflictError, KeychainItemExistsError, MacOSKeychain


class MemoryBackend:
    def __init__(self):
        self.values = {}

    def get(self, service: str, account: str) -> str:
        return self.values[(service, account)]

    def create(self, service: str, account: str, value: str) -> None:
        key = (service, account)
        if key in self.values:
            raise KeychainItemExistsError("already exists")
        self.values[key] = value

    def replace(
        self,
        service: str,
        account: str,
        value: str,
        *,
        expected: str,
    ) -> None:
        key = (service, account)
        if self.values[key] != expected:
            raise KeychainConflictError("changed")
        self.values[(service, account)] = value

    def delete(self, service: str, account: str, *, expected: str) -> None:
        key = (service, account)
        if self.values[key] != expected:
            raise KeychainConflictError("changed")
        del self.values[key]


def test_keychain_create_never_overwrites_existing_item():
    backend = MemoryBackend()
    keychain = MacOSKeychain(backend)

    keychain.create("pdocs-test", "encryption", "secret value")

    assert keychain.get("pdocs-test", "encryption") == "secret value"

    with pytest.raises(KeychainItemExistsError):
        keychain.create("pdocs-test", "encryption", "replacement")

    assert keychain.get("pdocs-test", "encryption") == "secret value"


def test_keychain_replace_requires_expected_current_value():
    backend = MemoryBackend()
    keychain = MacOSKeychain(backend)
    keychain.create("pdocs-test", "oauth", "old token")

    with pytest.raises(KeychainConflictError):
        keychain.replace(
            "pdocs-test",
            "oauth",
            "new token",
            expected="unexpected token",
        )

    assert keychain.get("pdocs-test", "oauth") == "old token"

    keychain.replace(
        "pdocs-test",
        "oauth",
        "new token",
        expected="old token",
    )

    assert keychain.get("pdocs-test", "oauth") == "new token"


def test_repair_access_uses_verified_temporary_backup():
    backend = MemoryBackend()
    keychain = MacOSKeychain(backend)
    keychain.create("pdocs-test", "encryption", "secret value")

    keychain.repair_access("pdocs-test", "encryption")

    assert keychain.get("pdocs-test", "encryption") == "secret value"
    assert list(backend.values) == [("pdocs-test", "encryption")]


def test_failed_repair_retains_recovery_item():
    class FailingBackend(MemoryBackend):
        def __init__(self):
            super().__init__()
            self.fail_original_create = False

        def create(self, service: str, account: str, value: str) -> None:
            if self.fail_original_create and account == "encryption":
                raise RuntimeError("simulated create failure")
            super().create(service, account, value)

        def delete(self, service: str, account: str, *, expected: str) -> None:
            super().delete(service, account, expected=expected)
            if account == "encryption":
                self.fail_original_create = True

    backend = FailingBackend()
    keychain = MacOSKeychain(backend)
    keychain.create("pdocs-test", "encryption", "secret value")

    with pytest.raises(Exception, match="recovery copy remains"):
        keychain.repair_access("pdocs-test", "encryption")

    recovery_items = [
        value
        for (service, account), value in backend.values.items()
        if service == "pdocs-test" and ".pdocs-repair-backup-" in account
    ]
    assert recovery_items == ["secret value"]
