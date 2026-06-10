from __future__ import annotations

from types import SimpleNamespace

import pytest

from pdocs.cli import _repair_keychain_access, _validate_record_input


def _config(domains: list[str]):
    return SimpleNamespace(raw={"taxonomy": {"domains": domains}})


def test_record_input_rejects_unknown_configured_domain():
    args = SimpleNamespace(domain="employmnt", issued_at="2026-06-10")

    with pytest.raises(ValueError, match="configured domains: employment"):
        _validate_record_input(_config(["employment"]), args)


def test_record_input_rejects_non_iso_issue_date():
    args = SimpleNamespace(domain="employment", issued_at="June 10, 2026")

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _validate_record_input(_config(["employment"]), args)


def test_record_input_rejects_alternative_iso_date_form():
    args = SimpleNamespace(domain="employment", issued_at="2026-W24-3")

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _validate_record_input(_config(["employment"]), args)


def test_record_input_allows_configured_domain_and_iso_date():
    args = SimpleNamespace(domain="employment", issued_at="2026-06-10")

    _validate_record_input(_config(["employment"]), args)


def test_repair_keychain_access_preserves_secret():
    class MemoryKeychain:
        def __init__(self):
            self.value = "existing encryption secret"
            self.deleted = False

        def get(self, service: str, account: str) -> str:
            return self.value

        def delete(self, service: str, account: str) -> None:
            self.deleted = True
            self.value = ""

        def set(self, service: str, account: str, value: str) -> None:
            assert self.deleted
            self.value = value

    config = SimpleNamespace(
        security=SimpleNamespace(
            keychain_service="pdocs",
            repository_key_account="repository-encryption",
        )
    )
    keychain = MemoryKeychain()

    _repair_keychain_access(config, keychain)

    assert keychain.value == "existing encryption secret"
