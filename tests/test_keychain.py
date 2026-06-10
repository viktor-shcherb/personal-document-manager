from __future__ import annotations

from pdocs.keychain import MacOSKeychain


class MemoryBackend:
    def __init__(self):
        self.values = {}

    def get(self, service: str, account: str) -> str:
        return self.values[(service, account)]

    def set(self, service: str, account: str, value: str) -> None:
        self.values[(service, account)] = value

    def delete(self, service: str, account: str) -> None:
        self.values.pop((service, account), None)


def test_keychain_delegates_without_exposing_secret_to_a_command():
    backend = MemoryBackend()
    keychain = MacOSKeychain(backend)

    keychain.set("pdocs-test", "encryption", "secret value")

    assert keychain.get("pdocs-test", "encryption") == "secret value"

    keychain.delete("pdocs-test", "encryption")

    assert backend.values == {}
